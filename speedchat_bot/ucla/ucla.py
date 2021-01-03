import discord
from discord.ext import commands, tasks
import random
import json
import urllib.parse as urlparse
from urllib.parse import urlencode
import requests
import re
import os
from bs4 import BeautifulSoup


import asyncio
from pyppeteer import launch

from constants import *
from perms import *


# regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\(".*?%s",({"Term":"21W","SubjectAreaCode":"%s","CatalogNumber":"%s","IsRoot":true,"SessionGroup":"%%","ClassNumber":"\W*%s\W*","SequenceNumber":null,"Path":"[\d_]*?%s","MultiListedClassFlag":"n",.*?}\))'
# Assumptions: class number is always either 001,002, etc., or '%'
regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("[\d_]*?%s[\d]{0,3}",({"Term":"%s".*?"ClassNumber":" *?[\d%%]{1,3} *.*?"Path":"[\d_]*?%s[\d]{0,3}".*?"Token":".*?"})\);'



def generate_url(base_url, params):
    """Generate a URL given many parameters to attach as query strings"""
    url_parts = list(urlparse.urlparse(base_url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)

    url_parts[4] = urlencode(query)

    final_url = urlparse.urlunparse(url_parts).replace("%27", "%22")
    return final_url


def parse_catalog_no(catalog):
    match = re.match(r"([0-9]+)([a-zA-Z]+)", catalog, re.I)
    if match:
        return '{:>04s}'.format(match[1]) + match[2]
    else:
        return '{:>04s}'.format(catalog)

# TODO: Check subjects with spaces, i.e. COM SCI
def search_for_class_model(subject, catalog, term):
    """Model?"""
    # Separate catalog no (151AH) into {numbers: 151, letters:AH}. The reason for this is really annoying:
    # For some reason, when padding the overall course name with zeroes, you only consider the length of the number part.
    # For example, Math 151AH would become MATH0151AH, while Math 31A would become MATH0031A
    better_catalog = parse_catalog_no(catalog)

    headers = {"X-Requested-With": "XMLHttpRequest"}
    pageNumber = 1
    while True:
        url = f'https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView?search_by=subject&model=%7B%22subj_area_cd%22%3A%22{subject}%22%2C%22search_by%22%3A%22Subject%22%2C%22term_cd%22%3A%22{term}%22%2C%22SubjectAreaName%22%3A%22Mathematics+(MATH)%22%2C%22CrsCatlgName%22%3A%22Enter+a+Catalog+Number+or+Class+Title+(Optional)%22%2C%22ActiveEnrollmentFlag%22%3A%22n%22%2C%22HasData%22%3A%22True%22%7D&pageNumber={pageNumber}&filterFlags=%7B%22enrollment_status%22%3A%22O%2CW%2CC%2CX%2CT%2CS%22%2C%22advanced%22%3A%22y%22%2C%22meet_days%22%3A%22M%2CT%2CW%2CR%2CF%22%2C%22start_time%22%3A%228%3A00+am%22%2C%22end_time%22%3A%227%3A00+pm%22%2C%22meet_locations%22%3Anull%2C%22meet_units%22%3Anull%2C%22instructor%22%3Anull%2C%22class_career%22%3Anull%2C%22impacted%22%3Anull%2C%22enrollment_restrictions%22%3Anull%2C%22enforced_requisites%22%3Anull%2C%22individual_studies%22%3Anull%2C%22summer_session%22%3Anull%7D'
        r = requests.get(url, headers=headers)

        # when we get past all the result pages, we'll get nothing from requests.get
        if r.content == b'':
            break

        real_regex = regex % (subject + better_catalog, term, subject + better_catalog)
        # print(real_regex)
        found = re.finditer(real_regex, str(r.content))
        
        if found:
            for i in found:
                yield i[1]

        pageNumber += 1



# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        f = open('speedchat_bot/ucla/subjects.json') 
        self.subjectsJSON = json.load(f)
        # self.class_regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("%s",({"Term":"20W","SubjectAreaCode":"%s","CatalogNumber":"%s","IsRoot":true,"SessionGroup":"%%","ClassNumber":"\W*%s\W*","SequenceNumber":null,"Path":"%s","MultiListedClassFlag":"n",.*?})'
        
        self.tenativeRegex     = re.compile('^Tenative')
        self.cancelledRegex    = re.compile('^Cancelled')
        self.closedByDeptRegex = re.compile('^Closed by Dept[a-zA-Z,/ ]*(\((?P<Capacity>\d+) capacity, (?P<EnrolledCount>\d+) enrolled, (?P<WaitlistedCount>\d+) waitlisted\))?')
        self.classFullRegex    = re.compile('ClosedClass Full \((?P<Capacity>\d+)\)(, Over Enrolled By (?P<OverenrolledCount>\d+))?')
        self.classOpenRegex    = re.compile('Open(?P<EnrolledCount>\d+) of (?P<Capacity>\d+) Enrolled(\d+) Spots? Left')
        self.waitlistOnlyRegex = re.compile('^Waitlist$')
        self.waitlistFullRegex = re.compile('^WaitlistClass Full \((?P<Capacity>\d+)\)(, Over Enrolled By (?P<OverenrolledCount>\d+))?')
        # Waitlist regexes
        self.waitlistOpenRegex   = re.compile('(?P<WaitlistCount>\d+) of (?P<WaitlistCapacity>\d+) Taken')
        self.noWaitlistRegex     = re.compile('No Waitlist')
        self.waitlistClosedRegex = re.compile('Waitlist Full \((?P<WaitlistCapacity>\d+)\)')

        self.term = "21W"
        self.reload_json()




    @commands.command(help="Switch to a new term for searching (i.e. to 20F)")
    @is_admin()
    async def switch_term(self, ctx, new_term: str):
        # First, is this the right format?
        template = re.compile('[\d]{2}[FWS]{1}') # i.e. 20F
        if template.match(new_term) is None:
            ctx.channel.send(f"Sorry, {new_term} looks like a malformed term.")
            return

        if self.term and self.term is new_term:
            ctx.channel.send(f"You're already on {self.term}!")
            return


        # If we pass the checks, actually switch term, and initialize class list
        self.term = new_term

        

    def reload_json(self):
        if os.path.exists("class_names.json"):
            with open('class_names.json') as fp:
                data = json.load(fp)
                if data["term"] == self.term: # no need to update json
                    return
        

        class_name_dict = {}
        headers = {"X-Requested-With": "XMLHttpRequest"}
        for subject in self.subjectsJSON:
            pageNumber = 1
            # Replace everything but 
            subject_name = urlparse.quote(subject["value"]).replace('%20', '+')
            all_classes = {}
            while True:
                url = f'https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView?search_by=subject&model=%7B%22subj_area_cd%22%3A%22{subject_name}%22%2C%22search_by%22%3A%22Subject%22%2C%22term_cd%22%3A%22{self.term}%22%2C%22SubjectAreaName%22%3A%22Mathematics+(MATH)%22%2C%22CrsCatlgName%22%3A%22Enter+a+Catalog+Number+or+Class+Title+(Optional)%22%2C%22ActiveEnrollmentFlag%22%3A%22n%22%2C%22HasData%22%3A%22True%22%7D&pageNumber={pageNumber}&filterFlags=%7B%22enrollment_status%22%3A%22O%2CW%2CC%2CX%2CT%2CS%22%2C%22advanced%22%3A%22y%22%2C%22meet_days%22%3A%22M%2CT%2CW%2CR%2CF%22%2C%22start_time%22%3A%228%3A00+am%22%2C%22end_time%22%3A%227%3A00+pm%22%2C%22meet_locations%22%3Anull%2C%22meet_units%22%3Anull%2C%22instructor%22%3Anull%2C%22class_career%22%3Anull%2C%22impacted%22%3Anull%2C%22enrollment_restrictions%22%3Anull%2C%22enforced_requisites%22%3Anull%2C%22individual_studies%22%3Anull%2C%22summer_session%22%3Anull%7D'
                # print(url)
                r = requests.get(url, headers=headers)
                soup = BeautifulSoup(r.content, "lxml")
                div_script_pairs = zip(soup.select("h3.head"), soup.select("script"))

                for div, script in div_script_pairs:
                    # TODO: What if duplicate tokens?!?!
                    all_classes[re.search('"Token":"(.*?)"}',script.decode_contents())[1]] = div.select_one('a[id$="-title"]').text

                # all_classes = all_classes + list(map(lambda pair: {re.search('"Token":"(.*?)"}',pair[1].decode_contents())[1]: pair[0].select_one('a[id$="-title"]').text}, div_script_pairs))

                # when we get past all the result pages, we'll get nothing from requests.get
                if r.content == b'':
                    break
                
                pageNumber += 1

            class_name_dict[subject_name] = all_classes
            print("loaded", subject["label"])


        class_names_file = open("class_names.json", "w")
        class_names_file.write(json.dumps({"term": self.term, "class_names" :class_name_dict}, indent=4, sort_keys=True))
        class_names_file.close()
        print("done")



    def _ParseEnrollmentStatus(self, potential_status, statusRegex, my_string):
        matches = statusRegex.match(my_string)
        if matches is None:
            return None
        else:
            match_dict = matches.groupdict()
            return {
                "enrollment_status": potential_status, 
                # TODO: Is it okay to return 0 
                "enrollment_capacity": int(match_dict["Capacity"] or 0) if "Capacity" in match_dict else None, 
                "enrollment_count": int(match_dict["EnrolledCount"] or 0) if "EnrolledCount" in match_dict else None,
                "enrollment_over": int(match_dict["OverenrolledCount"] or 0) if "OverenrolledCount" in match_dict else None,
            }

    def _parseWaitlistData(self, statusRegex, my_string):
        matches = statusRegex.match(my_string)
        if matches is None:
            return None
        else:
            match_dict = matches.groupdict()
            return {
                "waitlist_capacity": int(match_dict["Capacity"] or 0) if "Capacity" in match_dict else None, 
                "waitlist_count": int(match_dict["EnrolledCount"] or 0) if "EnrolledCount" in match_dict else None,
            }


    def _parse_class(self, soup, full_class_name=False):
        status = soup.select_one("div[id$=-status_data]").text
        # TODO: Multiple locations!
        locations = soup.select_one("div[id$=-location_data]").text
        days = []
        times = []

        # I hope it always looks lile <div id="blah-units_data"><p> # of units </p></div>
        # could be wrong...
        units = soup.select_one("div[id$=-units_data] p").text

        details_url = "https://sa.ucla.edu" + soup.select_one('a[title^="Class Detail for "]')['href']
        section_name = soup.select_one('a[title^="Class Detail for "]').text
        details_url_parts = dict(urlparse.parse_qsl(list(urlparse.urlparse(details_url))[4]))

        # I don't like this, but a quick detour into the public results endpoint allows us to get
        # the full class name (i.e. "Math 31B - Integration and Infinite Series")
        # Perhaps could use this entirely for parsing?
        # params = {'t': TERM, 'sBy': 'classidnumber','id': details_url_parts['class_id'].strip()}
        # final_url = generate_url("https://sa.ucla.edu/ro/Public/SOC/Results", params)
        # headers = {"X-Requested-With": "XMLHttpRequest"}
        # r = requests.get(final_url, headers=headers)
        # title_soup = BeautifulSoup(r.content, "lxml")
        # class_title = title_soup.select_one('a[id$="-title"]').text




        class_dict =  {
            # "class_id": details_url_parts['class_id'].strip(),
            # "subject":  details_url_parts['subj_area_cd'].strip(),
            "class_no": details_url_parts['class_no'].strip(),
            # "title": class_title,
            "term": self.term,
            "section_name": section_name,
            "days": days,
            "times": times,
            "locations": locations,
            "units": units,
            "url": details_url,
            "status": status, 
        }

        if full_class_name:
            script = soup.select_one("script").decode_contents()
            token = re.search('"Token":"(.*?)"}',script)[1]
            subject = re.search('"SubjectAreaCode":"(.*?)"',script)[1].strip()
            with open('class_names.json') as fp:
                data = json.load(fp)["class_names"]
                class_dict["class_name"] = data[subject][token]

        # BEGIN PARSING STATUS (the hard part)

        # make a guess at what the status is, and return the first one that works
        a = self._ParseEnrollmentStatus("Tentative", self.tenativeRegex, status)                   \
            or self._ParseEnrollmentStatus("Cancelled", self.cancelledRegex, status)               \
            or self._ParseEnrollmentStatus("Closed By Department", self.closedByDeptRegex, status) \
            or self._ParseEnrollmentStatus("Full", self.classFullRegex, status)                    \
            or self._ParseEnrollmentStatus("Open", self.classOpenRegex, status)                    \
            or self._ParseEnrollmentStatus("Waitlist Full", self.waitlistFullRegex, status)        \
            or self._ParseEnrollmentStatus("Waitlist Only", self.waitlistOnlyRegex, status)        \
            or None
        # make a guess at what the waitlisting status is like (open with some x out of y spots, no waitlist, or )
        b = self._parseWaitlistData(self.waitlistOpenRegex, status) \
            or self._parseWaitlistData(self.noWaitlistRegex, status)\
            or self._parseWaitlistData(self.noWaitlistRegex, status)\
            or None

        # TODO: I'm a bit uncomfortable with this. By merging dictionaries only when it a,b exist,
        # some of the keys like "enrollment_capacity" won't be present. Will that be a problem later
        # down the line??
        if a: class_dict = {**class_dict, **a} # grr if this were python 3.9 we could just use |
        if b: class_dict = {**class_dict, **b}

        # don't need to clean ints, only strings
        return {k:v.replace("\r", '').replace("\n", '').strip() if type(v) == "str" else v for k, v in class_dict.items()}

    @commands.command(help="Oof")
    @is_admin()
    async def searchclass(self, ctx, subject: str, catalog: str, mode="slow"):
        model_choices = search_for_class_model(subject, catalog, self.term)
        url = "https://sa.ucla.edu/ro/Public/SOC/Results"

        # which model to choose? display choices to user, let them choose, then add to JSON
        htmls = []
        for model in model_choices:
            # await ctx.channel.send(model)
            print(model)
            htmls = htmls + self.check_class(model)

        htmls = {chr(i+65): htmls[i] for i in range(len(htmls))}

        # I can't decide how this ought to be designed (idk anything about UX), but this is how it's gonna work:
        # there are two modes: slow and fast
        # Slow: use pyppeteer to query results by class_id, and take screenshot, send in channel
            # pros: looks pretty, easier to read
            # cons: I'm not sure how much I trust the ability to parse the class_id (see class_id assumption)
            # also, slower by like 7 seconds, might be annoying when looking through lots of classes

        # Fast: Just send 
            # pros: 
            # cons: Looks pretty ugly, quite a bit harder to read easily (especially picking out the important)
            # bits like enrollment status and instructor

        if mode == "slow":
            browser = await launch()

            for key, class_html in htmls.items():
                # class_no assumption: the class_id is always the first 9 digits of the id of the first div in the GetCourseSummary html
                class_id = self.parse_class_id(str(class_html))
                params = {'t': self.term, 'sBy': 'classidnumber','id': class_id}
                final_url = generate_url(url, params)

                page = await browser.newPage()

                await page.goto(final_url)

                await page.waitForSelector('#resultsTitle');          
                element = await page.querySelector('#resultsTitle')


                await element.screenshot(path='candidate.png')
                await ctx.channel.send(f"Choice {key}:")
                await ctx.channel.send(file=discord.File('candidate.png'))

                if os.path.exists("candidate.png"):
                    os.remove("candidate.png")

            await browser.close()

        else: # we're in fast mode
            for key, class_html in htmls.items():
                # await ctx.channel.send(f"Choice {key}: " + json.dumps(self._parse_class(class_html), indent=4))
                parsed_class = self._parse_class(class_html, full_class_name=True)
                embedVar = discord.Embed(title=f'(Choice {key}) {parsed_class["class_name"]}', description=f'[{parsed_class["section_name"]}]({parsed_class["url"]})', color=0x00ff00)
                embedVar.add_field(name="Term", value=parsed_class["term"], inline=True)
                embedVar.add_field(name="Times", value=parsed_class["times"], inline=True)
                embedVar.add_field(name="Locations", value=parsed_class["locations"], inline=True)

                embedVar.add_field(name="Status", value=f'{parsed_class["enrollment_status"]} ({parsed_class["enrollment_count"]}/{parsed_class["enrollment_capacity"]})', inline=True)

                await ctx.channel.send(embed=embedVar)


        while True:
            status = await ctx.send(f"Choose the class you want keep an eye on.")
            for key in htmls:
                await status.add_reaction(CHOICES[key])
            await status.add_reaction(NO_EMOJI)

            try:
                r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: u == ctx.author)
            except asyncio.TimeoutError:
                return
            else:
                if r.emoji == NO_EMOJI:
                    await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                    return 
                if r.emoji in CHOICES.values():
                    for key, value in CHOICES.items():
                        if r.emoji == value:
                            await status.edit(content=f"You've selected choice {key}")
                            my_choice = key
                            break
                    break

        if my_choice:
            # read
            try:
                a_file = open("sample_file.json", "r")
                json_object = json.load(a_file)
                a_file.close()
            except FileNotFoundError:
                json_object = {}

            #write
            json_object["d"] = 100

            a_file = open("sample_file.json", "w")
            json.dump(json_object, a_file)
            a_file.close()


    def parse_class_id(self, html):
        regex = '<div class="row-fluid data_row primary-row class-info class-not-checked" id="([\d]{9})_'
        match = re.search(regex, str(html))
        return match[1] if match else None
        

    def check_class(self, model):
        FilterFlags = '{"enrollment_status":"O,W,C,X,T,S","advanced":"y","meet_days":"M,T,W,R,F","start_time":"8:00 am","end_time":"7:00 pm","meet_locations":null,"meet_units":null,"instructor":null,"class_career":null,"impacted":null,"enrollment_restrictions":null,"enforced_requisites":null,"individual_studies":null,"summer_session":null}'
                
        params = {'search_by':'subject','model':model, 'FilterFlags':FilterFlags, '_':'1571869764769'}

        url = "https://sa.ucla.edu/ro/Public/SOC/Results/GetCourseSummary"
        
        headers = {"X-Requested-With": "XMLHttpRequest"}


        final_url = generate_url(url, params)
        print(final_url)
        r = requests.get(final_url, headers=headers)

        soup = BeautifulSoup(r.content, features="lxml")
        # print(soup)
        return soup.select(".row-fluid.data_row.primary-row.class-info.class-not-checked")
        # print(self._parse_class(soup))









    @tasks.loop(seconds=5.0, count=5)
    async def slow_count(self, ctx):
        await self.searchclass(ctx, "MATH", "110A")
        print(self.slow_count.current_loop)

    @slow_count.after_loop
    async def after_slow_count(self):
        print('done!')


    @commands.command(help="Count")
    async def start_the_count(self, ctx):
        self.slow_count.start(ctx)




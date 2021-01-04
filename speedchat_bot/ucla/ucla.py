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

def new_search_for_class_model(subject, catalog):
    better_subject_name = urlparse.quote(subject).replace('%20', '+')
    with open("class_names.json") as fp:
        # TODO: Maybe separate subjects into their own json?
        data = json.load(fp)['class_names']
        classes_in_subject = data[better_subject_name]
        for my_class in classes_in_subject:
            if my_class[0].split()[0] == str(catalog):
                yield (f"{better_subject_name} {my_class[0]}", my_class[1])


# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        f = open('speedchat_bot/ucla/subjects.json') 
        self.subjectsJSON = json.load(f)
        f.close()
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
        self.PUBLIC_RESULTS_URL = "https://sa.ucla.edu/ro/Public/SOC/Results"
        self.GET_COURSE_SUMMARY_URL = "https://sa.ucla.edu/ro/Public/SOC/Results/GetCourseSummary"


    def _generate_embed(self, parsed_class, key=None):
        """Build a Discord Embed message based on a class dictionary, for sending in a fast mode"""
        title = '{choice} {class_name}'.format(choice=f"(Choice {key})" if key else '', class_name=parsed_class["class_name"])
        
        embedVar = discord.Embed(title=title, description=f'[{parsed_class["section_name"]}]({parsed_class["url"]})', color=0x00ff00)
        embedVar.add_field(name="Term", value=parsed_class["term"], inline=True)
        embedVar.add_field(name="Times", value=parsed_class["times"], inline=True)
        embedVar.add_field(name="Locations", value=parsed_class["locations"], inline=True)

        embedVar.add_field(name="Status", value=f'{parsed_class["enrollment_status"]} ({parsed_class["enrollment_count"]}/{parsed_class["enrollment_capacity"]} enrolled)', inline=True)

        return embedVar

    async def _generate_image(self, browser, class_id, ctx, key=None):
        """Take a picture of a class id's details page, for sending in a slow mode"""
        params = {'t': self.term, 'sBy': 'classidnumber','id': class_id}
        final_url = generate_url(self.PUBLIC_RESULTS_URL, params)

        page = await browser.newPage()

        await page.goto(final_url)

        await page.waitForSelector('#resultsTitle');          
        element = await page.querySelector('#resultsTitle')

        # TODO: edit html with jquery or smth to add in (Choice X) to title of class
        await element.screenshot(path='candidate.png')
        if key:
            await ctx.channel.send(f"Choice {key}", file=discord.File('candidate.png'))
        else:
            await ctx.channel.send(file=discord.File('candidate.png'))

        if os.path.exists("candidate.png"):
            os.remove("candidate.png")


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
        self.reload_json()
        

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
            # Replace everything but spaces, which get changed to "+", i.e. "ART HIS" -> "ART+HIS"
            subject_name = urlparse.quote(subject["value"]).replace('%20', '+')
            all_classes = []
            while True:
                url = f'https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView?search_by=subject&model=%7B%22subj_area_cd%22%3A%22{subject_name}%22%2C%22search_by%22%3A%22Subject%22%2C%22term_cd%22%3A%22{self.term}%22%2C%22SubjectAreaName%22%3A%22Mathematics+(MATH)%22%2C%22CrsCatlgName%22%3A%22Enter+a+Catalog+Number+or+Class+Title+(Optional)%22%2C%22ActiveEnrollmentFlag%22%3A%22n%22%2C%22HasData%22%3A%22True%22%7D&pageNumber={pageNumber}&filterFlags=%7B%22enrollment_status%22%3A%22O%2CW%2CC%2CX%2CT%2CS%22%2C%22advanced%22%3A%22y%22%2C%22meet_days%22%3A%22M%2CT%2CW%2CR%2CF%22%2C%22start_time%22%3A%228%3A00+am%22%2C%22end_time%22%3A%227%3A00+pm%22%2C%22meet_locations%22%3Anull%2C%22meet_units%22%3Anull%2C%22instructor%22%3Anull%2C%22class_career%22%3Anull%2C%22impacted%22%3Anull%2C%22enrollment_restrictions%22%3Anull%2C%22enforced_requisites%22%3Anull%2C%22individual_studies%22%3Anull%2C%22summer_session%22%3Anull%7D'
                # print(url)
                r = requests.get(url, headers=headers)
                soup = BeautifulSoup(r.content, "lxml")
                div_script_pairs = zip(soup.select("h3.head"), soup.select("script"))

                for div, script in div_script_pairs:
                    # I can't guarantee that there isn't some wack scenario where there are two classes
                    # names exactly the same, make each name+model pair like a tuple instead
                    all_classes.append([div.select_one('a[id$="-title"]').text, re.search("({.*?})", script.decode_contents())[1]])
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


    def _ParseEnrollmentStatusLogic(self, potential_status, enrollment_dict):
        """
        Sometimes the status string doesn't say either the Capacity and or the Count,
        i.e. "ClosedClass Full (45), Over Enrolled By 3" doesn't give any info on the count
        but since the class is full, we know that the enrollment count and capacity have to match
        and are both 45. This implements that logic.
        """

        if potential_status == self.classFullRegex or potential_status == self.waitlistFullRegex:
            enrollment_dict["enrollment_count"] = enrollment_dict["enrollment_capacity"]

            


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
                "enrollment_count"   : int(match_dict["EnrolledCount"] or 0) if "EnrolledCount" in match_dict else None,
                "enrollment_over"    : int(match_dict["OverenrolledCount"] or 0) if "OverenrolledCount" in match_dict else None,
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


    def _parse_class(self, name_soup_pair):
        soup = name_soup_pair[1]
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

        class_dict =  {
            # "subject":  details_url_parts['subj_area_cd'].strip(),
            "class_no": details_url_parts['class_no'].strip(),
            "class_name": name_soup_pair[0],
            "term": self.term,
            "section_name": section_name,
            "days": days,
            "times": times,
            "locations": locations,
            "units": units,
            "url": details_url,
            "status": status, 

            "full_model": re.search("\((.*?)\)", soup.select_one("script").decode_contents())[1]
        }

        # if full_class_name:
        #     script = soup.select_one("script").decode_contents()
        #     token = re.search('"Token":"(.*?)"}',script)[1]
        #     subject = re.search('"SubjectAreaCode":"(.*?)"',script)[1].strip()
        #     with open('class_names.json') as fp:
        #         data = json.load(fp)["class_names"]
        #         class_dict["class_name"] = data[subject][token]

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
        model_choices = list(new_search_for_class_model(subject, catalog))

        # which model to choose? display choices to user, let them choose, then add to JSON
        htmls = []
        for name_model_pair in model_choices:
            # await ctx.channel.send(model)
            print(name_model_pair[1])
            htmls = htmls + self.check_class(name_model_pair)

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

            for key, name_soup_pair in htmls.items():
                # class_no assumption: the class_id is always the first 9 digits of the id of the first div in the GetCourseSummary html
                class_id = self.parse_class_id(str(name_soup_pair[1]))
                await self._generate_image(browser, class_id, ctx, key=key)

            await browser.close()

        else: # we're in fast mode
            for key, name_soup_pair in htmls.items():
                # await ctx.channel.send(f"Choice {key}: " + json.dumps(self._parse_class(class_html), indent=4))
                parsed_class = self._parse_class(name_soup_pair)
                await ctx.channel.send(embed=self._generate_embed(parsed_class), key=KeyboardInterrupt)


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
                a_file = open("classes_to_watch.json", "r")
                json_object = json.load(a_file)
                a_file.close()
            except (FileNotFoundError, json.JSONDecodeError):
                json_object = {"classes": []}

            #write lookup_info, which is the weird javascript thingy I've been getting the token from 
            lookup_info = re.search("\((.*?)\)", htmls[my_choice].select_one("script").decode_contents())[1]
            
            json_object["classes"].append(lookup_info)
            # TODO: warn about duplicates
            json_object["clases"] = list(set(json_object["classes"]))
            a_file = open("classes_to_watch.json", "w")
            json.dump(json_object, a_file)
            a_file.close()


    def parse_class_id(self, html):
        regex = '<div class="row-fluid data_row primary-row class-info class-not-checked" id="([\d]{9})_'
        match = re.search(regex, str(html))
        return match[1] if match else None
        

    def check_class(self, name_model_pair):
        name = name_model_pair[0]
        model = name_model_pair[1]
        FilterFlags = '{"enrollment_status":"O,W,C,X,T,S","advanced":"y","meet_days":"M,T,W,R,F","start_time":"8:00 am","end_time":"7:00 pm","meet_locations":null,"meet_units":null,"instructor":null,"class_career":null,"impacted":null,"enrollment_restrictions":null,"enforced_requisites":null,"individual_studies":null,"summer_session":null}'
                
        params = {'search_by':'subject','model':model, 'FilterFlags':FilterFlags, '_':'1571869764769'}
        
        headers = {"X-Requested-With": "XMLHttpRequest"}


        final_url = generate_url(self.GET_COURSE_SUMMARY_URL, params)
        print(final_url)
        r = requests.get(final_url, headers=headers)

        soup = BeautifulSoup(r.content, features="lxml")
        # print(soup)
        return [(name, html) for html in soup.select(".row-fluid.data_row.primary-row.class-info.class-not-checked")]
        # print(self._parse_class(soup))



    @commands.command(help="see classes you're keeping track of")
    async def see_classes(self, ctx, mode="fast"):
        try:
            a_file = open("classes_to_watch.json", "r")
            json_object = json.load(a_file)
            a_file.close()
        except (FileNotFoundError, json.JSONDecodeError):
            await ctx.channel.send("Looks like you don't have any classes kept track of, or the file got malformed.\nIf the file is malformed, try clearing it.")

        if mode == "fast":
            for my_class in json_object["classes"]:
                parsed_class = self._parse_class(BeautifulSoup(my_class, "lxml"))
                await ctx.channel.send(embed=self._generate_embed(parsed_class))

        else: # we're in the slow mode
            browser = await launch()

            for my_class in json_object["classes"]:
                # class_no assumption: the class_id is always the first 9 digits of the id of the first div in the GetCourseSummary html
                class_id = self.parse_class_id(str(my_class))
                self._generate_image(browser, class_id, ctx)
            await browser.close()






    @tasks.loop(minutes=1.0)
    async def slow_count(self, ctx):
        
        

        print(self.slow_count.current_loop)

    @slow_count.after_loop
    async def after_slow_count(self):
        print('done!')


    @commands.command(help="Count")
    async def start_the_count(self, ctx):
        self.slow_count.start(ctx)




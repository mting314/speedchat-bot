import discord
from discord.ext import commands, tasks
import random
import json
import urllib.parse as urlparse
from urllib.parse import urlencode
import requests
import re
from bs4 import BeautifulSoup


import asyncio
from pyppeteer import launch

from constants import *
from perms import *


# regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\(".*?%s",({"Term":"21W","SubjectAreaCode":"%s","CatalogNumber":"%s","IsRoot":true,"SessionGroup":"%%","ClassNumber":"\W*%s\W*","SequenceNumber":null,"Path":"[\d_]*?%s","MultiListedClassFlag":"n",.*?}\))'
# Assumptions: class number is always either 001,002, etc., or '%'
regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("[\d_]*?%s[\d]{0,3}",({"Term":"21W".*?"ClassNumber":" *?[\d%%]{1,3} *.*?"Path":"[\d_]*?%s[\d]{0,3}".*?"Token":".*?"})\);'
def generate_url(base_url, params):
    """Generate a URL given many parameters to attach as query strings"""
    url_parts = list(urlparse.urlparse(base_url))
    query = dict(urlparse.parse_qsl(url_parts[4]))
    query.update(params)

    url_parts[4] = urlencode(query)

    final_url = urlparse.urlunparse(url_parts).replace("%27", "%22")
    return final_url

def details_url(term, class_no):
    """Generate the class details url based on term and course number"""

def parse_catalog_no(catalog):
    match = re.match(r"([0-9]+)([a-zA-Z]+)", catalog, re.I)
    if match:
        return '{:>04s}'.format(match[1]) + match[2]
    else:
        return '{:>04s}'.format(catalog)

# TODO: Check subjects with spaces, i.e. COM SCI
def search_for_class_model(subject, catalog, lecture_no = None, term="21W"):
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
            # if lecture_no is None:
            #     raise Exception("Could not find class. Try searching with a certain lecture number.")
            # else:
            #     raise Exception("Could not find class, even with lecture number.")

        # real_regex = regex % (subject + better_catalog), subject.ljust(7), better_catalog.ljust(8), (f"00{str(lecture_no)}") if lecture_no else '%', subject + better_catalog)
        real_regex = regex % (subject + better_catalog, subject + better_catalog)
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
        self.classOpenRegex    = re.compile('Open(\d+) of (\d+) Enrolled(\d+) Spots? Left')
        self.waitlistOnlyRegex = re.compile('^Waitlist$')
        self.waitlistFullRegex = re.compile('^WaitlistClass Full \((?P<Capacity>\d+)\)(, Over Enrolled By (?P<OverenrolledCount>\d+))?')
        # Waitlist regexes
        self.waitlistOpenRegex   = re.compile('(?P<WaitlistCount>\d+) of (?P<WaitlistCapacity>\d+) Taken')
        self.noWaitlistRegex     = re.compile('No Waitlist')
        self.waitlistClosedRegex = re.compile('Waitlist Full \((?P<WaitlistCapacity>\d+)\)')



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


    def _parse_class(self, soup):
        status = soup.select_one("div[id$=-status_data]").text
        # TODO: Multiple locations!
        locations = soup.select_one("div[id$=-location_data]").text
        days = []
        times = []

        # I hope it always looks lile <div id="blah-units_data"><p> # of units </p></div>
        # could be wrong...
        units = soup.select_one("div[id$=-units_data] p").text

        class_dict =  {
            "section_id": "123",
            "term": "21W",
            "days": days,
            "times": times,
            "locations": locations,
            "units": units,
            "url": "google.com"
        }

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
    async def searchclass(self, ctx, subject: str, catalog: str, lecture_no: int):
        model_choices = search_for_class_model(subject, catalog, lecture_no=lecture_no)

        # which model to choose? display choices to user, let them choose, then add to JSON
        htmls = []
        for model in model_choices:
            # await ctx.channel.send(model)
            print(model)
            htmls = htmls + self.check_class(model)

        print(htmls)


        
        




        # browser = await launch()
        # page = await browser.newPage()
        # url = self._getURL(subject)
        # if url is None:
        #     await ctx.send("Couldn't find that subject!")
        #     return

        # print(url)
        # await page.goto(url)
        # await page.click('#expandAll')
        # # I think there might be a way to pass in js code that'll do this without having 
        # # to wait this fixed time
        # await page.waitFor(5000)
        # courses_containers = await page.querySelectorAll('.primarySection')

        # # courses = []
        # # for container in courses_containers:
        # #     courses.append(await page.evaluate('''el => {
        # #         const id =  el.getAttribute('id');
        # #         const fullCourse = id.match(/[A-Z]+\d+[A-Z]*\d*/)[0];
        # #         const course = fullCourse.substring(fullCourse.indexOf('0'));
        # #         const container = document.querySelector('[id$='${course}-children']')
        # #         const rows = container.querySelectorAll('.data_row')
        # #         return rows;
        # #     }''', container))

        # courses = []
        # for container in courses_containers:
        #     courses.append(await page.evaluate('''el => {
        #         const id =  el.getAttribute('id');
        #         const fullCourse = id.match(/[A-Z]+\d+[A-Z]*\d*/)[0];
        #         return fullCourse.substring(fullCourse.indexOf('0'));
        #     }''', container))

        # oof = []
        # for course in courses:
        #     benis = await page.querySelector(f"[id$='{course}-children']")
        #     # asdf = await page.evaluate('(benis) => benis.textContent', benis)
        #     rows = await benis.querySelectorAll('.data_row')
        #     for section in rows:
        #         # lectureNumber = 
        #         realLectureNumber = await page.evaluate('(lectureNumber) => lectureNumber.textContent', await section.querySelector('.sectionColumn p'))
        #         oof.append(realLectureNumber)
        #     # oof.append(asdf2)


        # print(oof)



        # await browser.close()

        # await status.edit(content="Aborted.", delete_after=TMPMSG_DEFAULT)

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




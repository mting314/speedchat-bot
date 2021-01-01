import discord
from discord.ext import commands
import random
import json
import urllib.parse as urlparse
from urllib.parse import urlencode
import requests
import re

import asyncio
from pyppeteer import launch

from constants import *
from perms import *


regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("%s",({"Term":"20W","SubjectAreaCode":"%s","CatalogNumber":"%s","IsRoot":true,"SessionGroup":"%%","ClassNumber":"\W*%s\W*","SequenceNumber":null,"Path":"%s","MultiListedClassFlag":"n",.*?})'

def parse_catalog_no(catalog):
    match = re.match(r"([0-9]+)([a-zA-Z]+)", catalog, re.I)
    if match:
        return '{:>04s}'.format(match[1]) + match[2]
    else:
        return '{:>04s}'.format(catalog)

# TODO: Check subjects with spaces, i.e. COM SCI
def search_for_class_model(subject, catalog, class_no = None):
    """Model?"""
    better_catalog = parse_catalog_no(catalog)


    headers = {"X-Requested-With": "XMLHttpRequest"}
    pageNumber = 1
    while True:
        url = f'https://sa.ucla.edu/ro/Public/SOC/Results/CourseTitlesView?search_by=subject&model=%7B%22subj_area_cd%22%3A%22{subject}%22%2C%22search_by%22%3A%22Subject%22%2C%22term_cd%22%3A%2220W%22%2C%22SubjectAreaName%22%3A%22Mathematics+(MATH)%22%2C%22CrsCatlgName%22%3A%22Enter+a+Catalog+Number+or+Class+Title+(Optional)%22%2C%22ActiveEnrollmentFlag%22%3A%22n%22%2C%22HasData%22%3A%22True%22%7D&pageNumber={pageNumber}&filterFlags=%7B%22enrollment_status%22%3A%22O%2CW%2CC%2CX%2CT%2CS%22%2C%22advanced%22%3A%22y%22%2C%22meet_days%22%3A%22M%2CT%2CW%2CR%2CF%22%2C%22start_time%22%3A%228%3A00+am%22%2C%22end_time%22%3A%227%3A00+pm%22%2C%22meet_locations%22%3Anull%2C%22meet_units%22%3Anull%2C%22instructor%22%3Anull%2C%22class_career%22%3Anull%2C%22impacted%22%3Anull%2C%22enrollment_restrictions%22%3Anull%2C%22enforced_requisites%22%3Anull%2C%22individual_studies%22%3Anull%2C%22summer_session%22%3Anull%7D'
        r = requests.get(url, headers=headers)
        if r.content == b'':
            if class_no is None:
                raise Exception("Could not find class. Try searching with a certain section number.")
            else:
                raise Exception("Could not find class, even with section number.")

        real_regex = regex % (subject + better_catalog + (f"00{str(class_no)}" if class_no else ''), subject.ljust(7), better_catalog.ljust(8), (f"00{str(class_no)}") if class_no else '%', subject + better_catalog + (f"00{str(class_no)}" if class_no else ''))
        # print(real_regex)
        found = re.search(real_regex, str(r.content))
        if not found:
            pageNumber += 1
            continue
        else:
            return found[1]

# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        f = open('speedchat_bot/ucla/subjects.json') 
        self.subjectsJSON = json.load(f)
        # self.class_regex = 'Iwe_ClassSearch_SearchResults.AddToCourseData\("%s",({"Term":"20W","SubjectAreaCode":"%s","CatalogNumber":"%s","IsRoot":true,"SessionGroup":"%%","ClassNumber":"\W*%s\W*","SequenceNumber":null,"Path":"%s","MultiListedClassFlag":"n",.*?})'
            
    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def searchclass(self, ctx, subject: str, catalog: str):
        model = search_for_class_model(subject, catalog)

        FilterFlags = '{"enrollment_status":"O,W,C,X,T,S","advanced":"y","meet_days":"M,T,W,R,F","start_time":"8:00 am","end_time":"7:00 pm","meet_locations":null,"meet_units":null,"instructor":null,"class_career":null,"impacted":null,"enrollment_restrictions":null,"enforced_requisites":null,"individual_studies":null,"summer_session":null}'
                
        params = {'search_by':'subject','model':model, 'FilterFlags':FilterFlags, '_':'1571869764769'}

        url = "https://sa.ucla.edu/ro/Public/SOC/Results/GetCourseSummary"
        headers = {"X-Requested-With": "XMLHttpRequest"}
        url_parts = list(urlparse.urlparse(url))
        query = dict(urlparse.parse_qsl(url_parts[4]))
        query.update(params)

        url_parts[4] = urlencode(query)

        final_url = urlparse.urlunparse(url_parts).replace("%27", "%22")
        print(final_url)
        r = requests.get(final_url, headers=headers)
        print(r.content)




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
        # #         const container = document.querySelector(`[id$='${course}-children']`)
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

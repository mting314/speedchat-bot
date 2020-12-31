import discord
from discord.ext import commands
import random
import json
import urllib

import asyncio
from pyppeteer import launch

from constants import *
from perms import *


# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        f = open('speedchat_bot/subjects.json') 
        self.subjectsJSON = json.load(f)

    def _getURL(self, subject):
        # if we can find it in the list of subjects
        if subject in [pair['value'] for pair in self.subjectsJSON]:
            formattedCode = urllib.parse.quote(subject).replace('%20', '+')
            return f'https://sa.ucla.edu/ro/Public/SOC/Results?t=19F&sBy=subject&subj={formattedCode}'
        else:
            return None
            
    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def searchclass(self, ctx, subject: str):
        status = await ctx.send(f"Searching for {subject}.")

        browser = await launch()
        page = await browser.newPage()
        url = self._getURL(subject)
        if url is None:
            await ctx.send("Couldn't find that subject!")
            return

        print(url)
        await page.goto(url)
        await page.click('#expandAll')
        # I think there might be a way to pass in js code that'll do this without having 
        # to wait this fixed time
        await page.waitFor(5000)
        data = await page.evaluate('''() => {
            courses = document.querySelectorAll('.primarySection')
            return Array.from(courses).map(rawSection => {
                const id =  rawSection.getAttribute('id');
                const fullCourse = id.match(/[A-Z]+\d+[A-Z]*\d*/)[0];
                const course = fullCourse.substring(fullCourse.indexOf('0'));
                return course;
          })
        }''')

        print(data)

        await browser.close()

        # await status.edit(content="Aborted.", delete_after=TMPMSG_DEFAULT)

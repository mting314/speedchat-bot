import discord
from discord.ext import commands
import random

from constants import *
from perms import *
from jisho import jisho


# Commands for looking up UCLA classes
class UCLA(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.j = jisho.Jisho()

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def getclass(self, ctx, *, kanji: str, meaning_num: int = 0):
        status = await ctx.send(f"Searching for {kanji}.")
        try:
            response_message = self.j.get_stroke_order(kanji)
        except TypeError:
            response_message = "Sorry, I could not find that."
            await status.edit(content=response_message)
            return

        await status.edit(content=response_message)


    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def benis(self, ctx, english: str, def_num: int = None,  meaning_num: int = 0, ):
        status = await ctx.send(f"Searching for {english}.")
        # try:
        response_message = self._generate_message(self.j.esearch(english), meaning_num=meaning_num)
        # except TypeError as e:
        #     print(e)
        #     await status.edit(content="Sorry, I could not find that.")
        #     return

        await status.edit(content=response_message)
        while True:
            await status.add_reaction(LEFT_EMOJI)
            await status.add_reaction(RIGHT_EMOJI)

            r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: u == ctx.author)
            #
            # await status.edit(content=self._get_meaning(hira, meaning_num+(1 if r.emoji == RIGHT_EMOJI else -1)))

        await status.edit(content="Aborted.", delete_after=TMPMSG_DEFAULT)

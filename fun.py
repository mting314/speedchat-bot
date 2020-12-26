import discord
from discord.ext import commands
import random

from constants import *
from perms import *
from jisho import jisho


# Chaos
class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.j = jisho.Jisho()

    def _generate_message(self, search_response, meaning_num=0, def_number=2):
        response_message = ""

        entry = search_response[meaning_num]
        jword = entry['japanese'][0]['word']  # 0 is primary reading
        reading = entry['japanese'][0]['reading']
        url = self.j.JISHO_NORMAL_URL + jword

        response_message += f"{jword}({reading}) {url}"

        for n, sense in enumerate(entry['senses']):
            if n == (def_number - 1):
                response_message += f"\n{n + 1}. " + ', '.join(sense['english_definitions'])

        return response_message

    def _get_meaning(self, hira, meaning_num=0):
        response = self.j.jsearch(hira)
        primary_meaning = response[meaning_num]
        response_message = hira + f"({primary_meaning['furigana']})"
        for n, meaning in enumerate(primary_meaning['meanings'].values()):
            response_message += f"\n{n + 1}. " + meaning

        response_message += "\n\nWas this the meaning you were looking for? If not, use arrows to move to a different one."
        return response_message

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def stroke(self, ctx, *, kanji: str, meaning_num: int = 0):
        status = await ctx.send(f"Searching for {kanji}.")
        try:
            stroke_gifs = self.j.get_stroke_order(kanji)
            for gif in stroke_gifs:
                # embed = discord.Embed()
                # embed.set_image(url=gif)
                # await ctx.send(embed=embed)

                await ctx.send(content=gif)

        except TypeError:
            response_message = "Sorry, I could not find that."
            await status.edit(content=response_message)
        return

        # await status.edit(content=response_message)

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def benis(self, ctx, english: str, def_num: int = None, meaning_num: int = 0, ):
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

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def search(self, ctx, kanji: str):
        status = await ctx.send(f"Searching for {kanji}.")
        # try:
        response_message = self.j.searchForKanji(kanji)
        # except TypeError as e:
        #     print(e)
        #     await status.edit(content="Sorry, I could not find that.")
        #     return

        await status.edit(content=response_message)

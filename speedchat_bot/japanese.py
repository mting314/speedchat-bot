import discord
from discord.ext import commands
import random

from constants import *
from perms import *
from jisho import jisho

import json # temporarily

class Japanese(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.j = jisho.Jisho()

    @commands.command(help="Display useful info for a word")
    async def search(self, ctx, kanji: str):
        status = await ctx.send(f"Searching for {kanji}")
        response_message = ""
        try:
            result = self.j.searchForPhrase(kanji)

            entry = result['data'][0]
            jword = entry['japanese'][0]['word']
            reading = entry['japanese'][0]['reading']
            # url = result['uri']

            # response_message += f'{jword}({reading}) {url}'
            response_message += f'{jword}({reading})'

            for index, sense in enumerate(entry['senses']):
                response_message += f'\n{index + 1}. ' + ', '.join(sense['english_definitions'])
        except TypeError as e:
            print(e)
            await status.edit(content="Sorry, I could not find that.")
            return

        await status.edit(content=response_message)

    @commands.command(help="Look up the stroke order for a word")
    async def stroke(self, ctx, word: str):
        status = await ctx.send(f"Searching for {word}'s stroke order.")
        try:
            for kanji in word:
                await ctx.send(self.j.searchForKanji(kanji)['strokeOrderGifUri'])
        except TypeError as e:
            print(e)
            await status.edit(content="Sorry, I could not find that.")
            return

        # await status.edit(content=response_message)


    @commands.command(help="Test again real")
    async def test(self, ctx, kanji: str):
        await ctx.send(f"Mine:")
        status = await ctx.send(f"Searching for {kanji}.")
        # try:
        result = self.j.searchForKanji(kanji)
        # for benis in result:
        await ctx.send(str(result)[:1999])
        # response_message = json.dumps(self.j.searchForWord(kanji), indent=4)[:1999]
        # response_message2 = json.dumps(self.j.searchForWord(kanji), indent=4)[1999:3999]
        # except TypeError as e:
        #     print(e)
        #     await status.edit(content="Sorry, I could not find that.")
        #     return

        # await status.edit(content=response_message)
        # await ctx.send(response_message2)
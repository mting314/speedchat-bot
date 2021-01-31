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
    async def jsearch(self, ctx, kanji: str):
        status = await ctx.send(f"Searching for {kanji}")
        response_message = ""
        try:
            result = self.j.search_for_phrase(kanji)

            entry = result['data'][0]
            jword = entry['japanese'][0]['word']
            reading = entry['japanese'][0]['reading']

            response_message += f'{jword}({reading})'

            for index, sense in enumerate(entry['senses']):
                response_message += f'\n{index + 1}. ' + ', '.join(sense['english_definitions'])
        except (TypeError, KeyError) as e:
            print(e)
            await status.edit(content="Sorry, I could not find that.")
            return

        await status.edit(content=response_message)

    @commands.command(help="Look up the stroke order for a word")
    async def stroke(self, ctx, word: str):
        status = await ctx.send(f"Searching for {word}'s stroke order.")
        sent = False

        # If we looked up hepburn
        if word.isalpha():
            result = self.j.search_for_phrase(word)
            entry = result['data'][0]
            search_value = entry['japanese'][0]['word']
        else:
            search_value = word

        for kanji in search_value:
            kanji_result = self.j.search_for_kanji(kanji)
            if 'strokeOrderGifUri' in kanji_result:
                await ctx.send(kanji_result['strokeOrderGifUri'])
                sent = True


        if not sent:
            await status.edit("Sorry, I couldn't find that.")

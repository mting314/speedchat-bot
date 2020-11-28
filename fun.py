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

    # shuffle users among a category of voice channels
    # TODO: opt-in shuffle
    @commands.command(help="Shuffle users about a category")
    @is_admin()
    async def shuf(self, ctx, *, chan: discord.CategoryChannel):
        status = await ctx.send(f"Okay, I'll shuffle users amongst {chan.name}.")
        random.seed()
        while True:
            await status.edit(content="Waiting for your reaction...")
            await status.add_reaction(OK_EMOJI)
            await status.add_reaction(NO_EMOJI)
            r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: u == ctx.author)
            if r.emoji == NO_EMOJI:
                break

            await status.edit(content="Shuffling...")

            # shuffle the lads
            for m in [m for c in chan.voice_channels for m in c.members]:
                await m.move_to(random.choice(chan.voice_channels))

            await status.edit(content="Shuffled!")
            await status.clear_reaction(OK_EMOJI)
        await status.edit(content="Aborted.", delete_after=TMPMSG_DEFAULT)

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
            response_message = self.j.get_stroke_order(kanji)
        except TypeError:
            response_message = "Sorry, I could not find that."
            await status.edit(content=response_message)
            return

        await status.edit(content=response_message)



    async def oof(self, ctx, *, hira: str, meaning_num: int = 0):
        status = await ctx.send(f"Searching for {hira}.")
        try:
            response_message = self._get_meaning(hira, meaning_num)
        except TypeError:
            response_message = "Sorry, I could not find that."
            await status.edit(content=response_message)
            return

        await status.edit(content=response_message)
        while True:
            await status.add_reaction(LEFT_EMOJI)
            await status.add_reaction(RIGHT_EMOJI)

            r, _ = await self.bot.wait_for("reaction_add", check=lambda r, u: u == ctx.author)

            await status.edit(content=self._get_meaning(hira, meaning_num+(1 if r.emoji == RIGHT_EMOJI else -1)))

        await status.edit(content="Aborted.", delete_after=TMPMSG_DEFAULT)

import discord
from discord.ext import commands
import random
import json

from speedchat_bot.constants import *
from speedchat_bot.perms import *

# Commands for Speedchat
class Speedchat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    @is_admin()
    async def speedchat(self, ctx):
        with open('speedchat.json') as fp:
            data = json.load(fp)
            random_index = random.randint(0, len(data)-1)
            await ctx.send(data[random_index])
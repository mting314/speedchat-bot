import discord
from discord.ext import commands
import random
import json

from constants import *
from perms import *

# Commands for Speedchat
class Speedchat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(help="Look up a stroke order for a SINGLE kanji")
    async def speedchat(self, ctx):
        with open('speedchat_bot/speedchat/speedchat.json') as fp:
            data = json.load(fp)
            message = random.choice(list(data.values()))
            await ctx.send(f'Speedchat:"{message}"')
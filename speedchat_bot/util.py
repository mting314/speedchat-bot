import re
import asyncio
import typing
import discord
from discord.ext import commands

from constants import *
from perms import *


# General server maintenance.
class Util(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # one-time use invite
    @commands.command(help="Generate a one-time use invite to the system messages channel")
    @is_owner()
    async def otp(self, ctx, channel: typing.Optional[discord.TextChannel], *, reason: typing.Optional[str]):
        status = await ctx.send(f"Creating an invite for you...")
        invite = await (channel or ctx.guild.system_channel).create_invite(max_age=0, max_uses=1,
                                                                           reason=reason or f"{ctx.author} asked for a one-time-use invite.")
        await status.edit(content=f"{ctx.author.mention} asked for a one-time-use invite:\n\n{invite.url}")
        await ctx.message.delete()

    # destroy an invite
    @commands.command(help="Destroy an invite")
    @is_owner()
    async def rmotp(self, ctx, inv: discord.Invite, *, reason: typing.Optional[str]):
        status = await ctx.send(f"Deleting invite id {inv.id}")
        await inv.delete()
        await ctx.message.delete(delay=TMPMSG_DEFAULT)
        await status.edit(content=f"{ctx.author.mention} deleted invite **{inv.id}**.", delete_after=TMPMSG_DEFAULT)

    # count messages
    @commands.command(help="Count messages matching a regex")
    async def count(self, ctx, chan: typing.Optional[discord.TextChannel], *, pattern: typing.Optional[str]):
        status = await ctx.send(f"Counting messages in {chan or ctx.channel} matching pattern `{pattern}`...")
        count = 0
        async for m in (chan or ctx).history(limit=5000):
            if re.search(pattern or ".*", m.content):
                count += 1
        await status.edit(content=f"Found {count} messages matching your query.")

    # count messages
    @commands.command(help="Count messages matching a regex")
    async def help_commands(self, ctx):
        """Build a Discord Embed message to show all commands"""

        #TODO: Split this into help for each command?

        title = 'Welcome to Toontown!'

        embedVar = discord.Embed(title=title)
        embedVar.add_field(name="Overview", value="Allows you to easily look up UCLA classes by name and term. You can also add as many classes as you want to a **watchlist**, where you'll be DM'ed by this bot every time the enrollment status of a class listed there changes.", inline=False)
        embedVar.add_field(name="~display_class", value="```\n~display_class MATH 131A --term 21W --mode fast``` Displays all offerings of a class with that name along with lots of helpful info about it (meeting times, professor, enrollment numbers, etc.) Make sure to use the subject name abbreviation as it appears on the Class Planner, i.e. MATH or COM SCI or C&S BIO. Term is in the format 20F/21W/21S.\nMode can be `fast` or `slow`. The order in which you provide term and mode doesn't matter.", inline=False)
        embedVar.add_field(name="~subject", value="```\n~subject JAPAN [--term] [--mode]``` Displays *all* classes under provided subject. Will ask you if you want to display classes above 300s because those classes are weird.", inline=False)
        
        embedVar.add_field(name="~search_class", value="```\n~search_class COM SCI 35L [--term] [--mode]``` Same usage and mostly same appearance as `display_class`. However, at the end, you will be presented with choice reaction emojis. Choose a reaction to have the corresponding class added to your watchlist.", inline=False)
        embedVar.add_field(name="~see_classes", value="```\n~see_classes``` Displays all classes in your (message author's) watchlist.", inline=False)
        embedVar.add_field(name="~remove_class", value="```\n~remove_classes``` Displays all classes in your (message author's) watchlist, and then presents similar reaction choices to `search_class`. Choose the appropriate reaction to remove that class from your watchlist.", inline=False)
        embedVar.add_field(name="~clear_classes", value="```\n~remove_classes``` Removes all classes from your (message author's) watchlist.", inline=False)
        # TODO: upload image to pic serves to use here, can use local file
        # embedVar.set_image(url="https://discordapp.com/assets/e4923594e694a21542a489471ecffa50.svg")
        
        
        await ctx.send(embed=embedVar)

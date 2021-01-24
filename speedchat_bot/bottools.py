import typing
import discord
from discord.ext import commands

# from speedchat_bot import constants, perms

from constants import *
from perms import *


# Bot admin and features
class BotTools(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    # set bot status
    @commands.command(help="Set the bot status")
    @is_owner()
    async def status(self, ctx, *, status: str):
        await self.bot.change_presence(status=discord.Status.online, activity=discord.Game(name=status))
        await ctx.send("Updated status.", delete_after=TMPMSG_DEFAULT)

    # say something
    @commands.command(help="Say something on your behalf")
    @is_owner()
    async def say(self, ctx, chan: typing.Optional[discord.TextChannel], user: typing.Optional[discord.User], *,
                  contents: str):
        if chan:
            await chan.send(contents)
        elif user == self.bot.user:
            await ctx.send(f"I can't send a DM to myself, silly.", delete_after=TMPMSG_DEFAULT)
        elif user:
            try:
                await user.send(contents)
            except AttributeError:
                await ctx.send(f"I couldn't send the DM to the user, sorry. (つ﹏<)･ﾟ｡", delete_after=TMPMSG_DEFAULT)
        else:
            await ctx.send(contents)

    # keep a conversation
    @commands.command(help="Start a conversation with someone on behalf of the bot")
    @is_owner()
    async def convo(self, ctx, user: typing.Optional[discord.User], *, initial_msg: str):
        portal = await ctx.send("```\nOpening the portal...\n```")
        msg = [m.content async for m in (user.dm_channel or await user.create_dm()).history()]
        await portal.edit(content=f"Got some messages: {msg}", delete_after=TMPMSG_DEFAULT)

    # count messages
    @commands.command(help="Count messages matching a regex")
    async def about(self, ctx):
        """Build a Discord Embed message to introduce """

        #TODO: Split this into help for each command?

        title = 'Welcome to Toontown!'

        embedVar = discord.Embed(title=title)



        embedVar.add_field(name="Overview", value="Allows you to easily look up UCLA classes by name and term. You can also add as many classes as you want to a **watchlist**, where you'll be DM'ed by this bot every time the enrollment status of a class listed there changes.", inline=False)
        embedVar.add_field(name="~display_class", value="```\n~display_class MATH 131A --term 21W --mode fast``` Displays all offerings of a class with that name along with lots of helpful info about it (meeting times, professor, enrollment numbers, etc.) Make sure to use the subject name abbreviation as it appears on the Class Planner, i.e. MATH or COM SCI or C&S BIO. Term is in the format 20F/21W/21S.\nMode can be `fast` or `slow`. The order in which you provide term and mode doesn't matter.", inline=False)
        embedVar.add_field(name="~subject", value="```\n~subject JAPAN [--term] [--mode]``` Displays *all* classes under provided subject. Will ask you if you want to display classes above 300s because those classes are weird.", inline=False)
        
        embedVar.add_field(name="~search_class", value="```\n~search_class COM SCI 35L [--term] [--mode]``` Same usage and mostly same appearance as `display_class`. However, at the end, you will be presented with choice reaction emojis. Choose a reaction to have the corresponding class added to your watchlist.", inline=False)
        embedVar.add_field(name="~see_watchlist", value="```\n~see_watchlist``` Displays all classes in your (message author's) watchlist.", inline=False)
        embedVar.add_field(name="~remove_class", value="```\n~remove_classes``` Displays all classes in your (message author's) watchlist, and then presents similar reaction choices to `search_class`. Choose the appropriate reaction to remove that class from your watchlist.", inline=False)
        embedVar.add_field(name="~clear_classes", value="```\n~remove_classes``` Removes all classes from your (message author's) watchlist.", inline=False)
        # TODO: upload image to pic serves to use here, can use local file
        # embedVar.set_image(url="https://discordapp.com/assets/e4923594e694a21542a489471ecffa50.svg")
        
        
        await ctx.send(embed=embedVar)
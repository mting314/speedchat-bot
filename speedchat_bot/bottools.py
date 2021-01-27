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



        embedVar.add_field(name="Overview", value="Allows you to easily look up UCLA classes by name and term. You can also add as many classes as you want to a **watchlist**, where you'll be DM'ed by this bot every time the enrollment status of a class listed there changes.\n\nTry running the follow example functions.", inline=False)
        
        
        embedVar.add_field(name="~display_class", value="```\n~display_class COM SCI 35L```", inline=False)
        embedVar.add_field(name="~subject",       value="```\n~subject JAPAN --term 20F```", inline=False)
        embedVar.add_field(name="~search_class",  value="```\n~search_class Math 142 --term 21S```", inline=False)
        
        # this forces next fields onto new line
        # embedVar.add_field(name = chr(173), value = chr(173))

        embedVar.add_field(name="~see_watchlist", value="```\n~see_watchlist```", inline=False)
        embedVar.add_field(name="~remove_class",  value="```\n~remove_classes```", inline=True)
        embedVar.add_field(name="~clear_classes", value="```\n~clear_classes```", inline=True)
        embedVar.add_field(name="Help!", value="You can always run `~help` for an overview of every command available, and `~help commandname` for more detailed info on a particular command.", inline=False)
        # TODO: upload image to pic serves to use here, can use local file
        embedVar.set_image(url="https://raw.githubusercontent.com/mting314/speedchat-bot/main/images/search.png?token=ANTHQXQUF7ML5QV2BTMNNP3ACHLSU")
        embedVar.set_footer(text="Bottom Text. You can message me at coolguy5530#7055 if you are stuck or find issues.")
        
        await ctx.send(embed=embedVar)
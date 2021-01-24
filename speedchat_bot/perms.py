import os
from discord.ext import commands


# ...but are you me?
def is_owner():
    return commands.check(lambda ctx: str(ctx.author) == os.getenv('OWNER'))

# check if this is first time user interacting with bot
def first_time():
    async def predicate(ctx):
        if not ctx.author.dm_channel:
            channel = await ctx.author.create_dm()
            messages = await channel.history().flatten()
            if not any([(message.content.startswith("Hi, thanks for using this bot") and message.author.bot) for message in messages]):
                await ctx.author.send("Hi, thanks for using this bot! Just so you know, you can also perform all the same commands in this DM channel, if you don't want to spam other people in a server.")
        return True
    return commands.check(predicate)

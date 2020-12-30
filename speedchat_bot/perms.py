import os
from discord.ext import commands


# you may be an admin...
def is_admin():
    return commands.check(lambda ctx: [role for role in ctx.author.roles if role.permissions.administrator])


# ...but are you me?
def is_owner():
    return commands.check(lambda ctx: str(ctx.author) == os.getenv('OWNER'))

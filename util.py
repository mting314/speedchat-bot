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
    @is_leo()
    async def otp(self, ctx, channel: typing.Optional[discord.TextChannel], *, reason: typing.Optional[str]):
        status = await ctx.send(f"Creating an invite for you...")
        invite = await (channel or ctx.guild.system_channel).create_invite(max_age=0, max_uses=1,
                                                                           reason=reason or f"{ctx.author} asked for a one-time-use invite.")
        await status.edit(content=f"{ctx.author.mention} asked for a one-time-use invite:\n\n{invite.url}")
        await ctx.message.delete()

    # destroy an invite
    @commands.command(help="Destroy an invite")
    @is_leo()
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

    # list all users in a role
    @commands.command(help="List all the users with a given (set of) role(s)")
    async def lsrole(self, ctx, *, pattern: str):
        status = await ctx.send(f"Gathering users")
        users = []
        for u in ctx.guild.members:
            for r in u.roles:
                if r.guild == ctx.guild and re.match(pattern, r.name):
                    users.append(f"{u.name}#{u.discriminator}")
                    break
        found = len(users)
        idx = 0
        print(found)

        while True:
            print(idx)
            preview = '\n'.join(users[idx:idx + 10])
            await status.edit(content=f"Here's entries {idx} through {idx + 10}:\n{preview}")
            await status.add_reaction("⬅️")
            await status.add_reaction("➡️")
            try:
                r, _ = await self.bot.wait_for("reaction_add",
                                               check=lambda r, u: u == ctx.author and r.message.id == status.id,
                                               timeout=TMPMSG_DEFAULT)
            except asyncio.TimeoutError:
                break
            else:
                if r.emoji == "⬅️":
                    idx -= 10
                if r.emoji == "➡️":
                    idx += 10
                if idx >= found or idx <= 0:
                    idx = 0
                await status.clear_reaction("⬅️")
                await status.clear_reaction("➡️")

    # bulk deletion tool
    @commands.command(name="d", help="Delete messages")
    @is_admin()
    async def delete(self, ctx, *args):
        status = await ctx.send("Standby...")

        channels = [ctx.channel]
        before = None
        after = None

        while True:
            msg = "Welcome to the bulk-deletion tool.\n"
            if channels != [ctx.channel]:
                msg += f"Channels: {[c.name for c in channels]}\n"
            if before:
                msg += f"Before: {before}\n"
            if after:
                msg += f"After: {after}\n"
            msg += f"React with {OK_EMOJI} to execute, {NO_EMOJI} to cancel.\n"

            await status.edit(content=msg)
            await status.add_reaction(NO_EMOJI)
            await status.add_reaction(OK_EMOJI)

            try:
                r, _ = await self.bot.wait_for("reaction_add",
                                               timeout=TMPMSG_DEFAULT,
                                               check=lambda r, u: u == ctx.author and r.emoji in INPUT)
            except asyncio.TimeoutError:
                await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                return
            else:
                if r.emoji == OK_EMOJI:
                    await status.edit(content="Starting deletion...")
                    break
                if r.emoji == NO_EMOJI:
                    await status.edit(content="Aborted!", delete_after=TMPMSG_DEFAULT)
                    return

        for c in channels:
            await status.edit(content=f"Deleting messages found in {c.name}")

            history = [m async for m in c.history(limit=MSG_LIMIT) if m.id != status.id]
            tasks = [asyncio.gather(*[m.delete() for m in history[i:i + 100]]) for i in range(0, len(history), 100)]
            count = len(tasks)

            await status.edit(content=f"Found {count} batches of ~100 messages. Executing.")
            for i, t in enumerate(tasks):
                await t
                await status.edit(content=f"Completed batch {i + 1}/{count}.")

            await status.edit(content=f"Done.")

        await status.edit(content="Transaction completed successfully.", delete_after=TMPMSG_DEFAULT)

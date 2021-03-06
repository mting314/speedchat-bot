#! env/bin/python
#
# speedchat-bot
#

import logging
import os
import random
import socket

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bottools import BotTools
from japanese import Japanese
from speedchat.speedchat import Speedchat
from ucla.ucla import UCLA

from constants import *

# import logging

# logging.basicConfig(filename='log/example.log', level=logging.DEBUG, format='%(asctime)s %(message)s', datefmt='%m/%d/%Y %I:%M:%S %p')

load_dotenv()

random.seed()

logging.basicConfig(level=logging.INFO)
intents = discord.Intents(messages=True, members=True, guilds=True)
cli = commands.Bot(command_prefix=CMD_PREFIX, intents=intents)


@cli.event
async def on_ready():
    logging.info(cli)
    logging.info(f"Successfully logged in as {cli.user}.")
    print(f"Successfully logged in as {cli.user}.")
    await cli.change_presence(status=discord.Status.online, activity=discord.Game("Updating"))


# cog setup
my_bottools = BotTools(cli)
cli.add_cog(my_bottools)
cli.add_cog(Japanese(cli))
cli.add_cog(Speedchat(cli))
cli.add_cog(UCLA(cli))

@cli.event
async def on_guild_join(guild):
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(embed=my_bottools.about_message())
        break

if __name__ == "__main__":
    # bind for Heroku
    port = int(os.environ.get("PORT") or 8080)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("", port))
    sock.listen(1)
    # log.info(f"Bound to port {port}")

    try:
        cli.run(os.environ.get("TOKEN"))
    except AttributeError as e:
        # log.error("An environment variable is not set.")
        print("An environment variable is not set.")

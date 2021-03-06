from .utils import config
from .utils import checks
from discord.ext import commands
import discord

import aiohttp

base_url = "https://api.owapi.net/api/v2/u/"
# This is a list of the possible things that we may want to retrieve from the stats
# The API returns something if it exists, and leaves it out of the data returned entirely if it does not
# For example if you have not win with a character, wins will not exist in the list
# This sets an easy way to use list comprehension later, to print all possible things we want, if it exists
check_g_stats = ["eliminations", "deaths", 'kpd', 'wins', 'losses', 'time_played',
                 'cards', 'damage_done', 'healing_done', 'multikills']
check_o_stats = ['wins', 'losses']


class Overwatch:
    """Class for viewing Overwatch stats"""

    def __init__(self, bot):
        self.bot = bot
        self.headers = {"User-Agent": "Bonfire/1.0.0"}
        self.session = aiohttp.ClientSession()

    @commands.group(no_pm=True)
    async def ow(self):
        """Command used to lookup information on your own user, or on another's
        When adding your battletag, it is quite picky, use the exact format user#xxxx
        Multiple names with the same username can be used, this is why the numbers are needed
        Capitalization also matters"""
        pass

    @ow.command(name="stats", pass_context=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def ow_stats(self, ctx, user: discord.Member = None, hero: str = ""):
        """Prints out a basic overview of a member's stats
        Provide a hero after the member to get stats for that specific hero"""
        if user is None:
            user = ctx.message.author

        ow_stats = await config.get_content('overwatch')
        bt = ow_stats.get(user.id)

        if bt is None:
            await self.bot.say("I do not have this user's battletag saved!")
            return
        # This API sometimes takes a while to look up information, so send a message saying we're processing
        await self.bot.say("Searching profile information....")

        if hero == "":
            # If no hero was provided, we just want the base stats for a player
            async with self.session.get(base_url + "{}/stats/general".format(bt), headers=self.headers) as r:
                data = await r.json()

            # Here is our list comprehension to get what kind of data we want.
            fmt = "\n".join("{}: {}".format(i, r) for i, r in data['game_stats'].items() if i in check_g_stats)
            fmt += "\n"
            fmt += "\n".join("{}: {}".format(i, r) for i, r in data['overall_stats'].items() if i in check_o_stats)
            # title and replace are used to format things nicely
            # while not having to have information for every piece of data
            await self.bot.say(
                "Overwatch stats for {}: ```py\n{}```".format(user.name, fmt.title().replace("_", " ")))
        else:
            # If there was a hero provided, search for a user's data on that hero
            url = base_url + "{}/heroes/{}".format(bt, hero.lower().replace('-', ''))
            async with self.session.get(url, headers=self.headers) as r:
                data = await r.json()
                msg = data.get('msg')
                # Check if a user has not used the hero provided before
                if msg == 'hero data not found':
                    fmt = "{} has not used the hero {} before!".format(user.name, hero.title())
                    await self.bot.say(fmt)
                    return
                # Check if a hero that doesn't exist was provided
                elif msg == 'bad hero name':
                    fmt = "{} is not an actual hero!".format(hero.title())
                    await self.bot.say(fmt)
                    return

            # Same list comprehension as before
            fmt = "\n".join("{}: {}".format(i, r) for i, r in data['general_stats'].items() if i in check_g_stats)
            # Someone was complaining there was no KDR provided, so I made one myself and added that to the list
            if data['general_stats'].get('eliminations') and data['general_stats'].get('deaths'):
                fmt += "\nKill Death Ratio: {0:.2f}".format(
                    data['general_stats'].get('eliminations') / data['general_stats'].get('deaths'))
            fmt += "\n"
            fmt += "\n".join("{}: {}".format(i, r) for i, r in data['hero_stats'].items())
            # Same formatting as above
            await self.bot.say("Overwatch stats for {} using the hero {}: ```py\n{}``` "
                               .format(user.name, hero.title(), fmt.title().replace("_", " ")))

    @ow.command(pass_context=True, name="add", no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def add(self, ctx, bt: str):
        """Saves your battletag for looking up information"""
        # Battletags are normally provided like name#id
        # However the API needs this to be a -, so repliace # with - if it exists
        bt = bt.replace("#", "-")

        # This API sometimes takes a while to look up information, so send a message saying we're processing
        await self.bot.say("Looking up your profile information....")
        url = base_url + "{}/stats/general".format(bt)

        # All we're doing here is ensuring that the status is 200 when looking up someone's general information
        # If it's not, let them know exactly how to format their tag
        async with self.session.get(url, headers=self.headers) as r:
            if not r.status == 200:
                await self.bot.say("Profile does not exist! Battletags are picky, "
                                   "format needs to be `user#xxxx`. Capitalization matters")
                return

        # Now just save the battletag
        ow = await config.get_content('overwatch')
        ow[ctx.message.author.id] = bt
        await config.save_content('overwatch', ow)
        await self.bot.say("I have just saved your battletag {}".format(ctx.message.author.mention))

    @ow.command(pass_context=True, name="delete", aliases=['remove'], no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def delete(self, ctx):
        """Removes your battletag from the records"""
        result = await config.get_content('overwatch')
        if result.get(ctx.message.author.id):
            del result[ctx.message.author.id]
            await self.bot.say("I no longer have your battletag saved {}".format(ctx.message.author.mention))
        else:
            await self.bot.say("I don't even have your battletag saved {}".format(ctx.message.author.mention))

        del result[ctx.message.author.id]
        await self.bot.say("I have just removed your battletag!")


def setup(bot):
    bot.add_cog(Overwatch(bot))

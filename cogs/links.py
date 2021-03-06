from discord.ext import commands
from .utils import config
from .utils import checks

import discord
import aiohttp
import random
import re


class Links:
    """This class contains all the commands that make HTTP requests
    In other words, all commands here rely on other URL's to complete their requests"""

    def __init__(self, bot):
        self.bot = bot
        # Only default headers for all requests we should use sets the User-Agent
        self.headers = {"User-Agent": "Bonfire/1.0.0"}
        self.session = aiohttp.ClientSession()

    @commands.command()
    @checks.custom_perms(send_messages=True)
    async def wiki(self, *, query: str):
        """Pulls the top match for a specific term, and returns the definition"""
        # All we need to do is search for the term provided, so the action list and format never need to change
        base_url = "https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srsearch="
        async with self.session.get("{}{}".format(base_url, query.replace(" ", "%20")), headers=self.headers) as r:
            data = await r.json()
        if len(data['query']['search']) == 0:
            await self.bot.say("I could not find any results with that term, I tried my best :c")
            return
        # Wiki articles' URLs are in the format https://en.wikipedia.org/wiki/[Titlehere]
        # Replace spaces with %20
        url = "https://en.wikipedia.org/wiki/{}".format(data['query']['search'][0]['title'].replace(' ', '%20'))
        snippet = data['query']['search'][0]['snippet']
        # The next part replaces some of the HTML formatting that's provided
        # These are the only ones I've encountered so far through testing, there may be more though
        snippet = re.sub('<span class=\\"searchmatch\\">', '', snippet)
        snippet = re.sub('</span>', '', snippet)
        snippet = re.sub('&quot;', '"', snippet)

        await self.bot.say(
            "Here is the best match I found with the query `{}`:\nURL: {}\nSnippet: \n```\n{}```".format(query, url,
                                                                                                         snippet))

    @commands.command()
    @checks.custom_perms(send_messages=True)
    async def urban(self, *msg: str):
        """Pulls the top urbandictionary.com definition for a term"""
        url = "http://api.urbandictionary.com/v0/define?term={}".format('+'.join(msg))
        async with self.session.get(url, headers=self.headers) as r:
            data = await r.json()

        # Urban dictionary has some long definitions, some might not be able to be sent
        try:
            # List is the list of definitions found, if it's empty then nothing was found
            if len(data['list']) == 0:
                await self.bot.say("No result with that term!")
            # If the list is not empty, use the first result and print it's defintion
            else:
                await self.bot.say(data['list'][0]['definition'])
        except discord.HTTPException:
            await self.bot.say('```Error: Definition is too long for me to send```')

    @commands.command(pass_context=True)
    @checks.custom_perms(send_messages=True)
    async def derpi(self, ctx, *search: str):
        """Provides a random image from the first page of derpibooru.org for the following term"""
        if len(search) > 0:
            # This sets the url as url?q=search+terms
            url = 'https://derpibooru.org/search.json?q={}'.format('+'.join(search))
            nsfw_channels = await config.get_content("nsfw_channels")
            nsfw_channels = nsfw_channels.get('registered') or []
            # If this is a nsfw channel, we just need to tack on 'explicit' to the terms
            # Also use the custom filter that I have setup, that blocks some certain tags
            # If the channel is not nsfw, we don't need to do anything, as the default filter blocks explicit
            if ctx.message.channel.id in nsfw_channels:
                url += ",+%28explicit+OR+suggestive%29&filter_id=95938"
            else:
                url += ",+safe"

            # Get the response from derpibooru and parse the 'search' result from it
            async with self.session.get(url, headers=self.headers) as r:
                data = await r.json()

            try:
                results = data['search']
            except KeyError:
                await self.bot.say("No results with that search term, {0}!".format(ctx.message.author.mention))
                return

            # Find a random image based on the first page of results.
            # Currently derpibooru provides no way to change how many results can be shown on one page
            # Nor anyway to see how many pages are returned by a certain query
            # Due to the fact that a query may only return one page
            # We cannot try to check more than one as it might fail
            # So this is the best that we can do at the moment
            if len(results) > 0:
                index = random.SystemRandom().randint(0, len(results) - 1)
                image_link = 'http://{}'.format(results[index].get('representations').get('full')[2:].strip())
            else:
                await self.bot.say("No results with that search term, {0}!".format(ctx.message.author.mention))
                return
        else:
            # If no search term was provided, search for a random image
            async with self.session.get('https://derpibooru.org/images/random') as r:
                # .url will be the URl we end up at, not the one requested. 
                # https://derpibooru.org/images/random redirects to a random image, so this is exactly what we want
                image_link = r.url
        await self.bot.say(image_link)

    @commands.command(pass_context=True)
    @checks.custom_perms(send_messages=True)
    async def e621(self, ctx, *, tags: str):
        """Searches for a random image from e621.net
        Format for the search terms need to be 'search term 1, search term 2, etc.'
        If the channel the command is ran in, is registered as a nsfw channel, this image will be explicit"""

        # This changes the formatting for queries, so we don't
        # Have to use e621's stupid formatting when using the command
        tags = tags.replace(' ', '_')
        tags = tags.replace(',_', '%20')
        url = 'https://e621.net/post/index.json?limit=320&tags={}'.format(tags)
        # e621 provides a way to change how many images can be shown on one request
        # This gives more of a chance of random results, however it causes the lookup to take longer than most
        # Due to this, send a message saying we're looking up the information first
        await self.bot.say("Looking up an image with those tags....")

        nsfw_channels = await config.get_content("nsfw_channels")
        nsfw_channels = nsfw_channels.get('registered') or []
        # e621 by default does not filter explicit content, so tack on
        # safe/explicit based on if this channel is nsfw or not
        if ctx.message.channel.id in nsfw_channels:
            url += "%20rating:explicit"
        else:
            url += "%20rating:safe"

        async with self.session.get(url, headers=self.headers) as r:
            data = await r.json()

        # Check if there were any results, if there are find a random image based on the length of results
        if len(data) == 0:
            await self.bot.say("No results with that image {}".format(ctx.message.author.mention))
            return
        else:
            if len(data) == 1:
                rand_image = data[0]['file_url']
            else:
                rand_image = data[random.SystemRandom().randint(0, len(data) - 1)]['file_url']
        await self.bot.say(rand_image)


def setup(bot):
    bot.add_cog(Links(bot))

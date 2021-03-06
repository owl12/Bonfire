import aiohttp
import asyncio
import discord
import re

from discord.ext import commands
from .utils import config
from .utils import checks

base_url = 'https://ptvappapi.picarto.tv'

# This is a public key for use, I don't care if this is seen
key = '03e26294-b793-11e5-9a41-005056984bd4'


async def online_users():
    try:
        # Someone from picarto contacted me and told me their database queries are odd
        # It is more efficent on their end to make a query for all online users, and base checks off that
        # In place of requesting for /channel and checking if that is online currently, for each channel
        # This method is in place to just return all online_users
        url = '{}/online/all?key={}'.format(base_url, key)
        with aiohttp.ClientSession(headers={"User-Agent": "Bonfire/1.0.0"}) as s:
            async with s.get(url) as r:
                return await r.json()
    except:
        return {}


def check_online(online_channels, channel):
    # online_channels is the dictionary of all users online currently
    # And channel is the name we are checking against that
    # This creates a list of all users that match this channel name (should only ever be 1)
    # And returns True as long as it is more than 0
    matches = [stream for stream in online_channels if stream['channel_name'].lower() == channel.lower()]
    return len(matches) > 0


class Picarto:
    def __init__(self, bot):
        self.bot = bot
        self.headers = {"User-Agent": "Bonfire/1.0.0"}
        self.session = aiohttp.ClientSession()

    async def check_channels(self):
        await self.bot.wait_until_ready()
        # This is a loop that runs every 30 seconds, checking if anyone has gone online
        while not self.bot.is_closed:
            picarto = await config.get_content('picarto')
            # Get all online users before looping, so that only one request is needed
            online_users_list = await online_users()
            old_online_users = {m_id: data for m_id, data in picarto.items() if
                                data['notifications_on'] and data['live']}
            old_offline_users = {m_id: data for m_id, data in picarto.items() if
                                 data['notifications_on'] and not data['live']}

            for m_id, r in old_offline_users.items():
                # Get their url and their user based on that url
                url = r['picarto_url']
                user = re.search("(?<=picarto.tv/)(.*)", url).group(1)
                # Check if they are online right now
                if check_online(online_users_list, user):
                    for server_id in r['servers']:
                        # Get the channel to send the message to, based on the saved alert's channel
                        server = self.bot.get_server(server_id)
                        server_alerts = await config.get_content('server_alerts')
                        channel_id = server_alerts.get(server_id) or server_id
                        channel = self.bot.get_channel(channel_id)
                        # Get the member that has just gone live
                        member = discord.utils.get(server.members, id=m_id)

                        fmt = "{} has just gone live! View their stream at {}".format(member.display_name, url)
                        await self.bot.send_message(channel, fmt)
                        picarto[m_id]['live'] = 1
                    await config.save_content('picarto', picarto)
            for m_id, r in old_online_users.items():
                # Get their url and their user based on that url
                url = r['picarto_url']
                user = re.search("(?<=picarto.tv/)(.*)", url).group(1)
                # Check if they are online right now
                if not check_online(online_users_list, user):
                    for server_id in r['servers']:
                        # Get the channel to send the message to, based on the saved alert's channel
                        server = self.bot.get_server(server_id)
                        server_alerts = await config.get_content('server_alerts')
                        channel_id = server_alerts.get(server_id) or server_id
                        channel = self.bot.get_channel(channel_id)
                        # Get the member that has just gone live
                        member = discord.utils.get(server.members, id=m_id)
                        fmt = "{} has just gone offline! Catch them next time they stream at {}".format(
                            member.display_name, url)
                        await self.bot.send_message(channel, fmt)
                        picarto[m_id]['live'] = 0
                    await config.save_content('picarto', picarto)
            await asyncio.sleep(30)

    @commands.group(pass_context=True, invoke_without_command=True)
    @checks.custom_perms(send_messages=True)
    async def picarto(self, ctx, member: discord.Member = None):
        """This command can be used to view Picarto stats about a certain member"""
        # If member is not given, base information on the author
        member = member or ctx.message.author
        picarto_urls = await config.get_content('picarto')
        try:
            member_url = picarto_urls.get(member.id)['picarto_url']
        except:
            await self.bot.say("That user does not have a picarto url setup!")
            return

        # Use regex to get the actual username so that we can make a request to the API
        stream = re.search("(?<=picarto.tv/)(.*)", member_url).group(1)
        url = '{}/channel/{}?key={}'.format(base_url, stream, key)
        async with self.session.get(url, headers=self.headers) as r:
            data = await r.json()

        # Not everyone has all these settings, so use this as a way to print information if it does, otherwise ignore it
        things_to_print = ['channel', 'commissions_enabled', 'is_nsfw', 'program', 'tablet', 'followers',
                           'content_type']
        # Using title and replace to provide a nice way to print the data
        fmt = "\n".join(
            "{}: {}".format(i.title().replace("_", " "), r) for i, r in data.items() if i in things_to_print)

        # Social URL's can be given if a user wants them to show
        # Print them if they exist, otherwise don't try to include them
        social_links = data.get('social_urls')
        if social_links:
            fmt2 = "\n".join("\t{}: {}".format(i.title().replace("_", " "), r) for i, r in social_links.items())
            fmt = "{}\nSocial Links:\n{}".format(fmt, fmt2)
        await self.bot.say("Picarto stats for {}: ```\n{}```".format(member.display_name, fmt))

    @picarto.command(name='add', pass_context=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def add_picarto_url(self, ctx, url: str):
        """Saves your user's picarto URL"""
        # This uses a lookbehind to check if picarto.tv exists in the url given
        # If it does, it matches picarto.tv/user and sets the url as that
        # Then (in the else) add https://www. to that
        # Otherwise if it doesn't match, we'll hit an AttributeError due to .group(0)
        # This means that the url was just given as a user (or something complete invalid)
        # So set URL as https://www.picarto.tv/[url]
        # Even if this was invalid such as https://www.picarto.tv/twitch.tv/user
        # For example, our next check handles that
        try:
            url = re.search("((?<=://)?picarto.tv/)+(.*)", url).group(0)
        except AttributeError:
            url = "https://www.picarto.tv/{}".format(url)
        else:
            url = "https://www.{}".format(url)

        api_url = '{}/channel/{}?key={}'.format(base_url, re.search("https://www.picarto.tv/(.*)", url).group(1), key)

        # Check if we can find a user with the provided information, if we can't just return
        async with self.session.get(api_url, headers=self.headers) as r:
            if not r.status == 200:
                await self.bot.say("That Picarto user does not exist! "
                                   "What would be the point of adding a nonexistant Picarto user? Silly")
                return

        picarto_urls = await config.get_content('picarto')
        result = picarto_urls.get(ctx.message.author.id)

        # If information for this user already exists, override just the url, and not the information
        # Otherwise create the information with notications on, and that they're not live.
        # The next time it's checked, they'll go 'online'
        if result is not None:
            picarto_urls[ctx.message.author.id]['picarto_url'] = url
        else:
            picarto_urls[ctx.message.author.id] = {'picarto_url': url,
                                                   'servers': [ctx.message.server.id],
                                                   'notifications_on': 1, 'live': 0}
        await config.save_content('picarto', picarto_urls)
        await self.bot.say(
            "I have just saved your Picarto url {}, this server will now be notified when you go live".format(
                ctx.message.author.mention))

    @picarto.command(name='remove', aliases=['delete'], pass_context=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def remove_picarto_url(self, ctx):
        """Removes your picarto URL"""
        picarto = await config.get_content('picarto')
        if picarto.get(ctx.message.author.id) is not None:
            del picarto[ctx.message.author.id]
            await config.save_content('picarto', picarto)
            await self.bot.say("I am no longer saving your picarto URL {}".format(ctx.message.author.mention))
        else:
            await self.bot.say(
                "I do not have your picarto URL added {}. You can save your picarto url with {}picarto add".format(
                    ctx.message.author.mention, ctx.prefix))

    @picarto.group(pass_context=True, no_pm=True, invoke_without_command=True)
    @checks.custom_perms(send_messages=True)
    async def notify(self, ctx):
        """This can be used to turn picarto notifications on or off
        Call this command by itself, to add this server to the list of servers to be notified"""
        member = ctx.message.author

        # If this user's picarto URL is not saved, no use in adding this server to the list that doesn't exist
        picarto = await config.get_content('picarto')
        result = picarto.get(member.id)
        if result is None:
            await self.bot.say(
                "I do not have your picarto URL added {}. You can save your picarto url with {}picarto add".format(
                    member.mention, ctx.prefix))

        # Append this server's ID and save the new content
        picarto[member.id]['servers'].append(ctx.message.server.id)
        await config.save_content('picarto', picarto)
        await self.bot.say(
            "I have just changed which channel will be notified when you go live, to `{}`".format(
                ctx.message.channel.name))

    @notify.command(name='on', aliases=['start,yes'], pass_context=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def notify_on(self, ctx):
        """Turns picarto notifications on"""
        picarto = await config.get_content('picarto')
        result = picarto.get(ctx.message.author.id)
        # Check if this user has saved their picarto URL first
        if result is None:
            await self.bot.say(
                "I do not have your picarto URL added {}. You can save your picarto url with !picarto add".format(
                    ctx.message.author.mention))
        # Next check if they are already set to notify
        elif result['notifications_on']:
            await self.bot.say("What do you want me to do, send two notifications? Not gonna happen {}".format(
                ctx.message.author.mention))
        else:
            picarto[ctx.message.author.id]['notifications_on'] = 1
            await config.save_content('picarto', picarto)
            await self.bot.say("I will notify if you go live {}, you'll get a bajillion followers I promise c:".format(
                ctx.message.author.mention))

    @notify.command(name='off', aliases=['stop,no'], pass_context=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def notify_off(self, ctx):
        """Turns picarto notifications off"""
        picarto = await config.get_content('picarto')
        # Check if this user has saved their picarto URL first
        if picarto.get(ctx.message.author.id) is None:
            await self.bot.say(
                "I do not have your picarto URL added {}. You can save your picarto url with !picarto add".format(
                    ctx.message.author.mention))
        # Next check if they are already set to not notify
        elif not picarto.get(ctx.message.author.id)['notifications_on']:
            await self.bot.say("I am already set to not notify if you go live! Pay attention brah {}".format(
                ctx.message.author.mention))
        else:
            picarto[ctx.message.author.id]['notifications_on'] = 0
            await config.save_content('picarto', picarto)
            await self.bot.say(
                "I will not notify if you go live anymore {}, "
                "are you going to stream some lewd stuff you don't want people to see?~".format(
                    ctx.message.author.mention))


def setup(bot):
    p = Picarto(bot)
    config.loop.create_task(p.check_channels())
    bot.add_cog(Picarto(bot))

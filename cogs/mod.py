from discord.ext import commands
from .utils import checks
from .utils import config
import discord
import re
import asyncio

valid_perms = [p for p in dir(discord.Permissions) if isinstance(getattr(discord.Permissions, p), property)]


class Mod:
    """Commands that can be used by a or an admin, depending on the command"""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(kick_members=True)
    async def alerts(self, ctx, channel: discord.Channel):
        """This command is used to set a channel as the server's 'notifications' channel
        Any notifications (like someone going live on Twitch, or Picarto) will go to that channel"""
        server_alerts = await config.get_content('server_alerts')
        # This will update/add the channel if an entry for this server exists or not
        server_alerts[ctx.message.server.id] = channel.id
        await config.save_content('server_alerts', server_alerts)
        await self.bot.say("I have just changed this server's 'notifications' channel"
                           "\nAll notifications will now go to `{}`".format(channel))

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(kick_members=True)
    async def usernotify(self, ctx, on_off: str):
        """This command can be used to set whether or not you want user notificaitons to show
        This will save what channel you run this command in, that will be the channel used to send the notification to
        Provide on, yes, or true to set it on; otherwise it will be turned off"""
        # Join/Leave notifications can be kept separate from normal alerts
        # So we base this channel on it's own and not from alerts
        # When mod logging becomes available, that will be kept to it's own channel if wanted as well
        on_off = ctx.message.channel.id if re.search("(on|yes|true)", on_off.lower()) else None
        notifications = await config.get_content('user_notifications')
        notifications[ctx.message.server.id] = on_off
        await config.save_content('user_notifications', notifications)
        fmt = "notify" if on_off else "not notify"
        await self.bot.say("This server will now {} if someone has joined or left".format(fmt))

    @commands.group(pass_context=True, no_pm=True)
    async def nsfw(self, ctx):
        """Handles adding or removing a channel as a nsfw channel"""
        # This command isn't meant to do anything, so just send an error if an invalid subcommand is passed
        if ctx.invoked_subcommand is None:
            await self.bot.say('Invalid subcommand passed: {0.subcommand_passed}'.format(ctx))

    @nsfw.command(name="add", pass_context=True, no_pm=True)
    @checks.custom_perms(kick_members=True)
    async def nsfw_add(self, ctx):
        """Registers this channel as a 'nsfw' channel"""
        nsfw_channels = await config.get_content('nsfw_channels')
        # rethinkdb cannot save a list as a field, so we need a dict with one elemtn to store our list
        nsfw_channels = nsfw_channels.get('registered') or []
        if ctx.message.channel.id in nsfw_channels:
            await self.bot.say("This channel is already registered as 'nsfw'!")
        else:
            # Append instead of setting to a certain channel, so that multiple channels can be nsfw
            nsfw_channels.append(ctx.message.channel.id)
            await config.save_content('nsfw_channels', {'registered': nsfw_channels})
            await self.bot.say("This channel has just been registered as 'nsfw'! Have fun you naughties ;)")

    @nsfw.command(name="remove", aliases=["delete"], pass_context=True, no_pm=True)
    @checks.custom_perms(kick_members=True)
    async def nsfw_remove(self, ctx):
        """Removes this channel as a 'nsfw' channel"""
        nsfw_channels = await config.get_content('nsfw_channels')
        nsfw_channels = nsfw_channels.get('registered') or []
        if ctx.message.channel.id not in nsfw_channels:
            await self.bot.say("This channel is not registered as a ''nsfw' channel!")
        else:
            nsfw_channels.remove(ctx.message.channel.id)
            await config.save_content('nsfw_channels', {'registered': nsfw_channels})
            await self.bot.say("This channel has just been unregistered as a nsfw channel")

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(kick_members=True)
    async def say(self, ctx, *, msg: str):
        """Tells the bot to repeat what you say"""
        fmt = "\u200B{}".format(msg)
        await self.bot.say(fmt)
        try:
            await self.bot.delete_message(ctx.message)
        except:
            pass

    @commands.group(pass_context=True, invoke_without_command=True, no_pm=True)
    @checks.custom_perms(send_messages=True)
    async def perms(self, ctx, *, command: str = None):
        """This command can be used to print the current allowed permissions on a specific command
        This supports groups as well as subcommands; pass no argument to print a list of available permissions"""
        if command is None:
            await self.bot.say(
                "Valid permissions are: ```\n{}```".format("\n".join("{}".format(i) for i in valid_perms)))
            return

        custom_perms = await config.get_content('custom_permissions')
        server_perms = custom_perms.get(ctx.message.server.id) or {}

        cmd = None
        # This is the same loop as the add command, we need this to get the
        # command object so we can get the qualified_name
        for part in command.split():
            try:
                if cmd is None:
                    cmd = self.bot.commands.get(part)
                else:
                    cmd = cmd.commands.get(part)
            except AttributeError:
                cmd = None
                break

        if cmd is None:
            await self.bot.say("That is not a valid command!")
            return

        perms_value = server_perms.get(cmd.qualified_name)
        if perms_value is None:
            # If we don't find custom permissions, get the required permission for a command
            # based on what we set in checks.custom_perms, if custom_perms isn't found, we'll get an IndexError
            try:
                custom_perms = [func for func in cmd.checks if "custom_perms" in func.__qualname__][0]
            except IndexError:
                # Loop through and check if there is a check called is_owner
                # Ff we loop through and don't find one
                # This means that the only other choice is to be
                # Able to manage the server (for the checks on perm commands)
                for func in cmd.checks:
                    if "is_owner" in func.__qualname__:
                        await self.bot.say("You need to own the bot to run this command")
                        return
                await self.bot.say(
                    "You are required to have `manage_server` permissions to run `{}`".format(cmd.qualified_name))
                return

            # Perms will be an attribute if custom_perms is found no matter what, so need to check this
            perms = "\n".join(attribute for attribute, setting in custom_perms.perms.items() if setting)
            await self.bot.say(
                "You are required to have `{}` permissions to run `{}`".format(perms, cmd.qualified_name))
        else:
            # Permissions are saved as bit values, so create an object based on that value
            # Then check which permission is true, that is our required permission
            # There's no need to check for errors here, as we ensure a permission is valid when adding it
            permissions = discord.Permissions(perms_value)
            needed_perm = [perm[0] for perm in permissions if perm[1]][0]
            await self.bot.say("You need to have the permission `{}` "
                               "to use the command `{}` in this server".format(needed_perm, command))

    @perms.command(name="add", aliases=["setup,create"], pass_context=True, no_pm=True)
    @commands.has_permissions(manage_server=True)
    async def add_perms(self, ctx, *msg: str):
        """Sets up custom permissions on the provided command
        Format must be 'perms add <command> <permission>'
        If you want to open the command to everyone, provide 'none' as the permission"""

        # Since subcommands exist, base the last word in the list as the permission, and the rest of it as the command
        command = " ".join(msg[0:len(msg) - 1])
        permissions = msg[len(msg) - 1]

        # If a user can run a command, they have to have send_messages permissions; so use this as the base
        if permissions.lower() == "none":
            permissions = "send_messages"

        # Convert the string to an int value of the permissions object, based on the required permission
        perm_obj = discord.Permissions.none()
        setattr(perm_obj, permissions, True)
        perm_value = perm_obj.value

        # This next loop ensures the command given is valid. We need to loop through commands
        # As self.bot.commands only includes parent commands
        # So we are splitting the command in parts, looping through the commands
        # And getting the subcommand based on the next part
        # If we try to access commands of a command that isn't a group
        # We'll hit an AttributeError, meaning an invalid command was given
        # If we loop through and don't find anything, cmd will still be None
        # And we'll report an invalid was given as well
        cmd = None
        for part in msg[0:len(msg) - 1]:
            try:
                if cmd is None:
                    cmd = self.bot.commands.get(part)
                else:
                    cmd = cmd.commands.get(part)
            except AttributeError:
                cmd = None
                break

        if cmd is None:
            await self.bot.say(
                "That command does not exist! You can't have custom permissions on a non-existant command....")
            return

        # Two cases I use should never have custom permissions setup on them, is_owner for obvious reasons
        # The other case is if I'm using the default has_permissions case
        # Which means I do not want to check custom permissions at all
        # Currently the second case is only on adding and removing permissions, to avoid abuse on these
        for check in cmd.checks:
            if "is_owner" == check.__name__ or re.search("has_permissions", str(check)) is not None:
                await self.bot.say("This command cannot have custom permissions setup!")
                return

        if getattr(discord.Permissions, permissions, None) is None:
            await self.bot.say("{} does not appear to be a valid permission! Valid permissions are: ```\n{}```"
                               .format(permissions, "\n".join(valid_perms)))
            return

        custom_perms = await config.get_content('custom_permissions')
        server_perms = custom_perms.get(ctx.message.server.id) or {}
        # Save the qualified name, so that we don't get screwed up by aliases
        server_perms[cmd.qualified_name] = perm_value
        custom_perms[ctx.message.server.id] = server_perms

        await config.save_content('custom_permissions', custom_perms)
        await self.bot.say("I have just added your custom permissions; "
                           "you now need to have `{}` permissions to use the command `{}`".format(permissions, command))

    @perms.command(name="remove", aliases=["delete"], pass_context=True, no_pm=True)
    @commands.has_permissions(manage_server=True)
    async def remove_perms(self, ctx, *command: str):
        """Removes the custom permissions setup on the command specified"""
        custom_perms = await config.get_content('custom_permissions')
        server_perms = custom_perms.get(ctx.message.server.id) or {}
        if server_perms is None:
            await self.bot.say("There are no custom permissions setup on this server yet!")
            return

        cmd = None
        # This is the same loop as the add command, we need this to get the
        # command object so we can get the qualified_name
        for part in command:
            try:
                if cmd is None:
                    cmd = self.bot.commands.get(part)
                else:
                    cmd = cmd.commands.get(part)
            except AttributeError:
                cmd = None
                break

        if cmd is None:
            await self.bot.say(
                "That command does not exist! You can't have custom permissions on a non-existant command....")
            return

        command_perms = server_perms.get(cmd.qualified_name)
        if command_perms is None:
            await self.bot.say("You do not have custom permissions setup on this command!")
            return

        del custom_perms[ctx.message.server.id][cmd]
        await config.save_content('custom_permissions', custom_perms)
        await self.bot.say("I have just removed the custom permissions for {}!".format(cmd))

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(manage_server=True)
    async def prefix(self, ctx, *, prefix: str):
        """This command can be used to set a custom prefix per server"""
        prefixes = await config.get_content('prefixes')
        prefixes[ctx.message.server.id] = prefix
        await config.save_content('prefixes', prefixes)
        await self.bot.say(
            "I have just updated the prefix for this server; you now need to call commands with `{}`".format(prefix))

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(manage_messages=True)
    async def purge(self, ctx, limit: int = 100):
        """This command is used to a purge a number of messages from the channel"""
        if not ctx.message.channel.permissions_for(ctx.message.server.me).manage_messages:
            await self.bot.say("I do not have permission to delete messages...")
            return
        await self.bot.purge_from(ctx.message.channel, limit=limit)

    @commands.command(pass_context=True, no_pm=True)
    @checks.custom_perms(manage_messages=True)
    async def prune(self, ctx, limit: int = 100):
        """This command can be used to prune messages from certain members
        Mention any user you want to prune messages from; if no members are mentioned, the messages removed will be mine
        If no limit is provided, then 100 will be used. This is also the max limit we can use"""
        # We can only get logs from 100 messages at a time, so make sure we are not above that threshold
        if limit > 100:
            limit = 100

        # If no members are provided, assume we're trying to prune our own messages
        members = ctx.message.mentions
        if len(members) == 0:
            members = [ctx.message.server.me]
        # If we're not setting the user to the bot, then we're deleting someone elses messages
        # To do so, we need manage_messages permission, so check if we have that
        elif not ctx.message.channel.permissions_for(ctx.message.server.me).manage_messages:
            await self.bot.say("I do not have permission to delete messages...")
            return

        # Since logs_from will give us any message, not just the user's we need
        # We'll increment count, and stop deleting messages if we hit the limit.
        count = 0
        async for msg in self.bot.logs_from(ctx.message.channel):
            if msg.author in members:
                await self.bot.delete_message(msg)
                count += 1
                if count >= limit:
                    break
        msg = await self.bot.say("{} messages succesfully deleted".format(count))
        await asyncio.sleep(60)
        await self.bot.delete_message(msg)

    @commands.group(aliases=['rule'], pass_context=True, no_pm=True, invoke_without_command=True)
    @checks.custom_perms(send_messages=True)
    async def rules(self, ctx):
        """This command can be used to view the current rules on the server"""
        rules = await config.get_content('rules')
        server_rules = rules.get(ctx.message.server.id)
        if server_rules is None or len(server_rules) == 0:
            await self.bot.say("This server currently has no rules on it! I see you like to live dangerously...")
            return
        # Enumerate the list, so that we can print the number and the rule for each rule
        fmt = "\n".join("{}) {}".format(num + 1, rule) for num, rule in enumerate(server_rules))
        await self.bot.say('```\n{}```'.format(fmt))

    @rules.command(name='add', aliases=['create'], pass_context=True, no_pm=True)
    @checks.custom_perms(manage_server=True)
    async def rules_add(self, ctx, *, rule: str):
        """Adds a rule to this server's rules"""
        # Nothing fancy here, just get the rules, append the rule, and save it
        rules = await config.get_content('rules')
        server_rules = rules.get(ctx.message.server.id) or []
        server_rules.append(rule)
        rules[ctx.message.server.id] = server_rules
        await config.save_content('rules', rules)
        await self.bot.say("I have just saved your new rule, use the rules command to view this server's current rules")

    @rules.command(name='remove', aliases=['delete'], pass_context=True, no_pm=True)
    @checks.custom_perms(manage_server=True)
    async def rules_delete(self, ctx, rule: int = None):
        """Removes one of the rules from the list of this server's rules
        Provide a number to delete that rule; if no number is provided
        I'll print your current rules and ask for a number"""
        rules = await config.get_content('rules')
        server_rules = rules.get(ctx.message.server.id) or []
        if server_rules is None or len(server_rules) == 0:
            await self.bot.say(
                "This server currently has no rules on it! Can't remove something that doesn't exist bro")
            return

        # Get the list of rules so that we can print it if no number was provided
        # Since this is a list and not a dictionary, order is preserved, and we just need the number of the rule
        list_rules = "\n".join("{}) {}".format(num + 1, rule) for num, rule in enumerate(server_rules))

        if rule is None:
            await self.bot.say("Your rules are:\n```\n{}```Please provide the rule number"
                               "you would like to remove (just the number)".format(list_rules))

            # All we need for the check is to ensure that the content is just a digit, that is all we need
            msg = await self.bot.wait_for_message(timeout=60.0, author=ctx.message.author, channel=ctx.message.channel,
                                                  check=lambda m: m.content.isdigit())
            if msg is None:
                await self.bot.say("You took too long...it's just a number, seriously? Try typing a bit quicker")
                return
            del server_rules[int(msg.content) - 1]
            rules[ctx.message.server.id] = server_rules
            await config.save_content('rules', rules)
            await self.bot.say("I have just removed that rule from your list of rules!")
            return

        # This check is just to ensure a number was provided within the list's range
        try:
            del server_rules[rule - 1]
            rules[ctx.message.server.id] = server_rules
            await config.save_content('rules', rules)
            await self.bot.say("I have just removed that rule from your list of rules!")
        except IndexError:
            await self.bot.say("That is not a valid rule number, try running the command again. "
                               "Your current rules are:\n```\n{}```".format(list_rules))


def setup(bot):
    bot.add_cog(Mod(bot))

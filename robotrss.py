# /bin/bash/python
# encoding: utf-8
import os

from telegram import Update, Chat
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

from util.database import DatabaseHandler
from util.feedhandler import FeedHandler
from util.filehandler import FileHandler
from util.processing import BatchProcess
from util.telegram_helpers import extract_status_change


async def greet_chat_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets new users in chats and announces when someone leaves"""
    result = extract_status_change(update.chat_member)
    if result is None:
        return

    was_member, is_member = result
    cause_name = update.chat_member.from_user.mention_html()
    member_name = update.chat_member.new_chat_member.user.mention_html()

    if not was_member and is_member:
        await update.effective_chat.send_message(
            f"{member_name} was added by {cause_name}. Welcome!",
            parse_mode=ParseMode.HTML,
        )
    elif was_member and not is_member:
        await update.effective_chat.send_message(
            f"{member_name} is no longer with us. Thanks a lot, {cause_name} ...",
            parse_mode=ParseMode.HTML,
        )


async def track_chats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tracks the chats the bot is in."""
    result = extract_status_change(update.my_chat_member)
    if result is None:
        message = "I am not in any channels"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message, disable_web_page_preview=True)
        return
    was_member, is_member = result
    print(result)

    # Let's check who is responsible for the change
    cause_name = update.effective_user.full_name

    # Handle chat types differently:
    chat = update.effective_chat
    if chat.type == Chat.PRIVATE:
        if not was_member and is_member:
            # This may not be really needed in practice because most clients will automatically
            # send a /start command after the user unblocks the bot, and start_private_chat()
            # will add the user to "user_ids".
            # We're including this here for the sake of the example.
            print("%s unblocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).add(chat.id)
        elif was_member and not is_member:
            print("%s blocked the bot", cause_name)
            context.bot_data.setdefault("user_ids", set()).discard(chat.id)
    elif chat.type in [Chat.GROUP, Chat.SUPERGROUP]:
        if not was_member and is_member:
            print("%s added the bot to the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).add(chat.id)
        elif was_member and not is_member:
            print("%s removed the bot from the group %s", cause_name, chat.title)
            context.bot_data.setdefault("group_ids", set()).discard(chat.id)
    elif not was_member and is_member:
        print("%s added the bot to the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).add(chat.id)
    elif was_member and not is_member:
        print("%s removed the bot from the channel %s", cause_name, chat.title)
        context.bot_data.setdefault("channel_ids", set()).discard(chat.id)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Send a message when the command /help is issued.
    """

    message = "You can use the following commands:\n""" \
              "/add <url> <entryname> - Adds a new subscription to your list.\n" \
              "/remove <entryname> - Removes an existing subscription from your list.\n" \
              "/get <entryname> [optional: <count 1-10>] - Manually parses your subscription, sending you the last " \
              "elements.\n" \
              "/list - Shows all your subscriptions as a list.\n" \
              "/about - Shows some information about RobotRSS Bot\n" \
              "/help - Shows the help menu\n\n" \
              "If you need help with handling the commands, please have a look at " \
              "https://github.com/cbrgm/telegram-robot-rss. There I have summarized " \
              "everything necessary for you!"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, disable_web_page_preview=True)


async def about_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows about information
    """

    message = "Thank you for using <b>RobotRSS</b>! \n\n If you like the bot, please recommend it to others! " \
              "\n\nDo you have problems, ideas or suggestions about what the bot should be able to do? Then " \
              "contact me at http://cbrgm.de or @cbrgm or create an issue on " \
              "https://github.com/cbrgm/telegram-robot-rss. There you will also find my source " \
              "code, if you are interested in how I work!"
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


class RobotRss(object):

    def __init__(self, telegram_token, update_interval):

        # Initialize bot internals
        self.db = DatabaseHandler("resources/datastore.db")
        self.fh = FileHandler("..")

        # Register webhook to telegram bot
        #persistence = PicklePersistence(filepath="bot_data")
        #self.application = ApplicationBuilder().token(telegram_token).persistence(persistence=persistence).build()
        self.application = ApplicationBuilder().token(telegram_token).build()
        # Regular commands
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("stop", self.stop))
        self.application.add_handler(CommandHandler("help", help_handler))
        self.application.add_handler(CommandHandler("about", about_handler))
        self.application.add_handler(CommandHandler("list", self.list))

        # Feed related commands
        self.application.add_handler(CommandHandler(
            "add",
            self.add,
            filters=None,
            has_args=True)
        )
        self.application.add_handler(CommandHandler(
            "get",
            self.get,
            filters=None,
            has_args=True)
        )
        self.application.add_handler(CommandHandler(
            "remove",
            self.remove,
            filters=None,
            has_args=True)
        )
        # Keep track of which chats the bot is in
        # self.application.add_handler(ChatMemberHandler(track_chats, ChatMemberHandler.MY_CHAT_MEMBER))
        self.application.add_handler(CommandHandler("show_chats", self.show_chats))
        # self.application.add_handler(ChatMemberHandler(greet_chat_members, ChatMemberHandler.CHAT_MEMBER))
        # self.application.add_handler(MessageHandler(filters.ALL, self.start_private_chat))

        self.processing = BatchProcess(
             database=self.db, update_interval=update_interval, bot=self.application.bot)

        self.processing.start()
        # Start the Bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Send a message when the command /start is issued.
        """

        telegram_user = update.message.from_user

        # Add new User if not exists
        if not self.db.get_user(telegram_id=telegram_user.id):
            message = "Hello! I don't think we've met before! I am an RSS News Bot and would like to help you to " \
                      "receive your favourite news in the future! Let me first set up a few things before we start..."
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

            self.db.add_user(telegram_id=telegram_user.id,
                             username=telegram_user.username,
                             firstname=telegram_user.first_name,
                             lastname=telegram_user.last_name,
                             language_code=telegram_user.language_code,
                             is_bot=telegram_user.is_bot,
                             is_active=True)

        self.db.update_user(telegram_id=telegram_user.id, is_active=1)

        message = "You will now receive news! Use /help if you need some tips how to tell me what to do!"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Adds a rss subscription to user
        """
        telegram_user = update.message.from_user
        args = context.args

        if len(args) != 2:
            message = "Sorry! I could not add the entry! Please use the the command passing the following " \
                      "arguments:\n\n /add <url> <entryname> \n\n Here is a short example: \n\n /add " \
                      "http://www.feedforall.com/sample.xml ExampleEntry"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        arg_url = FeedHandler.format_url_string(string=args[0])
        arg_entry = args[1]

        # Check if argument matches url format
        if not FeedHandler.is_parsable(url=arg_url):
            message = f"Sorry! It seems like {arg_url} doesn't provide an RSS news feed.. Have you tried another URL " \
                      f"from that provider?"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        # Check if entry does not exist
        entries = self.db.get_urls_for_user(telegram_id=telegram_user.id)
        for entry in entries:
            name = entry[1]
            url = entry[0]
            if url.lower() == arg_url.lower() or name.lower() == name:
                message = f"Sorry, {telegram_user.first_name}! I already have {url} " \
                          f"in your subscriptions with name '{name}'." \
                          f"Please choose another name or delete the entry using '/remove {name}'"
                await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
                return

        self.db.add_user_bookmark(
            telegram_id=telegram_user.id, url=arg_url.lower(), alias=arg_entry)
        message = f"I added {arg_entry} to your subscriptions"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    async def get(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Manually parses a rss feed
        """

        telegram_user = update.message.from_user
        help_message = "To get the last news of your subscription please use /get <entryname> [optional: <count " \
                       "1-10>]. Make sure you first add a feed using the /add command."

        args = context.args

        if len(args) > 2 or len(args) == 0:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=help_message)
            return

        if len(args) == 2:
            args_entry = args[0]
            args_count = int(args[1])
        else:
            args_entry = args[0]
            args_count = 4

        url = self.db.get_user_bookmark(
            telegram_id=telegram_user.id, alias=args_entry)

        if url is None:
            message = f"I can not find an entry with label {args_entry} in your subscriptions. Please check your " \
                      f"subscriptions using /list and use the delete " \
                      "command again!"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        entries = FeedHandler.parse_feed(url[0], args_count)
        for entry in entries:
            message = "[" + url[1] + "] <a href='" + \
                      entry.link + "'>" + entry.title + "</a>"
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=message,
                                               parse_mode=ParseMode.HTML)
            except Forbidden:
                self.db.update_user(telegram_id=telegram_user.id, is_active=0)
            except TelegramError:
                # handle all other telegram related errors
                pass

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Removes a rss subscription from user
        """

        telegram_user = update.message.from_user
        args = context.args

        if len(args) != 1:
            message = "To remove a subscriptions from your list please use /remove <entryname>. To see all your " \
                      "subscriptions along with their entry names use /list !"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        entry = self.db.get_user_bookmark(
            telegram_id=telegram_user.id, alias=args[0])

        if entry:
            self.db.remove_user_bookmark(
                telegram_id=telegram_user.id, url=entry[0])
            message = f"I removed {args[0]} from your subscriptions"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        else:
            message = f"I can not find {args[0]} in your subscriptions! Please check your subscriptions using /list " \
                      f"and use the delete " \
                      "command again!"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    async def list(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Displays a list of all user subscriptions
        """

        telegram_user = update.message.from_user

        entries = self.db.get_urls_for_user(telegram_id=telegram_user.id)

        if entries is not None and len(entries) > 0:
            message = "Subscriptions"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            for entry in entries:
                message = "[" + entry[1] + "]\n " + entry[0]
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        message = "You have no subscriptions"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Stops the bot from working
        """

        telegram_user = update.message.from_user
        self.db.update_user(telegram_id=telegram_user.id, is_active=0)

        message = "Oh.. Okay, I will not send you any more news updates! If you change your mind and you want to " \
                  "receive messages from me again use /start command again!"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)

    async def start_private_chat(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Greets the user and records that they started a chat with the bot if it's a private chat.
        Since no `my_chat_member` update is issued when a user starts a private chat with the bot
        for the first time, we have to track it explicitly here.
        """

        chat = update.effective_chat
        self.db.add_chat(chat)

        if chat.type != Chat.PRIVATE or chat.id in context.bot_data.get("user_ids", set()):
            return

        user_name = update.effective_user.full_name
        context.bot_data.setdefault("user_ids", set()).add(chat.id)

        await update.effective_message.reply_text(
            f"Welcome {user_name}. Use /show_chats to see what chats I'm in."
        )

    async def show_chats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Shows which chats the bot is in"""
        entries = self.db.get_all_chats()

        if entries is not None and len(entries) > 0:
            message = "Chats:\n"
            for entry in entries:
                name = ""
                if entry[1] is not None:
                    name = f" '{entry[1]}'"
                message += f"{entry[2]}: {entry[0]}{name}\n"
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message)
            return

        message = "You have no chats"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


if __name__ == '__main__':
    # Load Credentials
    fh = FileHandler("..")
    credentials = fh.load_json("resources/credentials.json")

    if 'BOT_TOKEN' in os.environ:
        token = os.environ.get("BOT_TOKEN")
    else:
        token = credentials["telegram_token"]
    if 'UPDATE_INTERVAL' in os.environ:
        update_interval = int(os.environ.get("UPDATE_INTERVAL", 300))
    else:
        update_interval = credentials["update_interval"]

    RobotRss(telegram_token=token, update_interval=update_interval)

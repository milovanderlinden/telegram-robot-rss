import sqlite3
from datetime import datetime

from telegram import Chat

from util.datehandler import DateHandler

from peewee import (
    Model,
    SqliteDatabase,
    CharField,
    AutoField,
    BooleanField,
    DateTimeField,
    ForeignKeyField, CompositeKey, IntegrityError
)

db = SqliteDatabase(None)


class BaseModel(Model):
    class Meta:
        database = db


class User(BaseModel):
    telegram_id: int = AutoField(primary_key=True)
    username: str = CharField()
    firstname: str = CharField()
    lastname: str = CharField()
    language: str = CharField()
    is_bot: bool = BooleanField()
    is_active: bool = BooleanField()

    class Meta:
        table_name = 'user'


class Feed(BaseModel):
    url: str = CharField(primary_key=True)
    last_updated: datetime = DateTimeField()

    class Meta:
        table_name = 'web'


class WebUser(BaseModel):
    url = ForeignKeyField(Feed, column_name='url', backref='web_user', on_delete='CASCADE')
    telegram_id = ForeignKeyField(User, column_name='telegram_id', backref='web_user', on_delete='CASCADE')
    alias = CharField()

    class Meta:
        table_name = 'web_user'
        primary_key = CompositeKey('url', 'telegram_id')


class Channel(BaseModel):
    chat_id: int = AutoField(primary_key=True)
    title: str = CharField()
    type: str = CharField()

    class Meta:
        table_name = 'chat'


class WebChat(BaseModel):
    url = ForeignKeyField(Feed, column_name='url', backref='web_chat', on_delete='CASCADE')
    chat_id = ForeignKeyField(Channel, column_name='chat_id', backref='web_user', on_delete='CASCADE')
    alias = CharField()

    class Meta:
        table_name = 'web_chat'
        primary_key = CompositeKey('url', 'chat_id')


class DatabaseHandler(object):

    def __init__(self, database_path):

        self.database_path = database_path
        self.db = db
        self.db.init(database_path)
        self.db.create_tables([User, Feed, WebUser, Channel, WebChat])

    def add_user(self, telegram_id, username, firstname, lastname, language_code, is_bot, is_active):
        """Adds a user to sqlite database

        Args:
            telegram_id (int): The telegram_id of a user.
            username (str): The username of a user.
            firstname (str): The firstname of a user.
            lastname (str): The lastname of a user.
            language_code (str): The language_code of a user.
            is_bot (bool): The is_bot flag of a user.
            is_active (bool): User active or inactive.
        """
        _user = User.create(
            telegram_id=telegram_id,
            username=username,
            firstname=firstname,
            lastname=lastname,
            language=language_code,
            is_bot=is_bot,
            is_active=is_active
        )
        self.db.close()

    def remove_user(self, telegram_id):
        """Removes a user from the sqlite database

        Args:
            telegram_id (int): The telegram_id of a user.
        """
        q = User.delete().where(User.telegram_id == telegram_id)
        q.execute()
        self.db.close()

    def update_user(self, telegram_id, **kwargs):
        """Updates a user to sqlite database

        Args:
            telegram_id (int): The telegram_id of a user.
            (kwargs): The attributes to be updated of a user.
        """
        _q = User.update(kwargs).where(User.telegram_id == telegram_id)
        _q.execute()
        self.db.close()

    def get_user(self, telegram_id) -> User:
        """Returns a user by its id

        Args:
            telegram_id (int): The telegram_id of a user.

        Returns:
            list: The return value. A list containing all attributes of a user.
        """
        try:
            return User.select().where(User.telegram_id == telegram_id).get()
        except User.DoesNotExist:
            pass

    def add_url(self, url):
        try:
            _feed = Feed.create(
                url=url,
                last_updated=DateHandler.get_datetime_now()
            )
        except IntegrityError:
            pass
        self.db.close()

    def remove_url(self, url):
        _q = Feed.select().where(Feed.url == url).get()
        _q.delete_instance(recursive=True)
        self.db.close()

    def update_url(self, url, **kwargs):
        _q = Feed.update(kwargs).where(Feed.url == url)
        _q.execute()
        db.close()

    def get_url(self, url) -> Feed:
        try:
            return Feed.select().where(url == url).get()
        except Feed.DoesNotExist:
            pass

    def get_all_urls(self):
        try:
            return Feed.select().get()
        except Feed.DoesNotExist:
            pass

    def add_user_bookmark(self, telegram_id, url, alias):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        self.add_url(url)  # add if not exists
        cursor.execute("INSERT OR IGNORE INTO web_user VALUES (?,?,?)",
                       (url, telegram_id, alias))

        conn.commit()
        conn.close()

    def remove_user_bookmark(self, telegram_id, url):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "DELETE FROM web_user WHERE telegram_id=(?) AND url = (?)", (telegram_id, url))
        cursor.execute(
            "DELETE FROM web WHERE web.url NOT IN (SELECT web_user.url from web_user)")

        conn.commit()
        conn.close()

    def update_user_bookmark(self, telegram_id, url, alias):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("UPDATE web_user SET alias=(?) WHERE telegram_id=(?) AND url=(?)",
                       (alias, telegram_id, url))

        conn.commit()
        conn.close()

    def get_user_bookmark(self, telegram_id, alias):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT web.url, web_user.alias, web.last_updated FROM web, web_user WHERE web_user.url = web.url AND "
            "web_user.telegram_id =" +
            str(telegram_id) + " AND web_user.alias ='" + str(alias) + "';")

        result = cursor.fetchone()

        conn.commit()
        conn.close()

        return result

    def get_urls_for_user(self, telegram_id):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT web.url, web_user.alias, web.last_updated FROM web, web_user WHERE web_user.url = web.url AND "
            "web_user.telegram_id =" +
            str(telegram_id) + ";")

        result = cursor.fetchall()

        conn.commit()
        conn.close()

        return result

    def get_users_for_url(self, url):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user.*, web_user.alias FROM user, web_user WHERE web_user.telegram_id = user.telegram_id AND "
            "web_user.url ='" + str(
                url) + "';")
        result = cursor.fetchall()

        conn.commit()
        conn.close()

        return result

    def add_chat(self, chat_info: Chat):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("INSERT OR IGNORE INTO chat VALUES (?,?,?)",
                       (chat_info.telegram_id, chat_info.title, chat_info.type))

        conn.commit()
        conn.close()

    def remove_chat(self, chat_id):
        """Remove a chat from the sqlite database

        Args:
            chat_id (int): The chat_id of a private chat, channel or group.
        """

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM chat WHERE chat_id=" +
                       str(chat_id))

        conn.commit()
        conn.close()

    def update_chat(self, chat_id, **kwargs):
        """Updates a user to sqlite database

        Args:
            chat_id (int): The chat_id of a private chat, channel or group.
            (kwargs): The attributes to be updated of a user.
        """

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        sql_command = "UPDATE chat SET "
        for key in kwargs:
            sql_command = sql_command + \
                          str(key) + "='" + str(kwargs[key]) + "', "
        sql_command = sql_command[:-2] + " WHERE chat_id=" + str(chat_id)

        cursor.execute(sql_command)

        conn.commit()
        conn.close()

    def get_chat(self, chat_id):
        """Returns a user by its id

        Args:
            chat_id (int): The chat_id of a private chat, channel or group.

        Returns:
            list: The return value. A list containing all attributes of a user.
        """
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM chat WHERE chat_id = " + str(chat_id))
        result = cursor.fetchone()

        conn.commit()
        conn.close()

        return result

    def get_all_chats(self):
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        sql_command = "SELECT * FROM chat;"

        cursor.execute(sql_command)
        result = cursor.fetchall()

        conn.commit()
        conn.close()

        return result

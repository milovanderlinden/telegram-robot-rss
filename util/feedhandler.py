import re

import feedparser


class FeedHandler(object):

    @staticmethod
    def parse_feed(url, entries=0):
        """
        Parses the given url, returns a list containing all available entries
        """

        if 1 <= entries <= 10:
            feed = feedparser.parse(url)
            return feed.entries[:entries]
        else:
            feed = feedparser.parse(url)
            return feed.entries[:4]

    @staticmethod
    def is_parsable(url):
        """
        Checks wether the given url provides a news feed. Return True if news are available, else False
        """

        if not _url_validator().match(url):
            return False

        feed = feedparser.parse(url)

        # Check if result is empty
        if not feed.entries:
            return False
        # Check if entries provide updated attribute
        for post in feed.entries:
            if not hasattr(post, "updated"):
                return False
        return True

    @staticmethod
    def format_url_string(string):
        """
        Formats a given url as string, so it matches http(s)://address.domain.
        This should be called before parsing the url, to make sure it is parsable
        """

        string = string.lower()

        if not _url_validator().match(string):
            string = "http://" + string

        return string


def _url_validator():
    return re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

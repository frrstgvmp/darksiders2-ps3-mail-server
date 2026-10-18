import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from news_api import MAX_FILE_BYTES, NEWS_PATH, NewsFeed, NewsFeedError, NewsQueryError


class NewsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'news.json'
        self.feed = NewsFeed(self.path)
        self.items = [
            {'prefix': 'Community', 'title': 'Earlier', 'body': 'First notice', 'datePosted': 100},
            {'prefix': 'Community', 'title': 'Latest', 'body': 'Second notice', 'datePosted': 200,
             'translations': {'Russian': {'title': 'Новости', 'body': 'Тестовая запись'}}}]
        self.write()

    def write(self):
        self.path.write_text(json.dumps({'items': self.items}, ensure_ascii=False), encoding='utf-8')

    @staticmethod
    def query(**extra):
        return NEWS_PATH + '?' + urlencode(dict(version='1', platform='PS3_PSN', title='Darksiders2', **extra))

    def test_positional_wire_order_localization_limit_and_empty_feed(self):
        body = self.feed.reply('GET', self.query(language='russian', limit='1'))
        self.assertEqual(json.loads(body), [0, [['Community', 'Новости', 'Тестовая запись', 200]]])
        self.assertEqual(json.loads(self.feed.reply('GET', self.query(language='Japanese'))),
                         [0, [['Community', 'Latest', 'Second notice', 200],
                              ['Community', 'Earlier', 'First notice', 100]]])
        self.assertEqual(json.loads(self.feed.reply('GET', self.query(limit='0'))), [0, []])
        self.assertEqual(NewsFeed().reply('GET', self.query()), b'[0,[]]\n')

    def test_edit_is_loaded_on_next_request_and_missing_file_is_an_error(self):
        self.items[1]['body'] = 'Updated'; self.write()
        self.assertEqual(json.loads(self.feed.reply('GET', self.query()))[1][0][2], 'Updated')
        self.path.unlink()
        with self.assertRaises(NewsFeedError): self.feed.reply('GET', self.query())

    def test_invalid_or_duplicate_query_parameters_are_rejected(self):
        for path in [NEWS_PATH, self.query() + '&version=1', self.query(limit='33'),
                     self.query(limit='-1'), self.query(limit='1') + '&limit=2',
                     self.query(language=''), self.query().replace('PS3_PSN', 'other')]:
            with self.subTest(path=path), self.assertRaises(NewsQueryError):
                self.feed.reply('GET', path)
        self.assertIsNone(self.feed.reply('POST', self.query()))
        self.assertIsNone(self.feed.reply('GET', '/thqconnect/cloud/execute'))

    def test_feed_bounds_types_and_control_characters_are_rejected(self):
        for change in [{'datePosted': 0x80000000}, {'datePosted': True},
                       {'title': 'x' * 257}, {'body': 'bad\0text'},
                       {'title': '\ud800'}, {'translations': {'Russian': {'unexpected': 'x'}}}]:
            with self.subTest(change=repr(change)):
                self.items = [{'prefix': '', 'title': 'Title', 'body': 'Body', 'datePosted': 1} | change]
                self.path.write_text(json.dumps({'items': self.items}), encoding='utf-8')
                with self.assertRaises(NewsFeedError): self.feed.entries('English')
        self.path.write_bytes(b' ' * (MAX_FILE_BYTES + 1))
        with self.assertRaises(NewsFeedError): self.feed.entries('English')
        self.path.write_text('{broken')
        with self.assertRaises(NewsFeedError): self.feed.entries('English')


if __name__ == '__main__': unittest.main()

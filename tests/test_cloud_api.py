import concurrent.futures
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from cloud_api import CloudStore


def request(profiles, operations, documents, keys, values, **extra):
    params = {'profileNames': profiles, 'ops': operations, 'docKeys': documents,
              'keys': keys, 'values': values, 'version': '1', 'platform': 'PS3_PSN',
              'title': 'Darksiders2', 'policy': '0', **extra}
    return '/thqconnect/cloud/execute?' + urlencode(params)


def rows(response):
    return json.loads(response)[1]


def received_values(document):
    entries = json.loads(document)
    if entries == {}:
        return {}
    return {key: data[0] for key, data in entries}


class CloudTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'cloud.sqlite3'
        self.store = CloudStore(self.path)

    def call(self, *args, **kw):
        return self.store.reply('GET', request(*args, **kw), b'')

    def test_send_read_restart_claim_and_retry(self):
        opaque = 'Qk9E+/opaque-payload=='
        reply = self.call('/psn/recipient', 'MAP_SET', 'TomeGift', '123', opaque)
        self.assertEqual(json.loads(rows(reply)[0][1]), {'123': opaque})
        self.store = CloudStore(self.path)
        reply = self.call('/psn/RECIPIENT', 'MAP_GET', 'TomeGift', '', '')
        self.assertEqual(received_values(rows(reply)[0][1]), {'123': opaque})
        for _ in range(2):
            self.assertEqual(json.loads(rows(self.call('/psn/recipient', 'MAP_REMOVE', 'TomeGift', '123', ''))[0][1]), {})
        self.store = CloudStore(self.path)
        self.assertEqual(json.loads(rows(self.call('/psn/recipient', 'MAP_GET', 'TomeGift', '', ''))[0][1]), {})

    def test_startup_batches_preserve_queued_gift(self):
        self.call('/psn/recipient', 'MAP_SET', 'TomeGift', 'gift', 'unchanged')
        reply = self.call('/psn/recipient,/psn/recipient', 'GET,GET', 'TomeGift,GameToWeb', ',', ',',
                          policy='0,0', worldPerms='-1,-1', friendPerms='-1,-1')
        self.assertEqual(len(rows(reply)), 2)
        self.assertEqual(json.loads(rows(reply)[0][1]), {'gift': 'unchanged'})
        reply = self.call('/psn/recipient,/psn/recipient', 'SET,SET', 'TomeGift,GameToWeb', ',', ',',
                          policy='1,1', worldPerms='2,2', friendPerms='0,0')
        self.assertEqual(json.loads(rows(reply)[0][1]), {'gift': 'unchanged'})
        self.assertEqual(rows(reply)[0][2], 1)

    def test_invalid_batch_does_not_partially_write(self):
        reply = self.call('/psn/a,/psn/a', 'MAP_SET,UNKNOWN', 'TomeGift,TomeGift', 'one,two', 'v1,v2')
        self.assertIsNone(reply)
        self.assertEqual(json.loads(rows(self.call('/psn/a', 'MAP_GET', 'TomeGift', '', ''))[0][1]), {})

    def test_rollback_on_later_corrupt_document(self):
        import sqlite3
        with sqlite3.connect(self.path) as conn:
            conn.execute('INSERT INTO documents VALUES(?,?,?,?,?,?)', ('/psn/a', 'GameToWeb', 'invalid json', 0, 0, ''))
        with self.assertRaises(ValueError):
            self.call('/psn/a,/psn/a', 'MAP_SET,MAP_GET', 'TomeGift,GameToWeb', 'gift,', 'payload,')
        self.assertEqual(json.loads(rows(self.call('/psn/a', 'MAP_GET', 'TomeGift', '', ''))[0][1]), {})

    def test_parallel_writes_through_separate_instances_keep_all_gifts(self):
        stores = [CloudStore(self.path) for _ in range(4)]
        def put(index):
            response = stores[index % 4].reply('GET', request('/psn/a', 'MAP_SET', 'TomeGift', str(index), f'value{index}'), b'')
            self.assertIsNotNone(response)
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(put, range(32)))
        mapping = received_values(rows(self.call('/psn/a', 'MAP_GET', 'TomeGift', '', ''))[0][1])
        self.assertEqual(mapping, {str(i): f'value{i}' for i in range(32)})

    def test_post_form_and_document_reset(self):
        params = request('/psn/a', 'MAP_SET', 'GameToWeb', 'stats', 'opaque').split('?', 1)[1].encode()
        self.assertIsNotNone(self.store.reply('POST', '/thqconnect/cloud/execute', params))
        self.assertIsNotNone(self.call('/psn/a', 'REMOVE', 'GameToWeb', '', ''))
        self.assertEqual(json.loads(rows(self.call('/psn/a', 'GET', 'GameToWeb', '', ''))[0][1]), {})


if __name__ == '__main__':
    unittest.main()

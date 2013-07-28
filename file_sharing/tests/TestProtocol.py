#/usr/bin/python


import unittest

import sys, os
sys.path.append(os.path.abspath(sys.path[0]) + '/../')

import fshare_protocol

class TestProtocol(unittest.TestCase):

    def setUp(self):
        self.protocol = fshare_protocol.Protocol('test@gajim.org/test')

    def test_request(self):
        iq = self.protocol.request('peer@gajim.org/test', '1234', 'documents/test2.txt')
        self.assertEqual(iq.getType(), 'get')
        self.assertNotEqual(iq.getID(), None)
        self.assertEqual(iq.getQuery().getName(), 'query')
        self.assertEqual(iq.getQuery().getNamespace(), fshare_protocol.NS_FILE_SHARING)
        self.assertEqual(iq.getQuery().getAttr('node'), 'documents/test2.txt')

    def test_offer(self):
        pass

    def test_reply(self):
        pass


if __name__ == '__main__':
    unittest.main()

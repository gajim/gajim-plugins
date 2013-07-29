#/usr/bin/python


import unittest

import sys, os
sys.path.append(os.path.abspath(sys.path[0]) + '/../')

import fshare_protocol
import nbxmpp

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

    def test_buildFileNode(self):
        file_info = {'name' : 'test2.text',
                     'date' : '00000',
                     'desc' : 'test',
                     'hash' : '00000',
                     'size' : '00000',
                     'type' : 'file'
                     }
        node = self.protocol.buildFileNode(file_info)
        self.assertEqual(node.getName(), 'file')
        self.assertEqual(node.getNamespace(), nbxmpp.NS_JINGLE_FILE_TRANSFER)
        self.assertEqual(len(node.getChildren()), 5)

    def test_offer(self):
        items = [ {'name' : 'test2.text',
                   'date' : '00000',
                   'desc' : 'test',
                   'hash' : '00000',
                   'size' : '00000',
                   'type' : 'file'
                  },
                  {
                   'name' : 'secret docs',
                   'type' : 'directory'
                  }
                ]
        iq = self.protocol.offer('1234', 'peer@gajim.org/test', 
                'documents', items)
        self.assertEqual(iq.getType(), 'result')
        self.assertNotEqual(iq.getID(), None)
        self.assertEqual(iq.getQuery().getName(), 'query')
        self.assertEqual(iq.getQuery().getNamespace(), fshare_protocol.NS_FILE_SHARING)
        self.assertEqual(iq.getQuery().getAttr('node'), 'documents')
        node = iq.getQuery()
        self.assertEqual(len(node.getChildren()), 2)



    def test_reply(self):
        pass


if __name__ == '__main__':
    unittest.main()

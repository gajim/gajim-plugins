#/usr/bin/python


import unittest
from mock import Mock
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
                     'desc' : 'test',
                     'hash' : '00000',
                     'size' : '00000',
                     'type' : 'file'
                     }
        node = self.protocol.buildFileNode(file_info)
        self.assertEqual(node.getName(), 'file')
        self.assertEqual(node.getNamespace(), nbxmpp.NS_JINGLE_FILE_TRANSFER)
        self.assertEqual(len(node.getChildren()), 4)

    def test_offer(self):
        items = [ {'name' : 'test2.text',
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


# Mock modules
fshare_protocol.gajim = Mock()
fshare_protocol.helpers = Mock()

class TestProtocolDispatcher(unittest.TestCase):

    def setUp(self):
        self.account = 'test@gajim.org/test'
        self.protocol = fshare_protocol.Protocol(self.account)
        testc = {self.account : Mock()}
        fshare_protocol.gajim.connections = testc
        self.dispatcher = fshare_protocol.ProtocolDispatcher(
                self.account, Mock())

    def test_handler(self):
        iq = self.protocol.request('peer@gajim.org/test', '1234', 
                'documents/test2.txt')
        #offer = self.dispatcher.on_offer
        request = self.dispatcher.on_request
        #self.dispatcher.on_offer = Mock()
        self.dispatcher.on_request = Mock()
        self.dispatcher.handler(iq, 'peer@gajim.org/test')
        assert(self.dispatcher.on_request.called)
        self.dispatcher.on_request = request 

    def test_on_offer(self):
        items = [ {'name' : 'test2.text',
                   'type' : 'file'
                  },
                  {
                   'name' : 'secret docs',
                   'type' : 'directory'
                  }
                ]
        iq = self.protocol.offer('1234', 'peer@gajim.org/test', 
                'documents', items)
        offered_files = self.dispatcher.on_offer(iq, 'peer@gajim.org/test')
        self.assertEqual(len(offered_files), 2)


    def test_on_request(self):
        iq = self.protocol.request('peer@gajim.org/test', '1234', 
                'documents')
        response = self.dispatcher.on_request(iq, 'peer@gajim.org/test')
        self.assertEqual(response.getType(), 'result')
        self.assertNotEqual(response.getID(), None)
        self.assertEqual(response.getQuery().getName(), 'query')
        self.assertEqual(response.getQuery().getNamespace(), fshare_protocol.NS_FILE_SHARING)
        self.assertEqual(response.getQuery().getAttr('node'), 'documents')
        node = response.getQuery()
        self.assertEqual(len(node.getChildren()), 0)



if __name__ == '__main__':
    unittest.main()


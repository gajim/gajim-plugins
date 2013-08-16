import nbxmpp
from nbxmpp import Hashes

try:
    from common import helpers
    from common import gajim
except ImportError:
    print "Import Error: Ignore if we are testing"

# Namespace for file sharing
NS_FILE_SHARING = 'urn:xmpp:fis'


class Protocol():
    '''
    Creates and extracts information from stanzas
    '''


    def __init__(self, ourjid):
        # set our jid with resource
        self.ourjid = ourjid

    def request(self, contact, stanzaID, path=None):
        iq = nbxmpp.Iq(typ='get', to=contact, frm=self.ourjid)
        iq.setID(stanzaID)
        query = iq.setQuery()
        query.setNamespace(NS_FILE_SHARING)
        if path:
            query.setAttr('node', path)
        return iq

    def buildFileNode(self, file_info):
        node = nbxmpp.Node(tag='file')
        node.setNamespace(nbxmpp.NS_JINGLE_FILE_TRANSFER)
        if not 'name' in file_info:
            raise Exception("Child name is required.")
        node.addChild(name='name').setData(file_info['name'])
        if 'date' in file_info:
            node.addChild(name='date').setData(file_info['date'])
        if 'desc' in file_info:
            node.addChild(name='desc').setData(file_info['desc'])
        if 'size' in file_info:
            node.addChild(name='size').setData(file_info['size'])
        if 'hash' in file_info:
            h = Hashes()
            h.addHash(file_info['hash'], 'sha-1')
            node.addChild(node=h)
        return node


    def offer(self, id_, contact, node, items):
        iq = nbxmpp.Iq(typ='result', to=contact, frm=self.ourjid,
                     attrs={'id': id_})
        query = iq.setQuery()
        query.setNamespace(NS_FILE_SHARING)
        if node:
            query.setAttr('node', node)
        for item in items:
            if item['type'] == 'file':
                fn = self.buildFileNode(item)
                query.addChild(node=fn)
            elif item['type'] == 'directory':
                query.addChild(name='directory',  attrs={'name': item['name']})
            else:
                raise Exception("Unexpected Type")
        return iq

class ProtocolDispatcher():
    '''
    Sends and receives stanzas
    '''


    def __init__(self, account, plugin):
        self.account = account
        self.plugin = plugin
        self.conn = gajim.connections[self.account]
        # get our jid with resource
        self.ourjid = gajim.get_jid_from_account(self.account)
        self.fsw = None


    def set_window(self, fsw):
        self.fsw = fsw


    def handler(self, stanza, fjid):
        # handles incoming match stanza
        # TODO: Stanza checking
        if stanza.getType() == 'get':
            self.on_request(stanza, fjid)
        elif stanza.getType() == 'result':
            return self.on_offer(stanza, fjid)
        else:
            # TODO: reply with malformed stanza error
            pass

    def on_request(self, stanza, fjid):
        node = stanza.getQuery().getAttr('node')
        jid = gajim.get_jid_without_resource(fjid)
        result = self.plugin.database.get_file(self.account, jid, None, node)
        return


        if stanza.getTag('error'):
            # TODO: better handle this
            return -1
        jid = gajim.get_jid_without_resource(fjid)
        req = stanza.getTag('match').getTag('request')
        if req.getTag('directory') and not \
                req.getTag('directory').getChildren():
            # We just received a toplevel directory request
            files = self.plugin.database.get_toplevel_files(self.account, jid)
            response = self.offer(stanza.getID(), fjid, files)
            self.conn.connection.send(response)
            return response
        elif req.getTag('directory') and req.getTag('directory').getTag('name'):
            dir_ = req.getTag('directory').getTag('name').getData()[1:]
            files = self.plugin.database.get_files_from_dir(self.account, jid, dir_)
            response = self.offer(stanza.getID(), fjid, files)
            self.conn.connection.send(response)
            return response

    def on_offer(self, stanza, fjid):
        offered = []
        query = stanza.getQuery()
        for child in query.getChildren():
            if child.getName() == 'directory':
                offered.append({'name' : child.getAttr('name'),
                                'type' : 'directory'})
            elif child.getName() == 'file':
                attrs = {'type' : 'file'}
                grandchildren = child.getChildren()
                for grandchild in grandchildren:
                    attrs[grandchild.getName()] = grandchild.getData()
                offered.append(attrs)
            else:
                print 'File sharing. Cant handle unknown type: ' + str(child)
        return offered


def get_files_info(stanza):
    # Crawls the stanza in search for file and dir structure.
    files = []
    dirs = []
    children = stanza.getTag('match').getTag('offer').getChildren()
    for c in children:
        if c.getName() == 'file':
            f = {'name' : \
                    c.getTag('name').getData()[1:] if c.getTag('name') else '',
                 'size' : c.getTag('size').getData() if c.getTag('size') else '',
                 'date' : c.getTag('date').getData() if c.getTag('date') else '',
                 'desc' : c.getTag('desc').getData() if c.getTag('desc') else '',
                 # TODO: handle different hash algo
                 'hash' : c.getTag('hash').getData() if c.getTag('hash') else '',
                }
            files.append(f)
        else:
            dirname = c.getTag('name')
            if dirname is None:
                return None
            dirs.append(dirname.getData()[1:])
    return (files, dirs)


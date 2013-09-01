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


    def convert_dbformat(self, records):
        # Converts db output format to the one expected by the Protocol methods
        formatted = []
        for record in records:
            r = {'name' : record[0]}
            if record[-1] == 0:
                r['type'] = 'file'
                if record[1] != None or record[1] != '':
                    r['hash'] = record[1]
                if record[2] != None or record[2] != '':
                    r['size'] = record[2]
                if record[3] != None or record[3] != '':
                    r['desc'] = record[3]
                if record[4] != None or record[4] != '':
                    r['date'] = record[4]
            else:
                r['type'] = 'directory'
            formatted.append(r)
        return formatted

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

class ProtocolDispatcher(Protocol):
    '''
    Sends and receives stanzas
    '''


    def __init__(self, account, plugin):
        self.account = account
        self.plugin = plugin
        self.conn = gajim.connections[self.account]
        # get our jid with resource
        ourjid = gajim.get_jid_from_account(self.account)
        Protocol.__init__(self, ourjid)
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


    def on_toplevel_request(self, stanza, jid):
        roots = self.plugin.database.get_toplevel_dirs(self.account, jid)
        items = []
        for root in roots:
            items.append({'type' : 'directory',
                          'name' : root[0]
                        })
        return self.offer(stanza.getID(), jid, None, items)

    def on_dir_request(self, stanza, fjid, jid, dir_):
        result = self.plugin.database.get_files_from_dir(self.account, jid, dir_)
        result = self.convert_dbformat(result)
        return self.offer(stanza.getID(), fjid, dir_, result)

    def on_request(self, stanza, fjid):
        jid = get_jid_without_resource(fjid)
        if stanza.getTag('error'):
            # TODO: better handle this
            return -1
        node = stanza.getQuery().getAttr('node')
        if node is None:
            return self.on_toplevel_request(stanza, jid)
        result = self.plugin.database.get_file(self.account, jid, None, node)
        if result == []:
            return self.offer(stanza.getID(), fjid, node, result)
        if result[-1] == 1:
            # The peer asked for the content of a dir
            reply = self.on_dir_request(self, stanza, fjid)
        else:
            # The peer asked for more information on a file
            # TODO: Refactor, make method to convert db format to expect file
            # format
            file_ = [{'type' : 'file',
                     'name' : result[0].split('/')[-1],
                     'hash' : result[1],
                     'size' : result[2],
                     'desc' : result[3],
                     'date' : result[4],
                    }]
            reply = self.offer(stanza.getID(), fjid, node, file_)
        return reply

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



def get_jid_without_resource(jid):
    return jid.split('/')[0]

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


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

    def buildReply(self, typ, stanza):
        iq = nbxmpp.Iq(typ, to=stanza.getFrom(), frm=stanza.getTo(),
            attrs={'id': stanza.getID()})
        iq.addChild(name='match', namespace=NS_FILE_SHARING)
        return iq

    def buildFileNode(self, file_info):
        node = nbxmpp.Node(tag='file')
        node.setNamespace(nbxmpp.NS_JINGLE_FILE_TRANSFER)
        if not file_info['name']:
            raise Exception("Child name is required.")
        node.addChild(name='name').setData(file_info['name'])
        if file_info['date']:
            node.addChild(name='date').setData(file_info['date'])
        if file_info['desc']:
            node.addChild(name='desc').setData(file_info['desc'])
        if file_info['size']:
            node.addChild(name='size').setData(file_info['size'])
        if file_info['hash']:
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


    def set_window(self, window):
        self.fsw = window


    def handler(self, stanza):
        # handles incoming match stanza
        if stanza.getTag('match').getTag('offer'):
            self.on_offer(stanza)
        elif stanza.getTag('match').getTag('request'):
            self.on_request(stanza)
        else:
            # TODO: reply with malformed stanza error
            pass

    def on_request(self, stanza):
        try:
            fjid = helpers.get_full_jid_from_iq(stanza)
        except helpers.InvalidFormat:
            # A message from a non-valid JID arrived, it has been ignored.
            return
        if stanza.getTag('error'):
            # TODO: better handle this
            return
        jid = gajim.get_jid_without_resource(fjid)
        req = stanza.getTag('match').getTag('request')
        if req.getTag('directory') and not \
                req.getTag('directory').getChildren():
            # We just received a toplevel directory request
            files = self.plugin.database.get_toplevel_files(self.account, jid)
            response = self.offer(stanza.getID(), fjid, files)
            self.conn.connection.send(response)
        elif req.getTag('directory') and req.getTag('directory').getTag('name'):
            dir_ = req.getTag('directory').getTag('name').getData()[1:]
            files = self.plugin.database.get_files_from_dir(self.account, jid, dir_)
            response = self.offer(stanza.getID(), fjid, files)
            self.conn.connection.send(response)

    def on_offer(self, stanza):
        # We just got a stanza offering files
        fjid = helpers.get_full_jid_from_iq(stanza)
        info = get_files_info(stanza)
        if fjid not in self.fsw.browse_jid or not info:
            # We weren't expecting anything from this contact, do nothing
            # Or we didn't receive any offering files
            return
        flist = []
        for f in info[0]:
            flist.append(f['name'])
        flist.extend(info[1])
        self.fsw.browse_fref = self.fsw.add_file_list(flist, self.fsw.ts_search,
                                              self.fsw.browse_fref,
                                              self.fsw.browse_jid[fjid]
                                             )
        for f in info[0]:
            iter_ = self.fsw.browse_fref[f['name']]
            path = self.fsw.ts_search.get_path(iter_)
            self.fsw.brw_file_info[path] = (f['name'], f['date'], f['size'],
                                            f['hash'], f['desc'])

        # TODO: add tooltip
        '''
        for f in info[0]:
            r = self.fsw.browse_fref[f['name']]
            path = self.fsw.ts_search.get_path(r)
            # AM HERE WORKING ON THE TOOLTIP
            tooltip.set_text('noooo')
            self.fsw.tv_search.set_tooltip_row(tooltip, path)
        '''
        for dir_ in info[1]:
            if dir_ not in self.fsw.empty_row_child:
                parent = self.fsw.browse_fref[dir_]
                row = self.fsw.ts_search.append(parent, ('',))
                self.fsw.empty_row_child[dir_] = row



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


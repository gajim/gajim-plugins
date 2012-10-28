from common import xmpp
from common import helpers
from common import gajim
from common import XMPPDispatcher
from common.xmpp import Hashes
import database
# Namespace for file sharing
NS_FILE_SHARING = 'http://gajim.org/protocol/filesharing'

class protocol():

    def __init__(self, account):
        self.account = account
        self.conn = gajim.connections[self.account]
        # get our jid with resource
        self.ourjid = gajim.get_jid_from_account(self.account)
        self.fsw = None

    def set_window(self, window):
        self.fsw = window

    def request(self, contact, name=None, isFile=False):
        iq = xmpp.Iq(typ='get', to=contact, frm=self.ourjid)
        match = iq.addChild(name='match', namespace=NS_FILE_SHARING)
        request = match.addChild(name='request')
        if not isFile and name is None:
            request.addChild(name='directory')
        elif not isFile and name is not None:
            dir_ = request.addChild(name='directory')
            dir_.addChild(name='name').addData('/' + name)
        elif isFile:
            pass
        return iq

    def __buildReply(self, typ, stanza):
        iq = xmpp.Iq(typ, to=stanza.getFrom(), frm=stanza.getTo(),
            attrs={'id': stanza.getID()})
        iq.addChild(name='match', namespace=NS_FILE_SHARING)
        return iq

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
            files = database.get_toplevel_files(self.account, jid)
            response = self.offer(stanza.getID(), fjid, files)
            self.conn.connection.send(response)
        elif req.getTag('directory') and req.getTag('directory').getTag('name'):
            dir_ = req.getTag('directory').getTag('name').getData()[1:]
            files = database.get_files_from_dir(self.account, jid, dir_)
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

    def handler(self, stanza):
        # handles incoming match stanza
        if stanza.getTag('match').getTag('offer'):
            self.on_offer(stanza)
        elif stanza.getTag('match').getTag('request'):
            self.on_request(stanza)
        else:
            # TODO: reply with malformed stanza error
            pass

    def offer(self, id_, contact, items):
        iq = xmpp.Iq(typ='result', to=contact, frm=self.ourjid, 
                     attrs={'id': id_})
        match = iq.addChild(name='match', namespace=NS_FILE_SHARING)
        offer = match.addChild(name='offer')
        if len(items) == 0:
            offer.addChild(name='directory')
        else:
            for i in items:
                # if it is a directory
                if i[5] == True:
                    item = offer.addChild(name='directory')
                    name = item.addChild('name')
                    name.setData('/' + i[0])
                else:
                    item = offer.addChild(name='file')
                    item.addChild('name').setData('/' + i[0])
                    if i[1] != '':
                        h = Hashes()
                        h.addHash(i[1], 'sha-1')
                        item.addChild(node=h)
                    item.addChild('size').setData(i[2])
                    item.addChild('desc').setData(i[3])
                    item.addChild('date').setData(i[4])
        return iq

    def set_window(self, fsw):
        self.fsw = fsw


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


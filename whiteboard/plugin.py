## plugins/whiteboard/plugin.py
##
## Copyright (C) 2009 Jeff Ling <jeff.ummu AT gmail.com>
## Copyright (C) 2010 Yann Leboulanger <asterix AT lagaule.org>
##
## This file is part of Gajim.
##
## Gajim is free software; you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published
## by the Free Software Foundation; version 3 only.
##
## Gajim is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with Gajim. If not, see <http://www.gnu.org/licenses/>.
##

'''
Whiteboard plugin.

:author: Yann Leboulanger <asterix@lagaule.org>
:since: 1st November 2010
:copyright: Copyright (2010) Yann Leboulanger <asterix@lagaule.org>
:license: GPL
'''

from gajim import common
from gajim.common import helpers
from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.gajimplugin import GajimPluginException
from gajim.plugins.helpers import log_calls, log
from nbxmpp import Message
from gi.repository import Gio
from gi.repository import GLib
from gajim import chat_control
from gajim.common import ged
from gajim.common.jingle_session import JingleSession
from gajim.common.jingle_content import JingleContent
from gajim.common.jingle_transport import JingleTransport, TransportType
from gajim import dialogs
from .whiteboard_widget import Whiteboard, HAS_GOOCANVAS

# Since Gajim 1.1.0 _() has to be imported
try:
    from gajim.common.i18n import _
except ImportError:
    pass

NS_JINGLE_XHTML = 'urn:xmpp:tmp:jingle:apps:xhtml'
NS_JINGLE_SXE = 'urn:xmpp:tmp:jingle:transports:sxe'
NS_SXE = 'urn:xmpp:sxe:0'

class WhiteboardPlugin(GajimPlugin):
    @log_calls('WhiteboardPlugin')
    def init(self):
        self.config_dialog = None
        self.events_handlers = {
            'jingle-request-received': (ged.GUI1, self._nec_jingle_received),
            'jingle-connected-received': (ged.GUI1, self._nec_jingle_connected),
            'jingle-disconnected-received': (ged.GUI1,
                self._nec_jingle_disconnected),
            'raw-message-received': (ged.GUI1, self._nec_raw_message),
        }
        self.gui_extension_points = {
            'chat_control' : (self.connect_with_chat_control,
                self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                None),
            'update_caps': (self._update_caps, None),
        }
        self.controls = []
        self.sid = None
        self.announce_caps = True

    @log_calls('WhiteboardPlugin')
    def _update_caps(self, account):
        if not self.announce_caps:
            return
        if NS_JINGLE_SXE not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(NS_JINGLE_SXE)
        if NS_SXE not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(NS_SXE)

    @log_calls('WhiteboardPlugin')
    def activate(self):
        if not HAS_GOOCANVAS:
            raise GajimPluginException('python-pygoocanvas is missing!')
        for account in app.caps_hash:
            if app.caps_hash[account] != '':
                self.announce_caps = True
                helpers.update_optional_features(account)

    @log_calls('WhiteboardPlugin')
    def deactivate(self):
        self.announce_caps = False
        helpers.update_optional_features()

    @log_calls('WhiteboardPlugin')
    def connect_with_chat_control(self, control):
        for base in self.controls:
            if base.chat_control == control:
                self.controls.remove(base)

        if isinstance(control, chat_control.ChatControl):
            base = Base(self, control)
            self.controls.append(base)

    @log_calls('WhiteboardPlugin')
    def disconnect_from_chat_control(self, chat_control):
        for base in self.controls:
            base.disconnect_from_chat_control()
        self.controls = []

    @log_calls('WhiteboardPlugin')
    def update_button_state(self, control):
        for base in self.controls:
            if base.chat_control == control:
                if control.contact.supports(NS_JINGLE_SXE) and \
                control.contact.supports(NS_SXE):
                    base.enable_action(True)
                else:
                    base.enable_action(False)

    @log_calls('WhiteboardPlugin')
    def show_request_dialog(self, account, fjid, jid, sid, content_types):
        def on_ok():
            session = app.connections[account].get_jingle_session(fjid, sid)
            self.sid = session.sid
            if not session.accepted:
                session.approve_session()
            for content in content_types:
                session.approve_content('xhtml')
            for _jid in (fjid, jid):
                ctrl = app.interface.msg_win_mgr.get_control(_jid, account)
                if ctrl:
                    break
            if not ctrl:
                # create it
                app.interface.new_chat_from_jid(account, jid)
                ctrl = app.interface.msg_win_mgr.get_control(jid, account)
            session = session.contents[('initiator', 'xhtml')]
            ctrl.draw_whiteboard(session)

        def on_cancel():
            session = app.connections[account].get_jingle_session(fjid, sid)
            session.decline_session()

        contact = app.contacts.get_first_contact_from_jid(account, jid)
        if contact:
            name = contact.get_shown_name()
        else:
            name = jid
        pritext = _('Incoming Whiteboard')
        sectext = _('%(name)s (%(jid)s) wants to start a whiteboard with '
            'you. Do you want to accept?') % {'name': name, 'jid': jid}
        dialog = dialogs.NonModalConfirmationDialog(pritext, sectext=sectext,
            on_response_ok=on_ok, on_response_cancel=on_cancel)
        dialog.popup()

    @log_calls('WhiteboardPlugin')
    def _nec_jingle_received(self, obj):
        if not HAS_GOOCANVAS:
            return
        content_types = obj.contents.media
        if content_types != 'xhtml':
            return
        self.show_request_dialog(obj.conn.name, obj.fjid, obj.jid, obj.sid,
            content_types)

    @log_calls('WhiteboardPlugin')
    def _nec_jingle_connected(self, obj):
        if not HAS_GOOCANVAS:
            return
        account = obj.conn.name
        ctrl = (app.interface.msg_win_mgr.get_control(obj.fjid, account)
            or app.interface.msg_win_mgr.get_control(obj.jid, account))
        if not ctrl:
            return
        session = app.connections[obj.conn.name].get_jingle_session(obj.fjid,
            obj.sid)

        if ('initiator', 'xhtml') not in session.contents:
            return

        session = session.contents[('initiator', 'xhtml')]
        ctrl.draw_whiteboard(session)

    @log_calls('WhiteboardPlugin')
    def _nec_jingle_disconnected(self, obj):
        for base in self.controls:
            if base.sid == obj.sid:
                base.stop_whiteboard(reason = obj.reason)

    @log_calls('WhiteboardPlugin')
    def _nec_raw_message(self, obj):
        if not HAS_GOOCANVAS:
            return
        if obj.stanza.getTag('sxe', namespace=NS_SXE):
            account = obj.conn.name

            try:
                fjid = helpers.get_full_jid_from_iq(obj.stanza)
            except helpers.InvalidFormat:
                obj.conn.dispatch('ERROR', (_('Invalid Jabber ID'),
                    _('A message from a non-valid JID arrived, it has been '
                      'ignored.')))

            jid = app.get_jid_without_resource(fjid)
            ctrl = (app.interface.msg_win_mgr.get_control(fjid, account)
                or app.interface.msg_win_mgr.get_control(jid, account))
            if not ctrl:
                return
            sxe = obj.stanza.getTag('sxe')
            if not sxe:
                return
            sid = sxe.getAttr('session')
            if (jid, sid) not in obj.conn._sessions:
                pass
#                newjingle = JingleSession(con=self, weinitiate=False, jid=jid, sid=sid)
#                self.addJingle(newjingle)

            # we already have such session in dispatcher...
            session = obj.conn.get_jingle_session(fjid, sid)
            cn = session.contents[('initiator', 'xhtml')]
            error = obj.stanza.getTag('error')
            if error:
                action = 'iq-error'
            else:
                action = 'edit'

            cn.on_stanza(obj.stanza, sxe, error, action)
#        def __editCB(self, stanza, content, error, action):
            #new_tags = sxe.getTags('new')
            #remove_tags = sxe.getTags('remove')

            #if new_tags is not None:
                ## Process new elements
                #for tag in new_tags:
                    #if tag.getAttr('type') == 'element':
                        #ctrl.whiteboard.recieve_element(tag)
                    #elif tag.getAttr('type') == 'attr':
                        #ctrl.whiteboard.recieve_attr(tag)
                #ctrl.whiteboard.apply_new()

            #if remove_tags is not None:
                ## Delete rids
                #for tag in remove_tags:
                    #target = tag.getAttr('target')
                    #ctrl.whiteboard.image.del_rid(target)

            # Stop propagating this event, it's handled
            return True


class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.chat_control.draw_whiteboard = self.draw_whiteboard
        self.contact = self.chat_control.contact
        self.account = self.chat_control.account
        self.jid = self.contact.get_full_jid()
        self.add_action()
        self.whiteboard = None
        self.sid = None

    def add_action(self):
        action_name = 'toggle-whiteboard-' + self.chat_control.control_id
        act = Gio.SimpleAction.new_stateful(
            action_name, None, GLib.Variant.new_boolean(False))
        act.connect('change-state', self.on_whiteboard_button_toggled)
        self.chat_control.parent_win.window.add_action(act)

        self.chat_control.control_menu.append(
            'WhiteBoard', 'win.' + action_name)

    def enable_action(self, state):
        win = self.chat_control.parent_win.window
        action_name = 'toggle-whiteboard-' + self.chat_control.control_id
        win.lookup_action(action_name).set_enabled(state)

    def draw_whiteboard(self, content):
        hbox = self.chat_control.xml.get_object('chat_control_hbox')
        if len(hbox.get_children()) == 1:
            self.whiteboard = Whiteboard(self.account, self.contact, content,
                self.plugin)
            # set minimum size
            self.whiteboard.hbox.set_size_request(300, 0)
            hbox.pack_start(self.whiteboard.hbox, False, False, 0)
            self.whiteboard.hbox.show_all()
            self.enable_action(True)
            content.control = self
            self.sid = content.session.sid

    def on_whiteboard_button_toggled(self, action, param):
        """
        Popup whiteboard
        """
        action.set_state(param)
        state = param.get_boolean()
        if state:
            if not self.whiteboard:
                self.start_whiteboard()
        else:
            self.stop_whiteboard()

    def start_whiteboard(self):
        conn = app.connections[self.chat_control.account]
        jingle = JingleSession(conn, weinitiate=True, jid=self.jid)
        self.sid = jingle.sid
        conn._sessions[jingle.sid] = jingle
        content = JingleWhiteboard(jingle)
        content.control = self
        jingle.add_content('xhtml', content)
        jingle.start_session()

    def stop_whiteboard(self, reason=None):
        conn = app.connections[self.chat_control.account]
        self.sid = None
        session = conn.get_jingle_session(self.jid, media='xhtml')
        if session:
            session.end_session()
        self.enable_action(False)
        if reason:
            txt = _('Whiteboard stopped: %(reason)s') % {'reason': reason}
            self.chat_control.print_conversation(txt, 'info')
        if not self.whiteboard:
            return
        hbox = self.chat_control.xml.get_object('chat_control_hbox')
        if self.whiteboard.hbox in hbox.get_children():
            if hasattr(self.whiteboard, 'hbox'):
                hbox.remove(self.whiteboard.hbox)
                self.whiteboard = None

    def disconnect_from_chat_control(self):
        menu = self.chat_control.control_menu
        for i in range(menu.get_n_items()):
            label = menu.get_item_attribute_value(i, 'label')
            if label.get_string() == 'WhiteBoard':
                menu.remove(i)
                break

class JingleWhiteboard(JingleContent):
    ''' Jingle Whiteboard sessions consist of xhtml content'''
    def __init__(self, session, transport=None, senders=None):
        if not transport:
            transport = JingleTransportSXE()
        JingleContent.__init__(self, session, transport, senders)
        self.media = 'xhtml'
        self.negotiated = True # there is nothing to negotiate
        self.last_rid = 0
        self.callbacks['session-accept'] += [self._sessionAcceptCB]
        self.callbacks['session-terminate'] += [self._stop]
        self.callbacks['session-terminate-sent'] += [self._stop]
        self.callbacks['edit'] = [self._EditCB]

    @log_calls('WhiteboardPlugin')
    def _EditCB(self, stanza, content, error, action):
        new_tags = content.getTags('new')
        remove_tags = content.getTags('remove')
        if not self.control.whiteboard:
            return

        if new_tags is not None:
            # Process new elements
            for tag in new_tags:
                if tag.getAttr('type') == 'element':
                    self.control.whiteboard.recieve_element(tag)
                elif tag.getAttr('type') == 'attr':
                    self.control.whiteboard.recieve_attr(tag)
            self.control.whiteboard.apply_new()

        if remove_tags is not None:
            # Delete rids
            for tag in remove_tags:
                target = tag.getAttr('target')
                self.control.whiteboard.image.del_rid(target)

    @log_calls('WhiteboardPlugin')
    def _sessionAcceptCB(self, stanza, content, error, action):
        log.debug('session accepted')
        self.session.connection.dispatch('WHITEBOARD_ACCEPTED',
            (self.session.peerjid, self.session.sid))

    def generate_rids(self, x):
        # generates x number of rids and returns in list
        rids = []
        for x in range(x):
            rids.append(str(self.last_rid))
            self.last_rid += 1
        return rids

    @log_calls('WhiteboardPlugin')
    def send_whiteboard_node(self, items, rids):
        # takes int rid and dict items and sends it as a node
        # sends new item
        jid = self.session.peerjid
        sid = self.session.sid
        message = Message(to=jid)
        sxe = message.addChild(name='sxe', attrs={'session': sid},
            namespace=NS_SXE)

        for x in rids:
            if items[x]['type'] == 'element':
                parent = x
                attrs = {'rid': x,
                     'name': items[x]['data'][0].getName(),
                     'type': items[x]['type']}
                sxe.addChild(name='new', attrs=attrs)
            if items[x]['type'] == 'attr':
                attr_name = items[x]['data']
                chdata = items[parent]['data'][0].getAttr(attr_name)
                attrs = {'rid': x,
                     'name': attr_name,
                     'type': items[x]['type'],
                     'chdata': chdata,
                     'parent': parent}
                sxe.addChild(name='new', attrs=attrs)
        self.session.connection.connection.send(message)

    @log_calls('WhiteboardPlugin')
    def delete_whiteboard_node(self, rids):
        message = Message(to=self.session.peerjid)
        sxe = message.addChild(name='sxe', attrs={'session': self.session.sid},
            namespace=NS_SXE)

        for x in rids:
            sxe.addChild(name='remove', attrs = {'target': x})
        self.session.connection.connection.send(message)

    def send_items(self, items, rids):
        # recieves dict items and a list of rids of items to send
        # TODO: is there a less clumsy way that doesn't involve passing
        # whole list
        self.send_whiteboard_node(items, rids)

    def del_item(self, rids):
        self.delete_whiteboard_node(rids)

    def encode(self, xml):
        # encodes it sendable string
        return 'data:text/xml,' + urllib.quote(xml)

    def _fill_content(self, content):
        content.addChild(NS_JINGLE_XHTML + ' description')

    def _stop(self, *things):
        pass

    def __del__(self):
        pass

def get_content(desc):
    return JingleWhiteboard

common.jingle_content.contents[NS_JINGLE_XHTML] = get_content

class JingleTransportSXE(JingleTransport):
    def __init__(self, node=None):
        JingleTransport.__init__(self, TransportType.SOCKS5)

    def make_transport(self, candidates=None):
        transport = JingleTransport.make_transport(self, candidates)
        transport.setNamespace(NS_JINGLE_SXE)
        transport.setTagData('host', 'TODO')
        return transport

common.jingle_transport.transports[NS_JINGLE_SXE] = JingleTransportSXE

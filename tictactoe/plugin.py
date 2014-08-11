## plugins/tictactoe/plugin.py
##
## Copyright (C) 2011 Yann Leboulanger <asterix AT lagaule.org>
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
Tictactoe plugin.

:author: Yann Leboulanger <asterix@lagaule.org>
:since: 21 November 2011
:copyright: Copyright (2011) Yann Leboulanger <asterix@lagaule.org>
:license: GPL
'''


from common import helpers
from common import gajim
from plugins import GajimPlugin
from plugins.plugin import GajimPluginException
from plugins.helpers import log_calls, log
from plugins.gui import GajimPluginConfigDialog
import nbxmpp
import gtk
from gtk import gdk
import cairo
import chat_control
from common import ged
import dialogs
from common import caps_cache
from common import stanza_session
from common.connection_handlers_events import InformationEvent

NS_GAMES = 'http://jabber.org/protocol/games'
NS_GAMES_TICTACTOE = NS_GAMES + '/tictactoe'

class TictactoePlugin(GajimPlugin):
    @log_calls('TictactoePlugin')
    def init(self):
        self.config_dialog = TictactoePluginConfigDialog(self)
        self.events_handlers = {
            'decrypted-message-received': (ged.GUI1,
                self._nec_decrypted_message_received),
        }
        self.gui_extension_points = {
            'chat_control_base' : (self.connect_with_chat_control,
                self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (self.update_button_state,
                None),
        }
        self.config_default_values = {
            'board_size': (5, ''),
        }
        self.controls = []

    @log_calls('TictactoePlugin')
    def _compute_caps_hash(self):
        for a in gajim.connections:
            gajim.caps_hash[a] = caps_cache.compute_caps_hash([
                gajim.gajim_identity], gajim.gajim_common_features + \
                gajim.gajim_optional_features[a])
            # re-send presence with new hash
            connected = gajim.connections[a].connected
            if connected > 1 and gajim.SHOW_LIST[connected] != 'invisible':
                gajim.connections[a].change_status(gajim.SHOW_LIST[connected],
                    gajim.connections[a].status)

    @log_calls('TictactoePlugin')
    def activate(self):
        if NS_GAMES not in gajim.gajim_common_features:
            gajim.gajim_common_features.append(NS_GAMES)
        if NS_GAMES_TICTACTOE not in gajim.gajim_common_features:
            gajim.gajim_common_features.append(NS_GAMES_TICTACTOE)
        self._compute_caps_hash()

    @log_calls('TictactoePlugin')
    def deactivate(self):
        if NS_GAMES_TICTACTOE in gajim.gajim_common_features:
            gajim.gajim_common_features.remove(NS_GAMES_TICTACTOE)
        if NS_GAMES in gajim.gajim_common_features:
            gajim.gajim_common_features.remove(NS_GAMES)
        self._compute_caps_hash()

    @log_calls('TictactoePlugin')
    def connect_with_chat_control(self, control):
        if isinstance(control, chat_control.ChatControl):
            base = Base(self, control)
            self.controls.append(base)
            # Already existing session?
            conn = gajim.connections[control.account]
            sessions = conn.get_sessions(control.contact.jid)
            tictactoes = [s for s in sessions if isinstance(s,
                TicTacToeSession)]
            if tictactoes:
                base.tictactoe = tictactoes[0]
                base.button.set_active(True)

    @log_calls('TictactoePlugin')
    def disconnect_from_chat_control(self, chat_control):
        for base in self.controls:
            base.disconnect_from_chat_control()
        self.controls = []

    @log_calls('TictactoePlugin')
    def update_button_state(self, control):
        for base in self.controls:
            if base.chat_control == control:
                if control.contact.supports(NS_GAMES) and \
                control.contact.supports(NS_GAMES_TICTACTOE):
                    base.button.set_sensitive(True)
                    tooltip_text = _('Play tictactoe')
                else:
                    base.button.set_sensitive(False)
                    tooltip_text = _('Client on the other side '
                        'does not support playing tictactoe')
                base.button.set_tooltip_text(tooltip_text)

    @log_calls('TictactoePlugin')
    def show_request_dialog(self, obj, session):
        def on_ok():
            session.invited(obj.stanza)

        def on_cancel():
            session.decline_invitation()

        account = obj.conn.name
        contact = gajim.contacts.get_first_contact_from_jid(account, obj.jid)
        if contact:
            name = contact.get_shown_name()
        else:
            name = obj.jid
        pritext = _('Incoming Tictactoe')
        sectext = _('%(name)s (%(jid)s) wants to play tictactoe with you. '
            'Do you want to accept?') % {'name': name, 'jid': obj.jid}
        dialog = dialogs.NonModalConfirmationDialog(pritext, sectext=sectext,
            on_response_ok=on_ok, on_response_cancel=on_cancel)
        dialog.popup()

    @log_calls('TictactoePlugin')
    def _nec_decrypted_message_received(self, obj):
        if isinstance(obj.session, TicTacToeSession):
            obj.session.received(obj.stanza)
        game_invite = obj.stanza.getTag('invite', namespace=NS_GAMES)
        if game_invite:
            account = obj.conn.name
            game = game_invite.getTag('game')
            if game and game.getAttr('var') == NS_GAMES_TICTACTOE:
                session = obj.conn.make_new_session(obj.fjid, obj.thread_id,
                    cls=TicTacToeSession)
                self.show_request_dialog(obj, session)

class Base(object):
    def __init__(self, plugin, chat_control):
        self.plugin = plugin
        self.chat_control = chat_control
        self.contact = self.chat_control.contact
        self.account = self.chat_control.account
        self.fjid = self.contact.get_full_jid()
        self.create_buttons()
        self.tictactoe = None

    def create_buttons(self):
        # create whiteboard button
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        self.button = gtk.ToggleButton(label=None, use_underline=True)
        self.button.set_property('relief', gtk.RELIEF_NONE)
        self.button.set_property('can-focus', False)
        img = gtk.Image()
        img_path = self.plugin.local_file_path('tictactoe.png')
        pixbuf = gtk.gdk.pixbuf_new_from_file(img_path)
        iconset = gtk.IconSet(pixbuf=pixbuf)
        factory = gtk.IconFactory()
        factory.add('tictactoe', iconset)
        factory.add_default()
        img.set_from_stock('tictactoe', gtk.ICON_SIZE_MENU)
        self.button.set_image(img)
        send_button = self.chat_control.xml.get_object('send_button')
        send_button_pos = actions_hbox.child_get_property(send_button,
            'position')
        actions_hbox.add_with_properties(self.button, 'position',
            send_button_pos - 1, 'expand', False)
        id_ = self.button.connect('toggled', self.on_tictactoe_button_toggled)
        self.chat_control.handlers[id_] = self.button
        self.button.show()

    def on_tictactoe_button_toggled(self, widget):
        """
        Popup whiteboard
        """
        if widget.get_active():
            if not self.tictactoe:
                self.start_tictactoe()
        else:
            self.stop_tictactoe('resign')

    def start_tictactoe(self):
        self.tictactoe = gajim.connections[self.account].make_new_session(
            self.fjid, cls=TicTacToeSession)
        self.tictactoe.base = self
        self.tictactoe.begin()

    def stop_tictactoe(self, reason=None):
        self.tictactoe.end_game(reason)
        if hasattr(self.tictactoe, 'board'):
            self.tictactoe.board.win.destroy()
        self.tictactoe = None

    def disconnect_from_chat_control(self):
        actions_hbox = self.chat_control.xml.get_object('actions_hbox')
        actions_hbox.remove(self.button)

class InvalidMove(Exception):
    pass

class TicTacToeSession(stanza_session.StanzaSession):
    def __init__(self, conn, jid, thread_id, type_):
        stanza_session.StanzaSession.__init__(self, conn, jid, thread_id, type_)
        contact = gajim.contacts.get_contact(conn.name,
            gajim.get_jid_without_resource(str(jid)))
        self.name = contact.get_shown_name()
        self.base = None
        self.control = None

    # initiate a session
    def begin(self, role_s='x'):
        self.rows = self.base.plugin.config['board_size']
        self.cols = self.base.plugin.config['board_size']

        self.role_s = role_s

        self.strike = self.base.plugin.config['board_size']

        if self.role_s == 'x':
            self.role_o = 'o'
        else:
            self.role_o = 'x'

        self.send_invitation()

        self.next_move_id = 1
        self.received = self.wait_for_invite_response

    def send_invitation(self):
        msg = nbxmpp.Message()

        invite = msg.NT.invite
        invite.setNamespace(NS_GAMES)
        invite.setAttr('type', 'new')

        game = invite.NT.game
        game.setAttr('var', NS_GAMES_TICTACTOE)

        x = nbxmpp.DataForm(typ='submit')
        f = x.setField('role')
        f.setType('list-single')
        f.setValue('x')
        f = x.setField('rows')
        f.setType('text-single')
        f.setValue(str(self.base.plugin.config['board_size']))
        f = x.setField('cols')
        f.setType('text-single')
        f.setValue(str(self.base.plugin.config['board_size']))
        f = x.setField('strike')
        f.setType('text-single')
        f.setValue(str(self.base.plugin.config['board_size']))

        game.addChild(node=x)

        self.send(msg)

    def read_invitation(self, msg):
        invite = msg.getTag('invite', namespace=NS_GAMES)
        game = invite.getTag('game')
        x = game.getTag('x', namespace='jabber:x:data')

        form = nbxmpp.DataForm(node=str(x))

        if form.getField('role'):
            self.role_o = form.getField('role').getValues()[0]
        else:
            self.role_o = 'x'

        if form.getField('rows'):
            self.rows = int(form.getField('rows').getValues()[0])
        else:
            self.rows = 3

        if form.getField('cols'):
            self.cols = int(form.getField('cols').getValues()[0])
        else:
            self.cols = 3

        # number in a row needed to win
        if form.getField('strike'):
            self.strike = int(form.getField('strike').getValues()[0])
        else:
            self.strike = 3

    # received an invitation
    def invited(self, msg):
        self.read_invitation(msg)

        # the number of the move about to be made
        self.next_move_id = 1

        # display the board
        self.board = TicTacToeBoard(self, self.rows, self.cols)

        # accept the invitation, join the game
        response = nbxmpp.Message()

        join = response.NT.join
        join.setNamespace(NS_GAMES)

        self.send(response)

        if self.role_o == 'x':
            self.role_s = 'o'

            self.their_turn()
        else:
            self.role_s = 'x'
            self.role_o = 'o'

            self.our_turn()

    # just sent an invitation, expecting a reply
    def wait_for_invite_response(self, msg):
        if msg.getTag('join', namespace=NS_GAMES):
            self.board = TicTacToeBoard(self, self.rows, self.cols)

            if self.role_s == 'x':
                self.our_turn()
            else:
                self.their_turn()

        elif msg.getTag('decline', namespace=NS_GAMES):
            gajim.nec.push_incoming_event(InformationEvent(None, conn=self.conn,
                level='info', pri_txt=_('Invitation refused'),
                sec_txt=_('%(name)s refused your invitation to play tic tac '
                'toe.') % {'name': self.name}))
            self.conn.delete_session(str(self.jid), self.thread_id)
            if self.base:
                self.base.button.set_active(False)

    def decline_invitation(self):
        msg = nbxmpp.Message()

        terminate = msg.NT.decline
        terminate.setNamespace(NS_GAMES)

        self.send(msg)

    def treat_terminate(self, msg):
        term = msg.getTag('terminate', namespace=NS_GAMES)
        if term:
            if term.getAttr('reason') == 'resign':
                self.board.state = 'resign'
            self.board.win.queue_draw()
            self.received = self.game_over
            return True

    # silently ignores any received messages
    def ignore(self, msg):
        self.treat_terminate(msg)

    def game_over(self, msg):
        invite = msg.getTag('invite', namespace=NS_GAMES)

        # ignore messages unless they're renewing the game
        if invite and invite.getAttr('type') == 'renew':
            self.invited(msg)

    def wait_for_move(self, msg):
        if self.treat_terminate(msg):
            return
        turn = msg.getTag('turn', namespace=NS_GAMES)
        move = turn.getTag('move', namespace=NS_GAMES_TICTACTOE)

        row = int(move.getAttr('row'))
        col = int(move.getAttr('col'))
        id_ = int(move.getAttr('id'))

        if id_ != self.next_move_id:
            print 'unexpected move id, lost a move somewhere?'
            return

        try:
            self.board.mark(row, col, self.role_o)
        except InvalidMove, e:
            # received an invalid move, end the game.
            self.board.cheated()
            self.end_game('cheating')
            self.received = self.game_over
            return

        # check win conditions
        if self.board.check_for_strike(self.role_o, row, col, self.strike):
            self.lost()
        elif self.board.full():
            self.drawn()
        else:
            self.next_move_id += 1

            self.our_turn()

    def is_my_turn(self):
        return self.received == self.ignore

    def our_turn(self):
        # ignore messages until we've made our move
        self.received = self.ignore
        self.board.set_title('your turn')

    def their_turn(self):
        self.received = self.wait_for_move
        self.board.set_title('their turn')

    # called when the board receives input
    def move(self, row, col):
        try:
            self.board.mark(row, col, self.role_s)
        except InvalidMove, e:
            print 'you made an invalid move'
            return

        self.send_move(row, col)

        # check win conditions
        if self.board.check_for_strike(self.role_s, row, col, self.strike):
            self.won()
        elif self.board.full():
            self.drawn()
        else:
            self.next_move_id += 1

            self.their_turn()

    # sends a move message
    def send_move(self, row, column):
        msg = nbxmpp.Message()
        msg.setType('chat')

        turn = msg.NT.turn
        turn.setNamespace(NS_GAMES)

        move = turn.NT.move
        move.setNamespace(NS_GAMES_TICTACTOE)

        move.setAttr('row', str(row))
        move.setAttr('col', str(column))
        move.setAttr('id', str(self.next_move_id))

        self.send(msg)

    # sends a termination message and ends the game
    def end_game(self, reason):
        msg = nbxmpp.Message()

        terminate = msg.NT.terminate
        terminate.setNamespace(NS_GAMES)
        terminate.setAttr('reason', reason)

        self.send(msg)

        self.received = self.game_over

    def won(self):
        self.end_game('won')
        self.board.won()

    def lost(self):
        self.end_game('lost')
        self.board.lost()

    def drawn(self):
        self.end_game('draw')
        self.board.drawn()

class TicTacToeBoard:
    def __init__(self, session, rows, cols):
        self.session = session

        self.state = 'None'

        self.rows = rows
        self.cols = cols

        self.board = [ [None] * self.cols for r in xrange(self.rows) ]

        self.setup_window()

    # check if the last move (at row r and column c) won the game
    def check_for_strike(self, p, r, c, strike):
        # number in a row: up and down, left and right
        tallyI = 0
        tally_ = 0

        # number in a row: diagonal
        # (imagine L or F as two sides of a right triangle: L\ or F/)
        tallyL = 0
        tallyF = 0

        # convert real columns to internal columns
        r -= 1
        c -= 1

        for d in xrange(-strike, strike):
            r_in_range = 0 <= r+d < self.rows
            c_in_range = 0 <= c+d < self.cols

            # vertical check
            if r_in_range:
                tallyI = tallyI + 1
                if self.board[r+d][c] != p:
                    tallyI = 0

            # horizontal check
            if c_in_range:
                tally_ = tally_ + 1
                if self.board[r][c+d] != p:
                    tally_ = 0

            # diagonal checks
            if r_in_range and c_in_range:
                tallyL = tallyL + 1
                if self.board[r+d][c+d] != p:
                    tallyL = 0

            if r_in_range and 0 <= c-d < self.cols:
                tallyF = tallyF + 1
                if self.board[r+d][c-d] != p:
                    tallyF = 0

            if any([t == strike for t in (tallyL, tallyF, tallyI, tally_)]):
                return True

        return False

    # is the board full?
    def full(self):
        for r in xrange(self.rows):
            for c in xrange(self.cols):
                if self.board[r][c] == None:
                    return False

        return True

    def setup_window(self):
        self.win = gtk.Window()

        self.title_prefix = 'tic-tac-toe with %s' % self.session.name
        self.set_title()

        self.win.set_app_paintable(True)

        self.win.add_events(gdk.BUTTON_PRESS_MASK)
        self.win.connect('button-press-event', self.clicked)
        self.win.connect('expose-event', self.expose)

        self.win.show_all()

    def clicked(self, widget, event):
        if not self.session.is_my_turn():
            return

        (width, height) = widget.get_size()

        # convert click co-ordinates to row and column
        row_height = height    // self.rows
        col_width = width    // self.cols

        row    = int(event.y // row_height) + 1
        column = int(event.x // col_width) + 1

        self.session.move(row, column)

    # this actually draws the board
    def expose(self, widget, event):
        win = widget.window

        cr = win.cairo_create()

        cr.set_source_rgb(1.0, 1.0, 1.0)

        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.paint()

        layout = cr.create_layout()
        text_height = layout.get_pixel_extents()[1][3]

        (width, height) = widget.get_size()

        row_height = (height - text_height) // self.rows
        col_width  = width    // self.cols

        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(2)
        for x in xrange(1, self.cols):
            cr.move_to(col_width * x, 0)
            cr.line_to(col_width * x, height - text_height)
        for x in xrange(1, self.rows):
            cr.move_to(0, row_height * x)
            cr.line_to(width, row_height * x)
        cr.stroke()

        cr.move_to(0, height - text_height)
        if self.state == 'None':
            if self.session.is_my_turn():
                txt = _('It\'s your turn')
            else:
                txt = _('It\'s %(name)s\'s turn') % {'name': self.session.name}
        elif self.state == 'won':
            txt = _('You won !')
        elif self.state == 'lost':
            txt = _('You lost !')
        elif self.state == 'resign': # other part resigned
            txt = _('%(name)s capitulated') % {'name': self.session.name}
        elif self.state == 'cheated': # other part cheated
            txt = _('%(name)s cheated') % {'name': self.session.name}
        else: #draw
            txt = _('It\'s a draw')
        layout.set_text(txt)
        cr.update_layout(layout)
        cr.show_layout(layout)

        for i in xrange(self.rows):
            for j in xrange(self.cols):
                if self.board[i][j] == 'x':
                    self.draw_x(cr, i, j, row_height, col_width)
                elif self.board[i][j] == 'o':
                    self.draw_o(cr, i, j, row_height, col_width)

    def draw_x(self, cr, row, col, row_height, col_width):
        if self.session.role_s == 'x':
            color = gajim.config.get('outmsgcolor')
        else:
            color = gajim.config.get('inmsgcolor')
        c = gtk.gdk.Color(color)
        cr.set_source_color(c)

        top = row_height * (row + 0.2)
        bottom = row_height * (row + 0.8)

        left = col_width * (col + 0.2)
        right = col_width * (col + 0.8)

        cr.set_line_width(row_height / 5)

        cr.move_to(left, top)
        cr.line_to(right, bottom)

        cr.move_to(right, top)
        cr.line_to(left, bottom)

        cr.stroke()

    def draw_o(self, cr, row, col, row_height, col_width):
        if self.session.role_s == 'o':
            color = gajim.config.get('outmsgcolor')
        else:
            color = gajim.config.get('inmsgcolor')
        c = gtk.gdk.Color(color)
        cr.set_source_color(c)

        x = col_width * (col + 0.5)
        y = row_height * (row + 0.5)

        cr.arc(x, y, row_height/4, 0, 2.0*3.2) # slightly further than 2*pi

        cr.set_line_width(row_height / 5)
        cr.stroke()

    # mark a move on the board
    def mark(self, row, column, player):
        if self.board[row-1][column-1]:
            raise InvalidMove
        else:
            self.board[row-1][column-1] = player

        self.win.queue_draw()

    def set_title(self, suffix = None):
        str_ = self.title_prefix

        if suffix:
            str_ += ': ' + suffix

        self.win.set_title(str_)

    def won(self):
        self.state = 'won'
        self.set_title('you won!')
        self.win.queue_draw()

    def lost(self):
        self.state = 'lost'
        self.set_title('you lost.')
        self.win.queue_draw()

    def drawn(self):
        self.state = 'drawn'
        self.win.set_title(self.title_prefix + ': a draw.')
        self.win.queue_draw()

    def cheated(self):
        self.state == 'cheated'
        self.win.queue_draw()


class TictactoePluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.board_size_spinbutton = self.xml.get_object('board_size')
        self.board_size_spinbutton.get_adjustment().set_all(3, 3, 10, 1, 1, 0)
        vbox = self.xml.get_object('vbox1')
        self.child.pack_start(vbox)

        self.xml.connect_signals(self)

    def on_run(self):
        self.board_size_spinbutton.set_value(self.plugin.config['board_size'])

    def board_size_value_changed(self, spinbutton):
        self.plugin.config['board_size'] = int(spinbutton.get_value())

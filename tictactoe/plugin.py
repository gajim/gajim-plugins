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

import string
import itertools
import random

import nbxmpp
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import Gio
from gi.repository import GLib
import gi
gi.require_version('PangoCairo', '1.0')
from gi.repository import PangoCairo

from gajim.common import helpers
from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls, log
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim import chat_control
from gajim.common import ged
from gajim import dialogs
from gajim.common.connection_handlers_events import InformationEvent

NS_GAMES = 'http://jabber.org/protocol/games'
NS_GAMES_TICTACTOE = NS_GAMES + '/tictactoe'

class TictactoePlugin(GajimPlugin):
    @log_calls('TictactoePlugin')
    def init(self):
        self.description = _('Play Tictactoe.')
        self.config_dialog = TictactoePluginConfigDialog(self)
        self.events_handlers = {
            'decrypted-message-received': (
                ged.PREGUI, self._nec_decrypted_message_received),
        }

        self.gui_extension_points = {
            'chat_control': (self.connect_with_chat_control,
                             self.disconnect_from_chat_control),
            'chat_control_base_update_toolbar': (
                self.update_button_state, None),
            'update_caps': (self._update_caps, None),
        }

        self.config_default_values = {
            'board_size': (5, ''),
        }

        self.controls = []
        self.announce_caps = True

    @log_calls('TictactoePlugin')
    def _update_caps(self, account):
        if not self.announce_caps:
            return
        if NS_GAMES not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(NS_GAMES)
        if NS_GAMES_TICTACTOE not in app.gajim_optional_features[account]:
            app.gajim_optional_features[account].append(NS_GAMES_TICTACTOE)

    @log_calls('TictactoePlugin')
    def activate(self):
        for account in app.caps_hash:
            if app.caps_hash[account] != '':
                self.announce_caps = True
                helpers.update_optional_features(account)

    @log_calls('TictactoePlugin')
    def deactivate(self):
        self.announce_caps = False
        helpers.update_optional_features()

    @log_calls('TictactoePlugin')
    def connect_with_chat_control(self, control):
        if isinstance(control, chat_control.ChatControl):
            base = Base(self, control)
            self.controls.append(base)
            # Already existing session?
            conn = app.connections[control.account]
            sessions = conn.get_sessions(control.contact.jid)
            tictactoes = [s for s in sessions if isinstance(s,
                TicTacToeSession)]
            if tictactoes:
                base.tictactoe = tictactoes[0]
                base.enable_action(True)

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
                    base.enable_action(True)
                else:
                    base.enable_action(False)

    @log_calls('TictactoePlugin')
    def show_request_dialog(self, obj, session):
        def on_ok():
            session.invited(obj.stanza)

        def on_cancel():
            session.decline_invitation()

        account = obj.conn.name
        contact = app.contacts.get_first_contact_from_jid(account, obj.jid)
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
        self.add_action()
        self.tictactoe = None

    def add_action(self):
        action_name = 'toggle-tictactoe-' + self.chat_control.control_id
        act = Gio.SimpleAction.new_stateful(
            action_name, None, GLib.Variant.new_boolean(False))
        act.connect('change-state', self.on_tictactoe_button_toggled)
        self.chat_control.parent_win.window.add_action(act)

        self.chat_control.control_menu.append(
            'TicTacToe', 'win.' + action_name)

    def enable_action(self, state):
        win = self.chat_control.parent_win.window
        action_name = 'toggle-tictactoe-' + self.chat_control.control_id
        win.lookup_action(action_name).set_enabled(state)

    def on_tictactoe_button_toggled(self, action, param):
        """
        Popup whiteboard
        """
        action.set_state(param)
        state = param.get_boolean()
        if state:
            if not self.tictactoe:
                self.start_tictactoe()
        else:
            self.stop_tictactoe('resign')

    def start_tictactoe(self):
        self.tictactoe = app.connections[self.account].make_new_session(
            self.fjid, cls=TicTacToeSession)
        self.tictactoe.base = self
        self.tictactoe.begin()

    def stop_tictactoe(self, reason=None):
        self.tictactoe.end_game(reason)
        if hasattr(self.tictactoe, 'board'):
            self.tictactoe.board.win.destroy()
        self.tictactoe = None

    def disconnect_from_chat_control(self):
        menu = self.chat_control.control_menu
        for i in range(menu.get_n_items()):
            label = menu.get_item_attribute_value(i, 'label')
            if label.get_string() == 'TicTacToe':
                menu.remove(i)
                break

class InvalidMove(Exception):
    pass

class TicTacToeSession(object):
    def __init__(self, conn, jid, thread_id, type_):
        self.conn = conn
        self.jid = jid
        self.type_ = type_
        self.resource = jid.getResource()

        if thread_id:
            self.received_thread_id = True
            self.thread_id = thread_id
        else:
            self.received_thread_id = False
            self.thread_id = self.generate_thread_id()

        contact = app.contacts.get_contact(
            conn.name, app.get_jid_without_resource(str(jid)))
        self.name = contact.get_shown_name()
        self.base = None
        self.control = None
        self.enable_encryption = False

    def send(self, msg):
        if self.thread_id:
            msg.NT.thread = self.thread_id

        msg.setAttr('to', self.get_to())
        self.conn.send_stanza(msg)

    def get_to(self):
        to = str(self.jid)
        return app.get_jid_without_resource(to) + '/' + self.resource

    def generate_thread_id(self):
        return ''.join(
            [f(string.ascii_letters) for f in itertools.repeat(
                random.choice, 32)]
        )

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

        form = nbxmpp.DataForm(node=x)

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
            app.nec.push_incoming_event(InformationEvent(None, conn=self.conn,
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
            log.warn('unexpected move id, lost a move somewhere?')
            return

        try:
            self.board.mark(row, col, self.role_o)
        except InvalidMove as e:
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
        except InvalidMove as e:
            log.warn('you made an invalid move')
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


class DrawBoard(Gtk.DrawingArea):
    def __init__(self):
        Gtk.DrawingArea.__init__(self)
        self.set_size_request(200, 200)
        self.set_property('expand', True)


class TicTacToeBoard:
    def __init__(self, session, rows, cols):
        self.session = session

        self.state = 'None'

        self.rows = rows
        self.cols = cols

        self.board = [ [None] * self.cols for r in range(self.rows) ]

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

        for d in range(-strike, strike):
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
        for r in range(self.rows):
            for c in range(self.cols):
                if self.board[r][c] == None:
                    return False

        return True

    def setup_window(self):
        self.win = Gtk.Window()
        draw = DrawBoard()
        self.win.add(draw)

        self.title_prefix = 'tic-tac-toe with %s' % self.session.name
        self.set_title()

        self.win.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.win.connect('button-press-event', self.clicked)

        draw.connect('draw', self.do_draw)

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
    def do_draw(self, widget, cr):
        cr.set_source_rgb(1.0, 1.0, 1.0)

        layout = PangoCairo.create_layout(cr)
        text_height = layout.get_pixel_extents()[1].height

        (width, height) = self.win.get_size()

        row_height = (height - text_height) // self.rows
        col_width  = width // self.cols

        cr.set_source_rgb(0, 0, 0)
        cr.set_line_width(2)
        for x in range(1, self.cols):
            cr.move_to(col_width * x, 0)
            cr.line_to(col_width * x, height - text_height)
        for x in range(1, self.rows):
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
        layout.set_text(txt, -1)
        # Inform Pango to re-layout the text with the new transformation
        PangoCairo.update_layout(cr, layout)
        PangoCairo.show_layout(cr, layout)

        for i in range(self.rows):
            for j in range(self.cols):
                if self.board[i][j] == 'x':
                    self.draw_x(cr, i, j, row_height, col_width)
                elif self.board[i][j] == 'o':
                    self.draw_o(cr, i, j, row_height, col_width)

    def draw_x(self, cr, row, col, row_height, col_width):
        if self.session.role_s == 'x':
            color = app.config.get('outmsgcolor')
        else:
            color = app.config.get('inmsgcolor')
        rgba = Gdk.RGBA()
        rgba.parse(color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)

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
            color = app.config.get('outmsgcolor')
        else:
            color = app.config.get('inmsgcolor')
        rgba = Gdk.RGBA()
        rgba.parse(color)
        cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, rgba.alpha)

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
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH, ['vbox1'])
        self.board_size_spinbutton = self.xml.get_object('board_size')
        self.board_size_spinbutton.get_adjustment().configure(3, 3, 10, 1, 1, 0)
        vbox = self.xml.get_object('vbox1')
        self.get_child().pack_start(vbox, True, True, 0)

        self.xml.connect_signals(self)

    def on_run(self):
        self.board_size_spinbutton.set_value(self.plugin.config['board_size'])

    def board_size_value_changed(self, spinbutton):
        self.plugin.config['board_size'] = int(spinbutton.get_value())

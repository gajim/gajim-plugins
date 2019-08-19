# Copyright (C) 2009 Jeff Ling <jeff.ummu AT gmail.com>
# Copyright (C) 2010-2017 Yann Leboulanger <asterix AT lagaule.org>
#
# This file is part of the Whiteboard Plugin.
#
# Gajim is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation; version 3 only.
#
# Gajim is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Gajim. If not, see <http://www.gnu.org/licenses/>.
#

from nbxmpp import Node
from gi.repository import Gtk

from gajim.common import app

from gajim.gtk.filechoosers import NativeFileChooserDialog
from gajim.gtk.filechoosers import Filter

from gajim.plugins.helpers import get_builder
from gajim.plugins.plugins_i18n import _

try:
    import gi
    gi.require_version('GooCanvas', '2.0')
    from gi.repository import GooCanvas
    HAS_GOOCANVAS = True
except ValueError:
    HAS_GOOCANVAS = False


class SvgSaveDialog(NativeFileChooserDialog):

    _title = _('Save File as…')
    _filters = [Filter(_('All files'), '*', False),
                Filter(_('SVG files'), '*.svg', True)]
    _action = Gtk.FileChooserAction.SAVE


'''
A whiteboard widget made for Gajim.
- Ummu
'''


class Whiteboard(object):
    def __init__(self, account, contact, session, plugin):
        self.plugin = plugin
        path = plugin.local_file_path('whiteboard_widget.ui')
        self._ui = get_builder(path)

        self.canvas = GooCanvas.Canvas()
        self.hbox = self._ui.whiteboard_hbox
        self._ui.whiteboard_hbox.pack_start(self.canvas, True, True, 0)
        self._ui.whiteboard_hbox.reorder_child(self.canvas, 0)
        self.root = self.canvas.get_root_item()
        self.tool_buttons = [
            self._ui.brush_button,
            self._ui.oval_button,
            self._ui.line_button,
            self._ui.delete_button
        ]
        self._ui.brush_button.set_active(True)

        # Events
        self.canvas.connect('button-press-event', self.button_press_event)
        self.canvas.connect('button-release-event', self.button_release_event)
        self.canvas.connect('motion-notify-event', self.motion_notify_event)
        self.canvas.connect('item-created', self.item_created)

        # Config
        self.line_width = 2
        self._ui.size_scale.set_value(2)
        c = self._ui.fg_color_button.get_rgba()
        self.color = int(c.red*255*256*256*256 +
                         c.green*255*256*256 +
                         c.blue*255*256 + 255)

        # SVG Storage
        self.image = SVGObject(self.root, session)

        self._ui.connect_signals(self)

        # Temporary Variables for items
        self.item_temp = None
        self.item_temp_coords = (0, 0)
        self.item_data = None

        # Will be instance of {ID: {type:'element'
        #                           data:[node, goocanvas]},
        #                      ID2: {}}
        self.receiving = {}

    def _on_tool_button_toggled(self, widget):
        for btn in self.tool_buttons:
            if btn == widget:
                continue
            btn.set_active(False)

    def _on_brush_button_toggled(self, widget):
        if widget.get_active():
            self.image.draw_tool = 'brush'
            self._on_tool_button_toggled(widget)

    def _on_oval_button_toggled(self, widget):
        if widget.get_active():
            self.image.draw_tool = 'oval'
            self._on_tool_button_toggled(widget)

    def _on_line_button_toggled(self, widget):
        if widget.get_active():
            self.image.draw_tool = 'line'
            self._on_tool_button_toggled(widget)

    def _on_delete_button_toggled(self, widget):
        if widget.get_active():
            self.image.draw_tool = 'delete'
            self._on_tool_button_toggled(widget)

    def _on_clear_button_clicked(self, widget):
        self.image.clear_canvas()

    def _on_fg_color_button_color_set(self, widget):
        c = self._ui.fg_color_button.get_rgba()
        self.color = int(
            c.red*255*256*256*256 +
            c.green*255*256*256 +
            c.blue*255*256 + 255)

    def _on_size_scale_format_value(self, widget):
        self.line_width = int(widget.get_value())

    def _on_export_button_clicked(self, widget):
        SvgSaveDialog(self.image.export_svg,
                      file_name=_('whiteboard.svg'),
                      path=app.config.get('last_save_dir'),
                      transient_for=app.app.get_active_window())

    def item_created(self, canvas, item, model):
        item.connect('button-press-event', self.item_button_press_events)

    def item_button_press_events(self, item, target_item, event):
        if self.image.draw_tool == 'delete':
            self.image.del_item(item)

    def button_press_event(self, widget, event):
        x = event.x
        y = event.y
        self.item_temp_coords = (x, y)

        if self.image.draw_tool == 'brush':
            self.item_temp = GooCanvas.CanvasEllipse(
                parent=self.root,
                center_x=x,
                center_y=y,
                radius_x=1,
                radius_y=1,
                stroke_color_rgba=self.color,
                fill_color=self.color,
                line_width=self.line_width)
            self.item_data = 'M %s,%s L ' % (x, y)

        elif self.image.draw_tool == 'oval':
            self.item_data = True

        if self.image.draw_tool == 'line':
            self.item_data = 'M %s,%s L' % (x, y)

    def motion_notify_event(self, widget, event):
        x = event.x
        y = event.y
        if self.item_temp is not None:
            self.item_temp.remove()

        if self.item_data is not None:
            if self.image.draw_tool == 'brush':
                self.item_data = self.item_data + '%s,%s ' % (x, y)
                self.item_temp = GooCanvas.CanvasPath(
                    parent=self.root,
                    data=self.item_data,
                    line_width=self.line_width,
                    stroke_color_rgba=self.color)
            elif self.image.draw_tool == 'oval':
                self.item_temp = GooCanvas.CanvasEllipse(
                    parent=self.root,
                    center_x=self.item_temp_coords[0] +
                    (x - self.item_temp_coords[0]) / 2,
                    center_y=self.item_temp_coords[1] +
                    (y - self.item_temp_coords[1]) / 2,
                    radius_x=abs(x - self.item_temp_coords[0]) / 2,
                    radius_y=abs(y - self.item_temp_coords[1]) / 2,
                    stroke_color_rgba=self.color,
                    line_width=self.line_width)
            elif self.image.draw_tool == 'line':
                self.item_data = 'M %s,%s L' % self.item_temp_coords
                self.item_data = self.item_data + ' %s,%s' % (x, y)
                self.item_temp = GooCanvas.CanvasPath(
                    parent=self.root,
                    data=self.item_data,
                    line_width=self.line_width,
                    stroke_color_rgba=self.color)

    def button_release_event(self, widget, event):
        x = event.x
        y = event.y

        if self.image.draw_tool == 'brush':
            self.item_data = self.item_data + '%s,%s' % (x, y)
            if x == self.item_temp_coords[0] and y == self.item_temp_coords[1]:
                GooCanvas.CanvasEllipse(
                    parent=self.root,
                    center_x=x,
                    center_y=y,
                    radius_x=1,
                    radius_y=1,
                    stroke_color_rgba=self.color,
                    fill_color=self.color,
                    line_width=self.line_width)
            self.image.add_path(self.item_data, self.line_width, self.color)

        if self.image.draw_tool == 'oval':
            cx = self.item_temp_coords[0] + (x - self.item_temp_coords[0]) / 2
            cy = self.item_temp_coords[1] + (y - self.item_temp_coords[1]) / 2
            rx = abs(x - self.item_temp_coords[0]) / 2
            ry = abs(y - self.item_temp_coords[1]) / 2
            self.image.add_ellipse(cx, cy, rx, ry, self.line_width, self.color)

        if self.image.draw_tool == 'line':
            self.item_data = 'M %s,%s L' % self.item_temp_coords
            self.item_data = self.item_data + ' %s,%s' % (x, y)
            if x == self.item_temp_coords[0] and y == self.item_temp_coords[1]:
                GooCanvas.CanvasEllipse(
                    parent=self.root,
                    center_x=x,
                    center_y=y,
                    radius_x=1,
                    radius_y=1,
                    stroke_color_rgba=self.color,
                    fill_color_rgba=self.color,
                    line_width=self.line_width)
            self.image.add_path(self.item_data, self.line_width, self.color)

        if self.image.draw_tool == 'delete':
            pass

        self.item_data = None
        if self.item_temp is not None:
            self.item_temp.remove()
            self.item_temp = None

    def recieve_element(self, element):
        node = self.image.g.addChild(name=element.getAttr('name'))
        self.image.g.addChild(node=node)
        self.receiving[element.getAttr('rid')] = {'type': 'element',
                                                  'data': [node],
                                                  'children': []}

    def recieve_attr(self, element):
        node = self.receiving[element.getAttr('parent')]['data'][0]
        node.setAttr(element.getAttr('name'), element.getAttr('chdata'))

        self.receiving[element.getAttr('rid')] = {'type': 'attr',
                                                  'data': element.getAttr(
                                                      'name'),
                                                  'parent': node}
        self.receiving[element.getAttr('parent')]['children'].append(
            element.getAttr('rid'))

    def apply_new(self):
        for x in self.receiving.keys():
            if self.receiving[x]['type'] == 'element':
                self.image.add_recieved(x, self.receiving)

        self.receiving = {}


class SVGObject():
    ''' A class to store the svg document and make changes to it.'''
    def __init__(self, root, session, height=300, width=300):
        # Will be instance of {ID: {type:'element',
        #                           data:[node, goocanvas]},
        #                      ID2: {}}
        self.items = {}
        self.root = root
        self.draw_tool = 'brush'

        # SXE session
        self.session = session

        # Initialize svg document
        self.svg = Node(node='<svg/>')
        self.svg.setAttr('version', '1.1')
        self.svg.setAttr('height', str(height))
        self.svg.setAttr('width', str(width))
        self.svg.setAttr('xmlns', 'http://www.w3.org/2000/svg')
        # TODO: Make this settable
        self.g = self.svg.addChild(name='g')
        self.g.setAttr('fill', 'none')
        self.g.setAttr('stroke-linecap', 'round')

    def add_path(self, data, line_width, color):
        '''
        Adds the path to the items listing, both minidom node and goocanvas
        object in a tuple
        '''
        goocanvas_obj = GooCanvas.CanvasPath(
            parent=self.root,
            data=data,
            line_width=line_width,
            stroke_color_rgba=color)
        goocanvas_obj.connect('button-press-event',
                              self.item_button_press_events)

        node = self.g.addChild(name='path')
        node.setAttr('d', data)
        node.setAttr('stroke-width', str(line_width))
        node.setAttr('stroke', str(color))
        self.g.addChild(node=node)

        rids = self.session.generate_rids(4)
        self.items[rids[0]] = {'type': 'element',
                               'data': [node, goocanvas_obj],
                               'children': rids[1:]}
        self.items[rids[1]] = {'type': 'attr',
                               'data': 'd',
                               'parent': node}
        self.items[rids[2]] = {'type': 'attr',
                               'data': 'stroke-width',
                               'parent': node}
        self.items[rids[3]] = {'type': 'attr',
                               'data': 'stroke',
                               'parent': node}

        self.session.send_items(self.items, rids)

    def add_recieved(self, parent_rid, new_items):
        '''
        Adds the path to the items listing, both minidom node and goocanvas
        object in a tuple
        '''
        node = new_items[parent_rid]['data'][0]

        self.items[parent_rid] = new_items[parent_rid]
        for x in new_items[parent_rid]['children']:
            self.items[x] = new_items[x]

        if node.getName() == 'path':
            goocanvas_obj = GooCanvas.CanvasPath(
                parent=self.root,
                data=node.getAttr('d'),
                line_width=int(node.getAttr('stroke-width')),
                stroke_color_rgba=int(node.getAttr('stroke')))

        if node.getName() == 'ellipse':
            goocanvas_obj = GooCanvas.CanvasEllipse(
                parent=self.root,
                center_x=float(node.getAttr('cx')),
                center_y=float(node.getAttr('cy')),
                radius_x=float(node.getAttr('rx')),
                radius_y=float(node.getAttr('ry')),
                stroke_color_rgba=int(node.getAttr('stroke')),
                line_width=float(node.getAttr('stroke-width')))

        self.items[parent_rid]['data'].append(goocanvas_obj)
        goocanvas_obj.connect('button-press-event',
                              self.item_button_press_events)

    def add_ellipse(self, cx, cy, rx, ry, line_width, stroke_color):
        '''
        Adds the ellipse to the items listing, both minidom node and goocanvas
        object in a tuple
        '''
        goocanvas_obj = GooCanvas.CanvasEllipse(
            parent=self.root,
            center_x=cx,
            center_y=cy,
            radius_x=rx,
            radius_y=ry,
            stroke_color_rgba=stroke_color,
            line_width=line_width)
        goocanvas_obj.connect('button-press-event',
                              self.item_button_press_events)

        node = self.g.addChild(name='ellipse')
        node.setAttr('cx', str(cx))
        node.setAttr('cy', str(cy))
        node.setAttr('rx', str(rx))
        node.setAttr('ry', str(ry))
        node.setAttr('stroke-width', str(line_width))
        node.setAttr('stroke', str(stroke_color))
        self.g.addChild(node=node)

        rids = self.session.generate_rids(7)
        self.items[rids[0]] = {'type': 'element',
                               'data': [node, goocanvas_obj],
                               'children': rids[1:]}
        self.items[rids[1]] = {'type': 'attr',
                               'data': 'cx',
                               'parent': node}
        self.items[rids[2]] = {'type': 'attr',
                               'data': 'cy',
                               'parent': node}
        self.items[rids[3]] = {'type': 'attr',
                               'data': 'rx',
                               'parent': node}
        self.items[rids[4]] = {'type': 'attr',
                               'data': 'ry',
                               'parent': node}
        self.items[rids[5]] = {'type': 'attr',
                               'data': 'stroke-width',
                               'parent': node}
        self.items[rids[6]] = {'type': 'attr',
                               'data': 'stroke',
                               'parent': node}

        self.session.send_items(self.items, rids)

    def del_item(self, item):
        rids = []
        for x in list(self.items.keys()):
            if self.items[x]['type'] == 'element':
                if self.items[x]['data'][1] == item:
                    for y in self.items[x]['children']:
                        rids.append(y)
                        self.del_rid(y)
                    rids.append(x)
                    self.del_rid(x)
                    break
        self.session.del_item(rids)

    def clear_canvas(self):
        for x in list(self.items.keys()):
            if self.items[x]['type'] == 'element':
                self.del_rid(x)

    def del_rid(self, rid):
        if self.items[rid]['type'] == 'element':
            self.items[rid]['data'][1].remove()
        del self.items[rid]

    def export_svg(self, filename):
        f = open(filename, 'w')
        f.writelines(str(self.svg))
        f.close()

    def item_button_press_events(self, item, target_item, event):
        self.del_item(item)

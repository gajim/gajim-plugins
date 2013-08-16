# -*- coding: utf-8 -*-

import gtk
import subprocess
import gobject

from common import gajim
from plugins import GajimPlugin
from plugins.helpers import log_calls, log
from plugins.gui import GajimPluginConfigDialog


class FlashingKeyboard(GajimPlugin):
    @log_calls('FlashingKeyboard')
    def init(self):
        self.config_dialog = FlashingKeyboardPluginConfigDialog(self)
        self.config_default_values = {
            'command1': ("xset led named 'Scroll Lock'", ''),
            'command2': ("xset -led named 'Scroll Lock'", ''),
            'flash': (True, ''),
        }

        self.is_active = None
        self.timeout = 500
        self.timeout_off = self.timeout / 2
        self.id_0 = None

    def on_event_added(self, event):
        if event.show_in_systray:
            self.flash_trigger()

    def on_event_removed(self, event_list):
        self.flash_trigger()

    def flash_trigger(self):
        if gajim.events.get_nb_systray_events():
            if self.id_0:
                return
            if self.config['flash']:
                self.id_0 = gobject.timeout_add(self.timeout, self.led_on)
            else:
                self.led_on()
                self.id_0 = True
        else:
            if self.id_0:
                if self.config['flash']:
                    gobject.source_remove(self.id_0)
                self.id_0 = None
                self.led_off()

    def led_on(self):
        subprocess.Popen('%s' % self.config['command1'], shell=True).wait()
        if self.config['flash']:
            gobject.timeout_add(self.timeout_off, self.led_off)
        return True

    def led_off(self):
        subprocess.Popen('%s' % self.config['command2'], shell=True).wait()

    @log_calls('FlashingKeyboard')
    def activate(self):
        gajim.events.event_added_subscribe(self.on_event_added)
        gajim.events.event_removed_subscribe(self.on_event_removed)
        if gajim.events.get_nb_systray_events():
            if self.config['flash']:
                self.id_0 = gobject.timeout_add(self.timeout, self.led_on)
            else:
                self.led_on()
                self.id_0 = True

    @log_calls('FlashingKeyboard')
    def deactivate(self):
        gajim.events.event_added_unsubscribe(self.on_event_added)
        gajim.events.event_removed_unsubscribe(self.on_event_removed)
        if self.id_0:
            gobject.source_remove(self.id_0)
            self.led_off()


class FlashingKeyboardPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
                'config_dialog.ui')
        self.xml = gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['config_table'])
        config_table = self.xml.get_object('config_table')
        self.child.pack_start(config_table)
        self.xml.connect_signals(self)
        self.connect('hide', self.on_close_button_clicked)

    def on_run(self):
        self.isactive = self.plugin.active
        if self.plugin.active:
            gajim.plugin_manager.deactivate_plugin(self.plugin)
        for name in ('command1', 'command2'):
            widget = self.xml.get_object(name)
            widget.set_text(self.plugin.config[name])
        widget = self.xml.get_object('flash_cb')
        widget.set_active(not self.plugin.config['flash'])

    def on_close_button_clicked(self, widget):
        widget = self.xml.get_object('command1')
        self.plugin.config['command1'] = widget.get_text()
        widget = self.xml.get_object('command2')
        self.plugin.config['command2'] = widget.get_text()
        widget = self.xml.get_object('flash_cb')
        self.plugin.config['flash'] = not widget.get_active()
        if self.isactive:
            gajim.plugin_manager.activate_plugin(self.plugin)

import subprocess

from gi.repository import Gtk
from gi.repository import GObject

from gajim.common import app
from gajim.plugins import GajimPlugin
from gajim.plugins.helpers import log_calls
from gajim.plugins.gui import GajimPluginConfigDialog
from gajim.plugins.plugins_i18n import _

class FlashingKeyboard(GajimPlugin):
    @log_calls('FlashingKeyboard')
    def init(self):
        self.description = _('Flashing keyboard led when there are unread messages.')
        self.config_dialog = FlashingKeyboardPluginConfigDialog(self)
        self.config_default_values = {
            'command1': ("xset led named 'Scroll Lock'", ''),
            'command2': ("xset -led named 'Scroll Lock'", ''),
            'flash': (True, ''),
        }

        self.is_active = None
        self.timeout = 500
        self.timeout_off = int(self.timeout / 2)
        self.id_0 = None

    def on_event_added(self, event):
        if event.show_in_systray:
            self.flash_trigger()

    def on_event_removed(self, event_list):
        self.flash_trigger()

    def flash_trigger(self):
        if app.events.get_nb_systray_events():
            if self.id_0:
                return
            if self.config['flash']:
                self.id_0 = GObject.timeout_add(self.timeout, self.led_on)
            else:
                self.led_on()
                self.id_0 = True
        else:
            if self.id_0:
                if self.config['flash']:
                    GObject.source_remove(self.id_0)
                self.id_0 = None
                self.led_off()

    def led_on(self):
        subprocess.Popen('%s' % self.config['command1'], shell=True).wait()
        if self.config['flash']:
            GObject.timeout_add(self.timeout_off, self.led_off)
        return True

    def led_off(self):
        subprocess.Popen('%s' % self.config['command2'], shell=True).wait()

    @log_calls('FlashingKeyboard')
    def activate(self):
        app.events.event_added_subscribe(self.on_event_added)
        app.events.event_removed_subscribe(self.on_event_removed)
        if app.events.get_nb_systray_events():
            if self.config['flash']:
                self.id_0 = GObject.timeout_add(self.timeout, self.led_on)
            else:
                self.led_on()
                self.id_0 = True

    @log_calls('FlashingKeyboard')
    def deactivate(self):
        app.events.event_added_unsubscribe(self.on_event_added)
        app.events.event_removed_unsubscribe(self.on_event_removed)
        if self.id_0:
            GObject.source_remove(self.id_0)
            self.led_off()


class FlashingKeyboardPluginConfigDialog(GajimPluginConfigDialog):
    def init(self):
        self.GTK_BUILDER_FILE_PATH = self.plugin.local_file_path(
            'config_dialog.ui')
        self.xml = Gtk.Builder()
        self.xml.set_translation_domain('gajim_plugins')
        self.xml.add_objects_from_file(self.GTK_BUILDER_FILE_PATH,
            ['config_table'])
        config_table = self.xml.get_object('config_table')
        self.get_child().pack_start(config_table, True, True, 0)
        self.xml.connect_signals(self)

    def on_run(self):
        self.isactive = self.plugin.active
        if self.plugin.active:
            app.plugin_manager.deactivate_plugin(self.plugin)
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
            app.plugin_manager.activate_plugin(self.plugin)
        GajimPluginConfigDialog.on_close_button_clicked(self, widget)

# Syntax Highlighting Plugin for Gajim

[Gajim](https://gajim.org/) Plugin that highlights source code blocks in chatbox.

## Installation

The recommended way of installing this plugin is to use
[Gajim's Plugin Installer](https://dev.gajim.org/gajim/gajim-plugins/#how-to-install).


### Manual Installation
To install the plugin manually clone it into Gajims plugins folder (should be
`~/.local/share/gajim/plugins/` on Linux or
`C:\Users\USERNAME\AppData\Roaming\Gajim\Plugins` on Windows):

```
cd ~/.local/share/gajim/plugins/
git clone https://github.com/FlorianMuenchbach/gajim-syntax-highlight
```

Then restart Gajim and enable the plugin in the plugins menu.


## Usage

Source code between `@@` tags will be highlighted in the chatbox.
You can test it by copying and sending the following text to one of your
contacts:
```
@@def test():
    print("Hello, world!")
@@
```
(**Node:** your contact will not receive highlighted text unless she is also
using the plugin.)

If you want to send code written in a programming language other than the
default, you can specify the language between the first `@@` and one additional
`@` tag:
```
@@bash@
echo "Hello, world"
@@
```


## Debug

The plugin adds its own logger. It can be used to set a specific debug level
for this plugin and/or filter log messages.

Run
```
gajim --loglevel gajim.plugin_system.syntax_highlight=DEBUG
```
in a terminal to display the debug messages.


## Known Issues / ToDo

 * Gajim crashes when correcting a message containing highlighted code.


## Credits

Since I had no experience in writing Plugins for Gajim, I used the
[Latex Plugin](https://trac-plugins.gajim.org/wiki/LatexPlugin)
written by Yves Fischer and Yann Leboulanger as an example and copied a big
portion of initial code. Therefore, credits go to the authors of the Latex
Plugin for providing an example.

The syntax highlighting itself is done by [pygments](http://pygments.org/).

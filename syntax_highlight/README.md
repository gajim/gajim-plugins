# Syntax Highlighting Plugin for Gajim

[Gajim](https://gajim.org) Plugin that highlights source code blocks in chatbox.

## Installation

The recommended way of installing this plugin is to use
Gajim's Plugin Installer.

For more information and instruction on how to install plugins manually, please
refer to the [Gajim Plugin Wiki seite](https://dev.gajim.org/gajim/gajim-plugins/wikis/home#how-to-install-plugins).


## Usage

This plugin uses markdown-style syntax to identify which parts of a message
should be formatted as code in the chatbox.

```
Inline source code  will be highlighted when placed in between `two single
back-ticks`.
```

The language used to highlight the syntax of inline code is selected as the
default language in the plugin settings.


Multi-line code blocks are started by three back-ticks followed by a newline.
Optionally, a language can be specified directly after the opening back-ticks and
before the line break:
````
```language
Note, that the last line of a code block may only contain the closing back-ticks,
i.e. there must be a newline here.
```
````

In case no languge is specified with the opening tag or the specified language
could not be identified, the default languge configured in the settings is
used.

You can test it by copying and sending the following text to one of your
contacts:
````
```python
def test():
    print("Hello, world!")
```
````
(**Note:** your contact will not receive highlighted text unless she is also
using the plugin.)

## Configuration

The configuration can be found via 'Gajim' > 'Plugins', then select the
'Source Code Syntax Highlight' Plugin and click the gears symbol.
The configuration options let you specify many details how code is formatted,
including default language, style, font settings, background color and formatting
of the code markers.

In the configuration window, the current settings are displayed in an
interactive preview pannel. This allows you to directly check how code would
look like in the message
window.

## Report Bugs and Feature Requests

For bug reports, please report them to the [Gajim Plugin Issue tracker](https://dev.gajim.org/gajim/gajim-plugins/issues/new?issue[FlorianMuenchbach]=&issue[description]=Gajim%20Version%3A%20%0APlugin%20Version%3A%0AOperating%20System%3A&issue[title]=[syntax_highlight]).

Please make sure that the issue you create contains `[syntax_highlight]` in the
title and information such as Gajim version, Plugin version, Operating system,
etc.

## Debug

The plugin adds its own logger. It can be used to set a specific debug level
for this plugin and/or filter log messages.

Run
```
gajim --loglevel gajim.plugin_system.syntax_highlight=DEBUG
```
in a terminal to display the debug messages.


## Known Issues / ToDo

 * ~~Gajim crashes when correcting a message containing highlighted code.~~
   (fixed in version 1.1.0)


## Credits

Since I had no experience in writing Plugins for Gajim, I used the
[Latex Plugin](https://trac-plugins.gajim.org/wiki/LatexPlugin)
written by Yves Fischer and Yann Leboulanger as an example and copied a big
portion of initial code. Therefore, credits go to the authors of the Latex
Plugin for providing an example.

The syntax highlighting itself is done by [pygments](http://pygments.org/).

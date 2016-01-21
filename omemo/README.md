# OMEMO Plugin for Gajim

This is an experimental plugin that adds support for the [OMEMO
Encryption](http://conversations.im/omemo) to [Gajim](https://gajim.org/). This
plugin is [free software](http://www.gnu.org/philosophy/free-sw.en.html)
distributed under the GNU General Public License version 3 or any later version.

**DO NOT rely on this plugin to protect sensitive information!** 

## Installation
Install the current stable version via the Gajim PluginManager. You *need* Gajim
version *0.16.5*. If your package manager does not provide an up to date version
you can install it from the official Mercurial repository. *DO NOT USE* gajim
0.16.4 it contains a vulnerability, which is fixed in 0.16.5.
```shell
hg clone https://hg.gajim.org/gajim
cd gajim
hg update gajim-0.16.5 --clean
```

### Python libraries
You *have* to install `python-axolotl` via `pip`. Depending on your setup you might
want to use `pip2` as Gajim is using python2.7. If you are using the official repository,
do not forget to install the `nbxmpp` dependency via pip or you package manager.

## Running
Enable *OMEMO Multi-End Message and Object Encryption* in the Plugin-Manager.
Before exchanging encrypted messages with a contact you have to hit the *Get
Device Keys* button. (Repeat that if you or your contact get new devices.)

Currently the plugin has no user interface for confirming the own and foreign
device keys.  It uses trust on first use. This will be added in near future.

## Debugging
To see OMEMO related debug output start Gajim with the parameter `-l
gajim.plugin_system.omemo=DEBUG`.

## Hacking
This repository contains the current development version. If you want to
contribute clone the git repository into your Gajim's plugin directory. 
```shell
mkdir ~/.local/share/gajim/plugins -p
cd ~/.local/share/gajim/plugins
git clone https://github.com/omemo/gajim-omemo
```

## Support this project
I develop this project in my free time. Your donation allows me to spend more
time working on it and on free software generally.

My Bitcoin Address is: `1CnNM3Mree9hU8eRjCXrfCWVmX6oBnEfV1`

[![Support Me via Flattr](http://api.flattr.com/button/flattr-badge-large.png)](https://flattr.com/thing/5038679)

## I found a bug
Please report it to the [issue
tracker](https://github.com/omemo/gajim-omemo/issues). If you are experiencing
misbehaviour please provide detailed steps to reproduce and debugging output.
Always mention the exact Gajim version. 

## Contact
You can contact me via email at `bahtiar@gadimov.de` or follow me on
[Twitter](https://twitter.com/_kalkin)

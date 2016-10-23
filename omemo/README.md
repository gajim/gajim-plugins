# OMEMO Plugin for Gajim

This Plugin adds support for the [OMEMO Encryption](http://conversations.im/omemo) to [Gajim](https://gajim.org/). This
plugin is [free software](http://www.gnu.org/philosophy/free-sw.en.html)
distributed under the GNU General Public License version 3 or any later version.

## Installation

Before you open any issues please read our [Wiki](https://github.com/omemo/gajim-omemo/wiki) which addresses some problems that can occur during an install

### Linux

See [Linux Wiki](https://github.com/omemo/gajim-omemo/wiki/Installing-on-Linux)

### Windows

See [Windows Wiki](https://github.com/omemo/gajim-omemo/wiki/Installing-on-Windows)

### Via Package Manager
#### Arch
See [Arch Wiki](https://wiki.archlinux.org/index.php/Gajim#OMEMO_Support)

#### Gentoo
`layman -a flow && emerge gajim-omemo`

### Via PluginInstallerPlugin

Install the current stable version via the Gajim PluginManager. You *need* Gajim
version *0.16.5*. If your package manager does not provide an up to date version
you can install it from the official Mercurial repository. *DO NOT USE* gajim
0.16.4 it contains a vulnerability, which is fixed in 0.16.5.
```shell
hg clone https://hg.gajim.org/gajim
cd gajim
hg update gajim-0.16.5 --clean
```

**NOTE:** You *have* to install `python-axolotl` via `pip`. Depending on your setup you might
want to use `pip2` as Gajim is using python2.7. If you are using the official repository,
do not forget to install the `nbxmpp` dependency via pip or you package manager.

if you still have problems, we have written down the most common problems [here](https://github.com/omemo/gajim-omemo/wiki/It-doesnt-work,-what-should-i-do%3F-(Linux))

## Running
Enable *OMEMO Multi-End Message and Object Encryption* in the Plugin-Manager.
If your contact supports OMEMO you should see a new orange fish icon in the chat window.

Encryption will be enabled by default for contacts that support OMEMO.
If you open the chat window, the Plugin will tell you with a green status message if its *enabled* or *disabled*.
If you see no status message, your contact doesnt support OMEMO.
(**Beware**, every status message is green. A green message does not mean encryption is active. Read the message !)
You can also check if encryption is enabled/disabled, when you click on the OMEMO icon.

When you send your first message the Plugin will query your contacts encryption keys and you will
see them in a readable fingerprint format in the fingerprint window which pops up.
you have to trust at least **one** fingerprint to send messages.
you can receive messages from fingerprints where you didnt made a trust decision, but you cant
receive Messages from *not trusted* fingerprints

## Groupchat

Groupchat works only in rooms that are
- non-anonymous
- members-only
- works only with contacts that you have in your roster

## Filetransfer

For Filetransfer use the **httpupload** plugin.

For decrypting and showing pictures in chat use the **url_image_preview** plugin.

If you want to use these plugins together with *OMEMO* you have to install the `python-cryptography` package

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

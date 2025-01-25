# Gajim Plugins

In this place you will find all plugins that are written for [Gajim](https://gajim.org) by the community. If you experience any problems with those plugins, please report them here.

## How to install plugins

**Note:** Some plugins have external dependencies that need to be installed separately.
Check the [plugin's wiki page](https://dev.gajim.org/gajim/gajim-plugins/-/wikis/home#plugins-list) for details.

There are several ways to install a plugin:

- You can browse / download / enable / configure plugins from within Gajim via 'Gajim' > 'Plugins' menu.
- You can also clone the repository directly from our Git and copy it to:

    **Linux:** `~/.local/share/gajim/plugins/`

    **Windows:** `C:\Users\USERNAME\AppData\Roaming\Gajim\Plugins`

- Alternatively (for developing), you can also symlink the gajim-plugins repository to Gajim's plugin path:

    **Symlink:** `ln -s /path/to/gajim-plugins-repository/* ~/.local/share/gajim/plugins/`

**For each major Gajim version there is a different plugins branch. Gajim >=1.4 uses the `master` branch.**

| Version | Plugins branch |
| ------- | -------------- |
|Gajim master|[master branch](https://dev.gajim.org/gajim/gajim-plugins/tree/master)|
|Gajim 1.3|[1.3 branch](https://dev.gajim.org/gajim/gajim-plugins/tree/gajim_1.3)|
|Gajim 1.2|[1.2 branch](https://dev.gajim.org/gajim/gajim-plugins/tree/gajim_1.2)|
|Gajim 1.1|[1.1 branch](https://dev.gajim.org/gajim/gajim-plugins/tree/gajim_1.1)|
|Gajim 1.0|[1.0 branch](https://dev.gajim.org/gajim/gajim-plugins/tree/gajim_1.0)|

*Note: Using master branch for plugins requires frequent updates of both Gajim and plugins!*

## Development

You have written a new plugin or want to improve an existing one?

First, thanks for that! Here is how to start:

- Register an account on our Gitlab [here](https://dev.gajim.org/users/sign_in)
- Tell us about your plans at [gajim@conference.gajim.org](xmpp:gajim@conference.gajim.org?join)
- Fork the Gajim-Plugins [repository](https://dev.gajim.org/gajim/gajim-plugins)
- Check `./scripts/dev_env.sh` to get a environment with dependencies installed
- When you are finished, do a merge request against the main plugins repository. You can read about how to use git [here](https://dev.gajim.org/gajim/gajim/wikis/howtogit).
- Additionally, there is a list of [plugin events](https://dev.gajim.org/gajim/gajim/wikis/development/pluginsevents) which might be helpful

**Before you put in any work, please contact us on [gajim@conference.gajim.org](xmpp:gajim@conference.gajim.org?join)**

**Please do not use dev.gajim.org for any projects that are not directly for the benefit of Gajim!**

## Plugins list

All available plugins are listed [here](https://dev.gajim.org/gajim/gajim-plugins/wikis/home).

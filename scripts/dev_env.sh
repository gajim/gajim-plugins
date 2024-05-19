echo -e "\e[32mCreate virtualenv\e[0m"
python -m venv .venv
source .venv/bin/activate
echo -e "\e[32mInstall dependencies into virtualenv\e[0m"
PYGOBJECT_STUB_CONFIG=Gtk3,Gdk3,Soup3,GtkSource4 pip install "rich" "ruff>=0.3.2" "codespell[toml]>=2.2.6" "isort>=5.13.2" "PyGObject-stubs @ git+https://github.com/pygobject/pygobject-stubs.git" "gajim @ git+https://dev.gajim.org/gajim/gajim.git"
deactivate
echo -e "\e[32mFinshed\e[0m"
echo -e "\e[34mUse 'source .venv/bin/activate' to activate the virtualenv\e[0m"

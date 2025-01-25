echo -e "\e[32mCreate virtualenv\e[0m"
python -m venv .venv
source .venv/bin/activate
echo -e "\e[32mInstall dependencies into virtualenv\e[0m"
pip install "PyGObject-stubs @ git+https://github.com/pygobject/pygobject-stubs.git"
pip install "gajim @ git+https://dev.gajim.org/gajim/gajim.git"
pip install pre-commit
pre-commit install
deactivate
echo -e "\e[32mFinshed\e[0m"
echo -e "\e[34mUse 'source .venv/bin/activate' to activate the virtualenv\e[0m"

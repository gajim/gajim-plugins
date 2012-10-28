import ConfigParser
import sys
import os

def set(option, value):
    _file = open(path, 'w')
    cp.set('General', option, value)
    cp.write(_file)
    _file.close()

def set_defaults():
    cp.add_section('General')
    set('incoming_dir', '/home')

path = sys.path[1]
path = path + '/file_sharing/' + 'conf.cfg' 
cp = ConfigParser.ConfigParser()
if os.path.exists(path):
    _file = open(path)
    cp.readfp(_file)
    _file.close()
else:
    set_defaults()
INCOMING_DIR = cp.get('General', 'incoming_dir')



#!/usr/bin/env python3

# Reads ui files and creates a typed class

import logging
import sys
from pathlib import Path
from xml.etree import ElementTree

logging.basicConfig(level="INFO", format="%(levelname)s: %(message)s")
log = logging.getLogger()

in_path = Path(sys.argv[1])

CLASS_DEF = "\nclass %s(Gtk.Builder):"
ATTR = "\n    %s: %s"


class InvalidFile(Exception):
    pass


def make_class_name(path: Path) -> str:
    name = path.name.removesuffix(".ui")
    names = name.split("_")
    names = [name.capitalize() for name in names]
    return "".join(names) + "Builder"


def parse(path: Path) -> tuple[str, str]:
    log.info("Read %s", path)
    lines: list[str] = []
    string = ""
    tree = ElementTree.parse(path)

    if tree.find("template") is not None:
        raise InvalidFile

    for node in tree.iter(tag="object"):
        id_ = node.attrib.get("id")

        if id_ is None:
            continue
        klass = node.attrib["class"]
        if klass.startswith("GtkSource"):
            klass = f"GtkSource.{klass.removeprefix('GtkSource')}"
        elif klass.startswith("Atk"):
            klass = f"Atk.{klass.removeprefix('Atk')}"
        else:
            klass = f"Gtk.{klass.removeprefix('Gtk')}"

        lines.append(ATTR % (id_.replace("-", "_"), klass))

    klass_name = make_class_name(path)
    string += CLASS_DEF % klass_name

    if not lines:
        string += "\n    pass"
    else:
        for line in lines:
            string += line
    string += "\n\n"
    return klass_name, string


try:
    cls_name, string = parse(in_path)
except InvalidFile:
    sys.exit()

print(string)

import sublime
from . import util, scheme, persist
from xml.etree import ElementTree
from .persist import settings

import re
import os

OLD_SETTINGS_ITEMS = {"warning_color": "", "error_color": "", "mark_style": ""}
NEW_SETTINGS_ITEMS = {"force_xml_scheme": "", "styles": []}


COLOR_SCHEME_PREAMBLE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
'''


class XmlScheme(scheme.Scheme):
    """docstring for XmlScheme"""

    def generate_color_scheme_async(self):
        """
            Generate a modified copy of the current color scheme that contains SublimeLinter color entries.

            The current color scheme is checked for SublimeLinter color entries. If any are missing,
            the scheme is copied, the entries are added, and the color scheme is rewritten to Packages/User/SublimeLinter.

            """
        print("XmlScheme.generate_color_scheme called.")

        # build legacy style_parser
        from . import persist, highlight
        persist.linter_styles["default"] = {
            "types": {
                "warning": "sublimelinter.mark.warning",
                "error": "sublimelinter.mark.error"
            }
        }

        def get_mark_style():
            mark_style = persist.settings.get("mark_style", "outline")
            return re.sub(" ", "_", mark_style)

        persist.highlight_styles = {
            "sublimelinter.mark.warning": {
                "scope": "sublimelinter.mark.warning",
                "mark_style": get_mark_style(),
                "icon": persist.gutter_marks["warning"]
            },
            "sublimelinter.mark.error": {
                "scope": "sublimelinter.mark.error",
                "mark_style": get_mark_style(),
                "icon": persist.gutter_marks["error"]
            }
        }

        # Append style dicts with our styles to the style array
        scheme_text = sublime.load_resource(self.paths["scheme_orig"])
        plist = ElementTree.XML(scheme_text)
        styles = plist.find('./dict/array')

        print("self.nodes: ", self.nodes)

        unfound = self.parse_scheme_xml(
            persist.highlight_styles.keys(), text=scheme_text)
        if not unfound:
            return

        # create unfound styles
        self.gen_xml_nodes(unfound)
        styles.extend(self.get_nodes())

        mod_name = self.paths["scheme_name"] + ' (SL)'
        mod_scheme_path = os.path.join(
            self.paths["usr_dir_abs"], mod_name + '.hidden-tmTheme')

        content = ElementTree.tostring(plist, encoding='unicode')

        with open(mod_scheme_path, 'w', encoding='utf8') as f:
            f.write(COLOR_SCHEME_PREAMBLE)
            f.write(content)

        # Set the amended color scheme to the current color scheme
        scheme_path_rel = self.packages_relative_path(
            os.path.join(self.paths["usr_dir_rel"], os.path.basename(mod_scheme_path)))

        # TODO: is there another way to prevent entering vicious cycle?
        self.set_scheme_path(scheme_path_rel)

    def gen_xml_nodes(self, unfound):
        """"""

        def get_color(key, default):

            color = settings.get(key, default)
            if not color.startswith('#'):
                color = '#' + color
            return color

        d = [
            {
                "scope": "sublimelinter.mark.warning",
                "foreground": get_color("warning_color", "#DDB700")
            },
            {
                "scope": "sublimelinter.mark.error",
                "foreground": get_color("error_color", "#D02000")
            },
            {
                "scope": "sublimelinter.gutter-mark",
                "foreground": "#FFFFFF"
            }
        ]

        filtered = [f for f in d if f["scope"] in unfound]

        for item in filtered:
            self.assemble_node(item["scope"], item)

    def assemble_node(self, scope, input_dict):
        """Assembles single node as XML ElementTree object."""
        root = ElementTree.Element('dict')

        def append_kv(first, second, root=root):
            ElementTree.SubElement(root, 'key').text = first
            ElementTree.SubElement(root, 'string').text = second

        append_kv("scope", scope)
        ElementTree.SubElement(root, "key").text = "settings"
        d = ElementTree.SubElement(root, "dict")

        if input_dict.get("foreground"):
            append_kv("foreground", input_dict.get("foreground").upper(), d)

        # if input_dict.get("background"):
        #     append_kv("background", input_dict.get("background").upper(), d)

        # if input_dict.get("font_style"):
        #     append_kv("fontStyle", input_dict.get("font_style"), d)

        self.nodes[scope] = root

    def packages_relative_path(self, path, prefix_packages=True):
        """
        Return a Packages-relative version of path with '/' as the path separator.

        Sublime Text wants Packages-relative paths used in settings and in the plugin API
        to use '/' as the path separator on all platforms. This method converts platform
        path separators to '/'. If insert_packages = True, 'Packages' is prefixed to the
        converted path.

        """
        components = util.get_path_components(path)

        if prefix_packages and components and components[0] != 'Packages':
            components.insert(0, 'Packages')

        return '/'.join(components)


OLD_KEYS = ("warning_color", "error_color", "mark_style", "user")
NEW_KEYS = ("styles", "user")


def legacy_check(func):
    """"""
    force_xml_scheme = settings.get("force_xml_scheme")
    above_3148 = int(sublime.version()) > 3148

    # transfer mark style into setings
    mark_style = settings.get("mark_style")
    if above_3148 and mark_style:
        styles = settings.setdefault("styles", [])
        for s in styles:
            s["mark_style"] = mark_style

    keys = OLD_KEYS if above_3148 else NEW_KEYS

    def clean_settings():
        for key in keys:
            settings.pop(key)
    clean_settings()

    settings.save()

    # finally return
    if above_3148 and not force_xml_scheme:
        def func_wrapper():
            return func

        return func_wrapper()

    return XmlScheme

import sublime
from . import util, scheme
from xml.etree import ElementTree
from .persist import settings as merged_settings
from .const import SETTINGS_FILE

import re
import os
import shutil
import json

COLOR_SCHEME_PREAMBLE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
'''


def touch_dir(dir):
    if not os.path.exists(dir):
        os.makedirs(dir)


class XmlScheme(scheme.Scheme):
    def generate_color_scheme_async(self):
        """
            Generate a modified copy of the current color scheme that contains
            SublimeLinter color entries.

            The current color scheme is checked for SublimeLinter color entries.
            If any are missing, the scheme is copied, the entries are added,
            and the color scheme is rewritten to Packages/User/SublimeLinter.
        """
        # build legacy style_parser
        from . import persist
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

        unfound = self.parse_scheme_xml(
            persist.highlight_styles, text=scheme_text)
        if not unfound:
            return

        # create unfound styles
        xml_nodes = self.gen_xml_nodes(unfound)
        styles.extend(xml_nodes)

        mod_name = self.paths["scheme_name"] + ' (SL)'
        mod_scheme_path = os.path.join(self.paths["usr_dir_abs"],
                                       mod_name + '.hidden-tmTheme')

        content = ElementTree.tostring(plist, encoding='unicode')

        touch_dir(self.paths["usr_dir_abs"])  # ensure dir exists
        with open(mod_scheme_path, 'w', encoding='utf8') as f:
            f.write(COLOR_SCHEME_PREAMBLE + content)

        # Set the amended color scheme to the current color scheme
        scheme_path_rel = self.packages_relative_path(
            os.path.join(self.paths["usr_dir_rel"],
                         os.path.basename(mod_scheme_path)))

        self.set_scheme_path(scheme_path_rel)

    def gen_xml_nodes(self, unfound):
        nodes = []

        def get_color(key, default):
            color = merged_settings.get(key, default)
            if not color.startswith('#'):
                color = '#' + color
            return color

        d = [{
            "scope": "sublimelinter.mark.warning",
            "foreground": get_color("warning_color", "#DDB700")
        }, {
            "scope": "sublimelinter.mark.error",
            "foreground": get_color("error_color", "#D02000")
        }, {
            "scope": "sublimelinter.gutter-mark",
            "foreground": "#FFFFFF"
        }]

        filtered = [f for f in d if f["scope"] in unfound]

        for item in filtered:
            nodes.append(self.assemble_node(item["scope"], item))

        return nodes

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

        return root

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
NEW_KEYS = ("styles", "user", "show_hover_line_report", "force_xml_scheme",
            "show_hover_line_report", "show_hover_region_report")


def update_settings(min_version, usr_dir_abs):
    merged_settings.load()

    def migrate(settings):
        settings = settings.copy()

        if not min_version:
            remove_keys = NEW_KEYS
        else:
            remove_keys = OLD_KEYS
            mark_style = merged_settings.get("mark_style")
            if mark_style:
                styles = settings.get("styles", [])
                for s in styles:
                    s["mark_style"] = mark_style

            if settings.get("lint_mode") == "load/save":
                settings["lint_mode"] = "load_save"

        # Flatten settings dict.
        user_settings = settings.get('user')
        if user_settings:
            for key, old_value in user_settings.items():

                # If the user setting is the same as new default setting then skip it.
                if merged_settings.has_setting(key):
                    new_value = merged_settings.get(key)
                    if old_value == new_value:
                        continue

                # Special case: gutter_theme (if the user setting is the same as default skip it)
                if key == 'gutter_theme':
                    if old_value == 'Packages/SublimeLinter/gutter-themes/Default/Default.gutter-theme':
                        continue

                # Special case: delay (if the user setting is the same as default skip it)
                if key == 'delay':
                    if old_value == 0.25:
                        continue

                settings[key] = old_value

        # Remove no longer used settings.
        for key in remove_keys:
            settings.pop(key, None)

        return settings

    usr_settings_path = os.path.join(usr_dir_abs, SETTINGS_FILE)
    if os.path.exists(usr_settings_path):
        # not working with a single context and 'w+'
        with open(usr_settings_path, "r") as rf:
            settings = json.load(rf)

        migrated_settings = migrate(settings)

        # Avoid writing and reloading settings if no change.
        if settings != migrated_settings:
            print('SublimeLinter: write migrated settings')
            with open(usr_settings_path, "w") as wf:
                js = json.dumps(migrated_settings, indent=4, sort_keys=True)
                wf.write(js)

            print('SublimeLinter: reload settings')
            merged_settings.load()


def rm_old_dir(usr_dir_abs):
    usr_dir_abs = os.path.join(usr_dir_abs, "SublimeLinter")
    shutil.rmtree(usr_dir_abs, ignore_errors=True)


def legacy_check(func):
    min_version = int(sublime.version()) >= 3149  # version check
    usr_dir_abs = os.path.join(sublime.packages_path(), "User")

    update_settings(min_version, usr_dir_abs)

    if min_version and not merged_settings.get("force_xml_scheme"):
        # remove old User/SublimeLinter dir
        rm_old_dir(usr_dir_abs)

        def func_wrapper():
            return func

        return func_wrapper()

    return XmlScheme

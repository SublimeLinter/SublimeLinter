import json
import os
from abc import ABCMeta, abstractmethod
from xml.etree import ElementTree
from copy import deepcopy

import sublime
import re
from . import util, style
from collections import OrderedDict


MARK_COLOR_RE = (
    r'(\s*<string>sublimelinter\.{}</string>\s*\r?\n'
    r'\s*<key>settings</key>\s*\r?\n'
    r'\s*<dict>\s*\r?\n'
    r'(?:\s*<key>(?:background|fontStyle)</key>\s*\r?\n'
    r'\s*<string>.*?</string>\r?\n)*'
    r'\s*<key>foreground</key>\s*\r?\n'
    r'\s*<string>)#.+?(</string>\s*\r?\n)'
)

COLOR_SCHEME_PREAMBLE = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
'''


AUTO_SCOPE = re.compile("region\.[a-z]+?ish")


class Scheme(metaclass=ABCMeta):
    """This class provides global access to scheme editing."""

    def __init__(self):
        """ """
        self.nodes = {}

        self.prefs = {}
        self.scheme = ""  # later include into self.paths

        self.paths = {}

    def generate(self, from_reload=True):
        """
        Asynchronously call generate_color_scheme_async.

        from_reload is True if this is called from the change callback for user settings.

        """

        # If this was called from a reload of prefs, turn off the prefs observer,
        # otherwise we'll end up back here when ST updates the prefs with the new color.


        style.StyleParser()()

        self.update_paths()

        # First make sure the user prefs are valid. If not, bail.
        self.get_settings()
        if not (self.prefs and self.scheme):
            return

        # self.update_paths()

        if from_reload:
            from . import persist

            def prefs_reloaded():
                persist.settings.observe_prefs()

            persist.settings.observe_prefs(observer=prefs_reloaded)

        # ST crashes unless this is run async
        sublime.set_timeout_async(self.generate_color_scheme_async, 0)

    def get_settings(self):
        """Return preference object and color scheme """
        settings_path = os.path.join(
            self.paths["usr_dir"], 'Preferences.sublime-settings')

        # TODO: couldn't better use sublime.load_resource ??
        if (os.path.isfile(settings_path)):
            try:
                with open(settings_path, mode='r', encoding='utf-8') as f:
                    json = f.read()
                sublime.decode_value(json)
            except:
                from . import persist
                persist.printf(
                    'generate_color_scheme: Preferences.sublime-settings invalid, aborting'
                )
                return

        # TODO: or take prefs from persist?
        self.prefs = sublime.load_settings('Preferences.sublime-settings')
        self.scheme = self.prefs.get('color_scheme')
        self.paths["scheme_orig"] = self.get_original_theme(self.scheme)
        self.paths["scheme_base"] = os.path.basename(self.paths["scheme_orig"])
        self.paths["scheme_name"], self.paths["ext"] = os.path.splitext(
            self.paths["scheme_base"])

        self.paths["usr_dir_rel"] = os.path.join("User", "SublimeLinter")
        self.paths["usr_dir_abs"] = os.path.join(
            sublime.packages_path(), self.paths["usr_dir_rel"])

    def get_original_theme(self, current_scheme_path):
        current_scheme_file = current_scheme_path.split("/")[-1]
        pattern = re.sub(r" ?\(SL\) ?|hidden-", "", current_scheme_file)

        theme_list = sublime.find_resources(pattern)

        if theme_list:
            theme_list = [t for t
                          in theme_list
                          if "Packages/User/" not in t
                          ]

        if not theme_list:
            return current_scheme_path

        return theme_list[0]

    def update_paths(self):

        pck_dir = sublime.packages_path()

        self.paths.update({
                          "usr_dir": os.path.join(pck_dir, "User")
                          })

    def parse_scheme_xml(self, nodes, *, text):
        """ included in base class as used by both derived classes, despite 'XML'"""
        unfound_nodes = []

        for scope in nodes:
            match = re.search(MARK_COLOR_RE.format(
                re.escape(scope)),
                text)
            if not match:
                unfound_nodes.append(scope)

        return unfound_nodes

    @staticmethod
    def touch_dir(dir):
        """Create dir if it does not exist."""
        # TODO: need to make it recursive???
        if not os.path.exists(dir):
            os.makedirs(dir)

    def set_scheme_path(self, path):
        """Set 'color_scheme' to provided path if it is currently is not."""
        from . import persist
        print("path: ", path)
        print("self.scheme: ", self.scheme)

        if path != self.scheme:
            persist.printf("New scheme path detected. Updating.")
            self.prefs.set('color_scheme', path)
            sublime.save_settings('Preferences.sublime-settings')
        else:
            persist.printf("Old scheme path detected. Pass.")
            pass

    def get_dyn_rules(self):
        """Return sorted list of dicts."""
        s_dict = OrderedDict(sorted(self.dynamic_nodes.items()))
        return s_dict.values()

    def unfound_scopes_dialogue(self, unfound):
        from . import persist
        msg = "The following scopes have not been found in the color scheme:\n{}".format(
            "\n".join(unfound))
        persist.printf(msg)

    @abstractmethod
    def generate_color_scheme_async(self):
        """       """
        pass

    @abstractmethod
    def assemble_node(self, scope, input_dict, name=None):
        """"""
        pass


class XmlScheme(Scheme):
    """docstring for XmlScheme"""

    def generate_color_scheme_async(self):
        """
            Generate a modified copy of the current color scheme that contains SublimeLinter color entries.

            The current color scheme is checked for SublimeLinter color entries. If any are missing,
            the scheme is copied, the entries are added, and the color scheme is rewritten to Packages/User/SublimeLinter.

            """
        print("XmlScheme.generate_color_scheme called.")

        # Append style dicts with our styles to the style array
        scheme_text = sublime.load_resource(self.paths["scheme_orig"])
        plist = ElementTree.XML(scheme_text)
        styles = plist.find('./dict/array')
        styles.extend(self.get_dyn_rules())

        from . import persist

        unfound = self.parse_scheme_xml(
            self.static_nodes.keys(), text=scheme_text)
        if unfound:
            self.unfound_scopes_dialogue(unfound)

        print("self.paths['usr_dir_abs']: ", self.paths["usr_dir_abs"])

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

        if input_dict.get("background"):
            append_kv("background", input_dict.get("background").upper(), d)

        if input_dict.get("font_style"):
            append_kv("fontStyle", input_dict.get("font_style"), d)

        self.nodes[scope] = root

    def packages_relative_path(self, path, prefix_packages=True):
        """
        Return a Packages-relative version of path with '/' as the path separator.

        Sublime Text wants Packages-relative paths used in settings and in the plugin API
        to use '/' as the path separator on all platforms. This method converts platform
        path separators to '/'. If insert_packages = True, 'Packages' is prefixed to the
        converted path.

        """
        from . import util

        components = util.get_path_components(path)

        if prefix_packages and components and components[0] != 'Packages':
            components.insert(0, 'Packages')

        return '/'.join(components)


class JsonScheme(Scheme):

    def generate_color_scheme_async(self):
        """Generates scheme in format .subilme-color-scheme."""
        print("JsonScheme.generate_color_scheme called.")
        original_scheme = self.get_original_theme(self.scheme)
        scheme_text = sublime.load_resource(original_scheme)

        if self.paths["ext"] == ".sublime-color-scheme":
            scheme_dict = sublime.decode_value(scheme_text)
            unfound = self.parse_scheme_json(
                self.static_nodes, rules=scheme_dict.get("rules", {}))
        elif self.paths["ext"].endswith("tmTheme"):
            unfound = self.parse_scheme_xml(self.nodes, text=scheme_text)
        else:  # file extension not defined
            raise Exception

        # To ensure update when theme set to 'xxx (SL).tmTheme'
        self.set_scheme_path(self.paths["scheme_orig"])

        if not unfound and not self.nodes:
            print("No nodes to include")
            return

        new_scheme_path = os.path.join(self.paths["usr_dir"],
                                       self.paths["scheme_name"] +
                                       ".sublime-color-scheme"
                                       )

        if os.path.exists(new_scheme_path):
            with open(new_scheme_path, "r") as f:
                print("new_scheme_path exists")
                theme = json.load(f)

            old_rules = theme.get("rules")

            theme["rules"].clear()
            if old_rules and unfound:
                unfound = self.parse_scheme_json(unfound, rules=old_rules)

        if unfound:
            self.unfound_scopes_dialogue(unfound)

    def parse_scheme_json(self, scopes, *, rules):
        """Returns dict of {scope: style} not defined in json."""
        unfound_scopes = set(scopes)

        for node in rules:
            def_scopes = node.get("scope", "").split()
            unfound_scopes -= set(def_scopes)  # remove existing scopes
            if not unfound_scopes:
                return []

        return unfound_scopes

    def assemble_node(self, rule, scope):
        if not AUTO_SCOPE.match(scope):
            self.nodes[rule] = scope


def init_scheme(force_xml_scheme=False):
    """Returns either the modern json schme parser or old xml scheme parser. Depending on sublime version."""
    if int(sublime.version()) >= 3149 and not force_xml_scheme:
        return JsonScheme()

    return XmlScheme()

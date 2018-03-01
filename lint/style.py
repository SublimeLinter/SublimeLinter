import sublime
from . import persist, util

import logging
import os


logger = logging.getLogger(__name__)
linter_style_stores = {}
COLORIZE = True


def get_linter_style_store(name):
    try:
        return linter_style_stores[name]
    except KeyError:
        linter_style_stores[name] = store = LinterStyleStore(name)
        return store


def read_gutter_theme():
    theme_path = persist.settings.get('gutter_theme')
    theme_file = os.path.basename(theme_path)
    global COLORIZE
    COLORIZE = True

    if not theme_file.endswith(".gutter-theme"):
        theme_file += ".gutter-theme"

    theme_files = sublime.find_resources(theme_file)

    if theme_files:
        theme_file = theme_files[0]
        opts = util.load_json(theme_file)
        if opts:
            COLORIZE = opts.get("colorize", True)


class HighlightStyleStore:
    styles = {}

    @classmethod
    def update(self, name, dict):
        self.styles[name] = dict

    def has_style(self, style):
        return style in self.styles

    def get(self, style):
        return self.styles.get(style, {})

    def get_icon(f):
        def wrapper(*args):
            res = f(*args)
            key = args[1]

            if not res:
                logger.error("Styles are invalid. Please check your settings and restart Sublime Text.")
                return

            if key != "icon":
                return res
            else:
                if res in ("circle", "dot", "bookmark", "none"):  # Sublime Text has some default icons
                    return res
                elif res != os.path.basename(res):
                    return res
                else:
                    theme = persist.settings.get('gutter_theme')
                    return 'Packages/SublimeLinter/gutter-themes/{}/{}.png'.format(theme, res)

        return wrapper

    @get_icon
    def get_val(self, key, style, error_type):
        """Look up style definition in that order of precedence.

        1. Individual style definition.
        2. Linter error type
        3. Default error type
        """
        # 1. Individual style definition.
        y = self.styles.get(style, {}).get(key)
        if y:
            return y

        styles = self.styles

        def fetch_style(linter_name):
            x = [v.get(key) for k, v
                 in styles.items()
                 if linter_name in k and error_type in v.get("types", [])]

            if x[0]:
                return x[0]

        base, linter, ext = style.split(".")

        # 2. Linter error type
        if linter != "default":
            val = fetch_style(linter)
            if val:
                return val

        # 3. Default error type
        val = fetch_style("default")
        if val:
            return val


class LinterStyleStore:
    all_linter_styles = {}
    default_styles = {}

    @classmethod
    def update(cls, name, dict):
        if name == "default":
            cls.default_styles = dict
        else:
            cls.all_linter_styles[name] = dict

    def __init__(self, linter_name):
        self.linter_styles = self.all_linter_styles.get(linter_name, {})

    def traverse_dict(self, dict, error_type):
        return dict.get("types", {}).get(error_type)

    def get_default_style(self, error_type):
        """Return default style for error_type of this linter.

        If not found returns style of SublimeLinter error_type.
        """
        lint_def = self.traverse_dict(self.linter_styles, error_type)
        if lint_def:
            return lint_def

        # default_styles = persist.linter_styles.get("default")
        return self.traverse_dict(self.default_styles, error_type)

    def get_style(self, code, error_type):

        style = self.linter_styles.get("codes", {}).get(code)

        if not style:
            style = self.get_default_style(error_type)

        return style


class StyleParser:
    def __call__(self):
        linter_style_stores.clear()
        LinterStyleStore.all_linter_styles.clear()
        LinterStyleStore.default_styles.clear()
        HighlightStyleStore.styles.clear()

        rule_validities = []

        # 1 - for default styles
        styles = persist.settings.get("styles", [])
        validity = self.parse_styles(styles, "default")
        rule_validities.append(validity)

        # 2 - for linters
        for linter_name, d in persist.settings.get("linters", {}).items():
            styles = d.get("styles")
            if not styles:
                continue
            validity = self.parse_styles(styles, linter_name)
            rule_validities.append(validity)

        if False in rule_validities:
            sublime.error_message(
                "SublimeLinter: One or more style settings invalid.\nCheck console for details."
            )

    def parse_styles(self, custom_styles, linter_name):
        all_rules_valid = True
        lint_dict = {}
        lint_dict["types"] = {}
        lint_dict["codes"] = {}

        rule_name_tmpl = "sublime_linter." + linter_name + ".style_{0:03d}"

        for i, node in enumerate(custom_styles):
            style_dict = {}

            # 1 - define style
            # scopes => scheme.py
            rule_name = rule_name_tmpl.format(i + 1)

            def transfer_style_item(key):
                if key in node:
                    style_dict[key] = node[key]

            # styles => highlight.py
            transfer_style_item("scope")
            transfer_style_item("mark_style")

            if persist.settings.has('gutter_theme'):
                transfer_style_item("icon")
                transfer_style_item("priority")

            types = node.get("types")
            if types:
                style_dict["types"] = types

            # 2 - define targets
                for type_name in node.get("types"):
                    lint_dict["types"][type_name] = rule_name

            for code in node.get("codes", []):
                lint_dict["codes"][code] = rule_name

            HighlightStyleStore.update(rule_name, style_dict)

        LinterStyleStore.update(linter_name, lint_dict)

        return all_rules_valid

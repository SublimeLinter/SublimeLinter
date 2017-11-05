import re
from . import persist, highlight, util
from .const import STYLE_KEYS, TARGET_KEYS


class StyleParser:
    """"""

    def __call__(self):
        print("StyleParser.create_styles called")

        # 1 - for default styles
        styles = persist.settings.get("styles", [])
        self.parse_styles(styles, "default")

        # 2 - for linters
        for linter_name, d in persist.settings.get("linters", {}).items():
            styles = d.get("styles")
            if not styles:
                continue
            self.parse_styles(styles, linter_name)

    def parse_styles(self, custom_styles, linter_name):
        """ """

        lint_dict = {}
        lint_dict["types"] = {}
        lint_dict["codes"] = {}

        rule_name_tmpl = "sublimelinter." + linter_name + ".style_{0:03d}"

        for i, node in enumerate(custom_styles):
            style_dict = {}

            # 0 - check node
            # TODO: find better corrupt style handling here
            try:
                self.is_node_valid(node)
            except CorruptStyleDefintion:
                continue

            # 1 - define style
            # scopes => scheme.py
            rule_name = rule_name_tmpl.format(i + 1)
            persist.scheme.assemble_node(rule_name, node["scope"])

            def transfer_style_item(key):
                if key in node:
                    style_dict[key] = node[key]

            # styles => highlight.py
            transfer_style_item("scope")
            transfer_style_item("mark_style")

            if persist.has_gutter_theme:
                transfer_style_item("icon")
                transfer_style_item("priority")

            persist.highlight_styles[rule_name] = style_dict

            # 2 - define targets
            for type_name in node.get("types", []):
                lint_dict["types"][type_name] = rule_name

            for code in node.get("codes", []):
                lint_dict["codes"][code] = rule_name

        persist.linter_styles[linter_name] = lint_dict

    def is_node_valid(self, node):
        msg = None

        if "scope" not in node:
            msg = "No 'scope' declared. node:\n{}".format(node)
        elif not util.any_key_in(node, STYLE_KEYS):
            msg = "No 'mark_style' nor 'icon' declared. node:\n{}".format(node)
        elif not util.any_key_in(node, TARGET_KEYS):
            msg = "No target definition found: Neither 'types' nor 'codes' declared:\n{}".format(node)

        if msg:
            raise CorruptStyleDefintion(msg)


class CorruptStyleDefintion(Exception):
    """Raise this when node in custom styling is missing necessary definitions or contains unknown keywords
    """
    pass

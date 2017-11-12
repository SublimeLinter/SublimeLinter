import sublime
import re
from . import persist, highlight, util
from .const import STYLE_KEYS, TARGET_KEYS, INVALID_RULE_MSG, CHECK_CONSOLE_MSG
import json


class StyleParser:
    """"""

    def __call__(self):
        print("StyleParser.create_styles called.")
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

        # 3 - inform user about invalid rules
        if False in rule_validities:
            sublime.error_message(INVALID_RULE_MSG + CHECK_CONSOLE_MSG)

    def parse_styles(self, custom_styles, linter_name):
        """ """

        all_rules_valid = True
        lint_dict = {}
        lint_dict["types"] = {}
        lint_dict["codes"] = {}

        rule_name_tmpl = "sublime_linter." + linter_name + ".style_{0:03d}"

        for i, node in enumerate(custom_styles):
            style_dict = {}

            # 0 - check node
            if not self.is_node_valid(node, linter_name):
                all_rules_valid = False
                continue

            # 1 - define style
            # scopes => scheme.py
            rule_name = rule_name_tmpl.format(i + 1)
            persist.scheme.add_scope(node["scope"])

            def transfer_style_item(key):
                if key in node:
                    style_dict[key] = node[key]

            # styles => highlight.py
            transfer_style_item("scope")
            transfer_style_item("mark_style")

            if persist.has_gutter_theme:
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

            persist.highlight_styles[rule_name] = style_dict

        persist.linter_styles[linter_name] = lint_dict

        return all_rules_valid

    def is_node_valid(self, node, linter_name):
        errors = []

        if "scope" not in node:
            errors.append("No 'scope' declared.")
        if not util.any_key_in(node, STYLE_KEYS):
            errors.append("Neither 'mark_style' nor 'icon' declared.")
        if not util.any_key_in(node, TARGET_KEYS):
            errors.append("Neither 'types' nor 'codes' declared.")

        if errors:
            msg = "Style rule is corrupt for: {}\n".format(linter_name)
            msg += "\n".join(errors)
            msg += json.dumps(node, indent=4, sort_keys=True)
            persist.printf(msg)
            return False

        return True

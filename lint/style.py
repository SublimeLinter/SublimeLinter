import re


AUTO_SCOPE = re.compile("region\.[a-z]+?ish")


class StyleParser:
    """"""

    def __init__(self):
        # TODO: refactor, move variables down into create_styles
        # __call__
        from . import persist, highlight
        self.settings = persist.settings

        self.highlight = highlight.Highlight()
        self.scheme = persist.scheme
        self.linter_styles = persist.linter_styles

        self.has_gutter_theme = persist.has_gutter_theme

    def create_styles(self):
        print("StyleParser.create_styles called")
        from . import persist

        # 1 - for default styles
        styles = self.settings.get("styles", [])
        self.parse_styles(styles, "default")

        # 2 - for linters
        for linter_name, d in self.settings.get("linters", {}).items():
            styles = d.get("styles")
            if not styles:
                continue
            self.parse_styles(styles, linter_name)



    def parse_styles(self, custom_styles, linter_name):
        """ """
        from . import util, persist  # TODO: clean imports up

        lint_dict = {}
        lint_dict["types"] = {}
        lint_dict["codes"] = {}
        lint_dict["scopes"] = {}
        scope_name_tmpl = "sublimelinter." + linter_name + ".style_{0:03d}"

        scope_index = 1  # index for counting self-defined scopes

        for i, node in enumerate(custom_styles):
            style_dict = {}

            if not util.any_key_in(node, util.STYLE_KEYS):
                # no styling provided => skip
                msg = "No style definition found: Neither 'scope' nor any of 'foreground', 'background' or 'font_style' declared. node:\n{}".format(
                    node)
                raise CorruptStyleDefintion(msg)

            # 1 - define style
            # scheme => scheme.py
            if "scope" in node:
                scope_name = node["scope"]
                # do not build nodes for auto generarted scopes, like
                # 'region.greenish'
                if not re.match(AUTO_SCOPE, scope_name):
                    self.scheme.assemble_node(scope_name, node)

            else:
                scope_name = scope_name_tmpl.format(scope_index)
                self.scheme.assemble_node(scope_name, node)
                scope_index += 1

            # mark and gutter style => highlight.py
            if self.has_gutter_theme:
                if "icon" in node:
                    style_dict["icon"] = node["icon"]

                if "priority" in node:
                    style_dict["priority"] = node["priority"]

                if "mark_style" in node:
                    style_dict["mark_style"] = re.sub(" ", "_", node["mark_style"])

                self.highlight.styles[scope_name] = style_dict

            # 2 - define targets
            if not util.any_key_in(node, util.TARGET_KEYS):
                msg = "No target definition found: Neither 'types' nor 'codes' declared:\n{}".format(
                    node)

                raise CorruptStyleDefintion(msg)

            for type_name in node.get("types", []):
                if type_name not in ("warning", "error"):
                    msg = "type_name: {} not defined".format(type_name)
                    raise CorruptStyleDefintion(msg)
                lint_dict["types"][type_name] = scope_name

            for code in node.get("codes", []):
                lint_dict["codes"][code] = scope_name

        persist.linter_styles[linter_name] = lint_dict


class CorruptStyleDefintion(Exception):
    """Raise this when node in custom styling is missing necessary definitions or contains unknown keywords
    """

    pass

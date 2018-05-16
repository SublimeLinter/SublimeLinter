import sublime
from . import persist, util

from itertools import chain
import logging
import os


logger = logging.getLogger(__name__)

COLORIZE = True


def read_gutter_theme():
    global COLORIZE
    COLORIZE = True

    theme_path = persist.settings.get('gutter_theme')
    theme_file = os.path.basename(theme_path)
    if not theme_file.endswith(".gutter-theme"):
        theme_file += ".gutter-theme"

    theme_files = sublime.find_resources(theme_file)

    if theme_files:
        theme_file = theme_files[0]
        opts = util.load_json(theme_file)
        if opts:
            COLORIZE = opts.get("colorize", True)


def get_value(key, error, default=None):
    linter, code, error_type = error['linter'], error['code'], error['error_type']

    linter_styles = persist.settings.get('linters', {}).get(linter, {}).get('styles', [])
    default_styles = persist.settings.get('styles', [])

    for style_definition in linter_styles:
        if code in style_definition.get('codes', []):
            try:
                return style_definition[key]
            except KeyError:
                ...

    for style_definition in chain(linter_styles, default_styles):
        if error_type in style_definition.get('types', []):
            try:
                return style_definition[key]
            except KeyError:
                ...

    return default


def get_icon(error):
    icon = get_value('icon', error)

    if icon in ("circle", "dot", "bookmark", "none"):  # Sublime Text has some default icons
        return icon
    elif icon != os.path.basename(icon):
        return icon
    elif persist.settings.get('gutter_theme').endswith('.gutter-theme'):
        theme_path = os.path.dirname(persist.settings.get('gutter_theme'))
        if not icon.endswith('.png'):
            icon += '.png'
        return '{}/{}'.format(theme_path, icon)
    else:
        theme = persist.settings.get('gutter_theme')
        if not icon.endswith('.png'):
            icon += '.png'
        return 'Packages/SublimeLinter/gutter-themes/{}/{}'.format(theme, icon)

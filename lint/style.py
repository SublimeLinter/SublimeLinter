import sublime
from . import persist, util

from itertools import chain
import logging
import os


logger = logging.getLogger(__name__)

COLORIZE = True
WHITE_SCOPE = 'region.whitish'  # hopefully a white color
DEFAULT_STYLES = None  # holds the styles we ship as the default settings


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
    global_styles = persist.settings.get('styles', [])
    default_styles = get_default_styles()

    for style_definition in linter_styles:
        if code in style_definition.get('codes', []):
            try:
                return style_definition[key]
            except KeyError:
                ...

    for style_definition in chain(linter_styles, global_styles, default_styles):
        if error_type in style_definition.get('types', [error_type]):
            try:
                return style_definition[key]
            except KeyError:
                ...

    return default


def get_default_styles():
    # Using `yield from` to load the defaults on first usage, possibly never.
    global DEFAULT_STYLES

    if DEFAULT_STYLES is None:
        try:
            defaults = util.load_json(
                'SublimeLinter.sublime-settings', from_sl_dir=True)
        except Exception:
            logger.warning("Could not load the default styles")
            DEFAULT_STYLES = []
        else:
            DEFAULT_STYLES = defaults.get('styles', [])

    yield from DEFAULT_STYLES


def get_icon(error):
    icon = get_value('icon', error, 'none')

    if icon in ('circle', 'dot', 'bookmark', 'none'):  # Sublime Text has some default icons
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


def get_icon_scope(error):
    if COLORIZE:
        return get_value('scope', error)
    else:
        return WHITE_SCOPE

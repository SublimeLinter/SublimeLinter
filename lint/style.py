from functools import lru_cache
from itertools import chain
import logging
import os

import sublime
from . import events, persist, util


logger = logging.getLogger(__name__)

COLORIZE = True
WHITE_SCOPE = 'region.whitish'  # hopefully a white color
DEFAULT_STYLES = None  # holds the styles we ship as the default settings


@events.on('plugin_loaded')
def on_plugin_loaded():
    read_gutter_theme()


@events.on('settings_changed')
def on_settings_changed(settings, **kwargs):
    clear_caches()
    if settings.has_changed('gutter_theme'):
        read_gutter_theme()


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


def clear_caches():
    get_value_.cache_clear()
    get_icon_.cache_clear()


def get_value(key, error, default=None):
    linter, code, error_type = error['linter'], error['code'], error['error_type']
    return get_value_(key, linter, code, error_type, default)


@lru_cache(maxsize=128)
def get_value_(key, linter, code, error_type, default):
    linter_styles = persist.settings.get('linters', {}).get(linter, {}).get('styles', [])
    global_styles = persist.settings.get('styles', [])
    for style_definition in linter_styles:
        if code in style_definition.get('codes', []):
            try:
                return style_definition[key]
            except KeyError:
                ...

    for style_definition in linter_styles:
        # For linter_styles, do not auto fill 'types' if the user already
        # provided 'codes'
        default = [] if 'codes' in style_definition else [error_type]
        if error_type in style_definition.get('types', default):
            try:
                return style_definition[key]
            except KeyError:
                ...

    default_styles = get_default_styles()
    for style_definition in chain(global_styles, default_styles):
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
    # type: (persist.LintError) -> str
    linter, code, error_type = error['linter'], error['code'], error['error_type']
    return get_icon_(linter, code, error_type)


@lru_cache(maxsize=16)
def get_icon_(linter, code, error_type):
    # type: (persist.LinterName, str, str) -> str
    icon = get_value_('icon', linter, code, error_type, 'none')

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
    # type: (persist.LintError) -> str
    if COLORIZE:
        return get_value('scope', error)
    else:
        return WHITE_SCOPE

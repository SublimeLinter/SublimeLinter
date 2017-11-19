PLUGIN_NAME = 'SublimeLinter'
SETTINGS_FILE = PLUGIN_NAME + ".sublime-settings"

PROTECTED_REGIONS_KEY = "sublime_linter.protected_regions"

ST_ICONS = ("circle", "dot", "bookmark")

STYLE_KEYS = ("mark_style", "icon")
TARGET_KEYS = ("types", "codes")

MSG_HUSK = PLUGIN_NAME + "\n{}\n"
INVALID_RULE_MSG = MSG_HUSK.format("One or more style settings invalid.")
UNFOUND_SCOPES_MSG = MSG_HUSK.format(
    "One or more scopes not found in current color scheme.")
CHECK_CONSOLE_MSG = "\nCheck console for details."

WARNING = 'warning'
ERROR = 'error'
WARN_ERR = (WARNING, ERROR)

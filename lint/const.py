import os

PLUGIN_NAME = "SublimeLinter"
SETTINGS_FILE = PLUGIN_NAME + ".sublime-settings"
# Get the name of the plugin directory, which is the parent of this file's directory
PLUGIN_DIRECTORY = os.path.basename(os.path.dirname(os.path.dirname(__file__)))

PROTECTED_REGIONS_KEY = "sublime_linter.protected_regions"
STATUS_KEY = "sublime_linter_status"

WARNING = "warning"
ERROR = "error"
WARN_ERR = (WARNING, ERROR)
INBUILT_ICONS = ("circle", "dot", "bookmark", "none")  # 'none' added as well

LINT_MODES = (
    ('background', 'Lint whenever the text is modified'),
    ('load_save', 'Lint only when a file is loaded or saved'),
    ('manual', 'Lint only when requested')
)

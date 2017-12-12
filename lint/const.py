import os

PROTECTED_REGIONS_KEY = "sublime_linter.protected_regions"
STATUS_KEY = "sublime_linter_status"

WARNING = "warning"
ERROR = "error"
WARN_ERR = (WARNING, ERROR)
INBUILT_ICONS = ("circle", "dot", "bookmark", "none")

LINT_MODES = (
    ('background', 'Lint whenever the text is modified'),
    ('load_save', 'Lint only when a file is loaded or saved'),
    ('manual', 'Lint only when requested')
)

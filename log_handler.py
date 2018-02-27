import logging
import sublime

from .lint import util


DEBUG_FALSE_LEVEL = logging.WARNING
DEBUG_TRUE_LEVEL = logging.INFO
ERROR_PANEL_LEVEL = logging.ERROR
STATUS_BAR_LEVEL = logging.WARNING

logger = logging.getLogger('SublimeLinter')
logger.setLevel(logging.DEBUG)
handler = None
error_panel_handler = None
status_bar_handler = None


def install():
    install_std_handler()
    install_error_panel_handler()
    install_status_bar_handler()

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    settings.add_on_change('SublimeLinter._logging', install_std_handler)


def plugin_unloaded():
    if handler:
        logger.removeHandler(handler)
    if error_panel_handler:
        logger.removeHandler(error_panel_handler)
    if status_bar_handler:
        logger.removeHandler(status_bar_handler)

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    settings.clear_on_change('SublimeLinter._logging')


def install_std_handler():
    global handler
    if handler:
        logger.removeHandler(handler)

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    level = settings.get('debug', False)

    if level is False:
        level = DEBUG_FALSE_LEVEL
        formatter = TaskNumberFormatter(
            fmt="SublimeLinter: {LEVELNAME}{message}",
            style='{')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
    else:
        if level is True:
            level = DEBUG_TRUE_LEVEL
        else:
            level = logging.getLevelName(level.upper())

        formatter = TaskNumberFormatter(
            fmt="SublimeLinter: {TASK_NUMBER}{filename}:{lineno}: {LEVELNAME}{message}",
            style='{')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)

    handler.setLevel(level)
    logger.addHandler(handler)
    logger.setLevel(min(ERROR_PANEL_LEVEL, STATUS_BAR_LEVEL, level))
    logger.info(
        'Logging installed; log level {}'.format(logging.getLevelName(level))
    )


def install_error_panel_handler():
    global error_panel_handler
    if error_panel_handler:
        logger.removeHandler(error_panel_handler)

    formatter = TaskNumberFormatter(
        fmt="SublimeLinter: {TASK_NUMBER}{LINTER_NAME}{FILENAME}{levelname}:\n\n"
            " {message}",
        style='{')
    error_panel_handler = ErrorPanelHandler()
    error_panel_handler.setFormatter(formatter)
    error_panel_handler.setLevel(ERROR_PANEL_LEVEL)

    logger.addHandler(error_panel_handler)


def install_status_bar_handler():
    global status_bar_handler
    if status_bar_handler:
        logger.removeHandler(status_bar_handler)

    formatter = TaskNumberFormatter(fmt="SublimeLinter: {message}", style="{")
    status_bar_handler = StatusBarHandler()
    status_bar_handler.setFormatter(formatter)
    status_bar_handler.setLevel(STATUS_BAR_LEVEL)

    logger.addHandler(status_bar_handler)


class TaskNumberFormatter(logging.Formatter):
    def format(self, record):
        thread_name = record.threadName
        if thread_name.startswith('LintTask|'):
            _, task_number, linter_name, filename = thread_name.split('|')
            record.TASK_NUMBER = '#{} '.format(task_number)
            record.LINTER_NAME = linter_name + ' '
            record.FILENAME = filename + ' '
        else:
            record.TASK_NUMBER = ''
            record.LINTER_NAME = ''
            record.FILENAME = ''

        levelno = record.levelno
        if levelno > logging.INFO:
            record.LEVELNAME = record.levelname + ': '
        else:
            record.LEVELNAME = ''

        return super().format(record)


class ErrorPanelHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            util.message(msg)
        except Exception:
            self.handleError(record)


class StatusBarHandler(logging.Handler):
    def emit(self, record):
        if record.levelno != STATUS_BAR_LEVEL:
            return

        try:
            msg = self.format(record)
            window = sublime.active_window()
            window.status_message(msg)
        except Exception:
            self.handleError(record)

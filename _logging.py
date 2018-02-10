import logging
import sublime

from .lint import util


logger = logging.getLogger(__package__)
logger.setLevel(logging.DEBUG)
handler = None
error_panel_handler = None


def plugin_loaded():
    install_std_handler()
    install_error_panel_handler()

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    settings.add_on_change('SublimeLinter._logging', install_std_handler)


def plugin_unloaded():
    if handler:
        logger.removeHandler(handler)
    if error_panel_handler:
        logger.removeHandler(error_panel_handler)

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    settings.clear_on_change('SublimeLinter._logging')


def install_std_handler():
    global handler
    if handler:
        logger.removeHandler(handler)

    settings = sublime.load_settings("SublimeLinter.sublime-settings")
    level = settings.get('debug', False)

    if level is False:
        formatter = TaskNumberFormatter(
            fmt="SublimeLinter: {LEVELNAME}{message}",
            style='{')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(logging.WARNING)

        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    else:
        if level is True:
            level = logging.DEBUG
        else:
            level = logging.getLevelName(level.upper())

        formatter = TaskNumberFormatter(
            fmt="SublimeLinter:{thread_info} {filename}:{lineno}: {LEVELNAME}{message}",
            style='{')
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        handler.setLevel(level)

        logger.addHandler(handler)
        logger.setLevel(min(logging.WARNING, level))


def install_error_panel_handler():
    global error_panel_handler
    if error_panel_handler:
        logger.removeHandler(error_panel_handler)

    formatter = logging.Formatter(
        fmt="SublimeLinter: {levelname}: {message}",
        style='{')
    error_panel_handler = ErrorPanelHandler()
    error_panel_handler.setFormatter(formatter)
    error_panel_handler.setLevel(logging.WARNING)

    logger.addHandler(error_panel_handler)


class TaskNumberFormatter(logging.Formatter):
    def format(self, record):
        thread_name = record.threadName
        if thread_name.startswith('LintTask.'):
            _, task_number = thread_name.split('.')
            record.thread_info = ' #{}'.format(task_number)
        else:
            record.thread_info = ''

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

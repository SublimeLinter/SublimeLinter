import webbrowser
import re
import sublime
from . import persist


class Tooltip:

    """
    Class to manage tooltips
    """

    def __init__(self):

        self.style = ''
        self.load_setting()

    def load_setting(self):
        style_file = persist.settings.get('tooltip_theme', '')
        if style_file:
            self.style = '<style>' + re.sub(
                r'(\n+)|(\r+)|( +)|(\t+)',
                ' ',
                sublime.load_resource(style_file)
            ) + '</style>'

    def show(self, view, errors):
        self.load_setting()
        syntax = persist.get_syntax(view)
        divContent = ''
        for err in errors:
            divContent += '<p><a href="open:'
            + syntax + ' ' + err + '">' + err
            + '</a></p>'
        view.show_popup(
            ''.join(self.style)
            + '<div class="content">' + divContent + '</div>',
            max_width=600,
            on_navigate=self.on_navigate
            )
        divContent = ''

    def on_navigate(self, href):
        params = href.split(':')
        param = ''
        for i, s in enumerate(params):
            if i == 0:
                pass
            else:
                param += s
        if params[0] == 'open':
            webbrowser.open(
                'https://www.google.hu/#q=' + self.to_query_string(''+param)
            )

    def to_query_string(self, str):
        ret = ''
        for c in str:
            ret += self.match(c)
        sublime.status_message(ret)
        return ret

    def match(self, ch):
        if ch == ' ':
            return '+'
        if ch == '#':
            return '%23'
        if ch == ',':
            return '%2C'
        else:
            return ch

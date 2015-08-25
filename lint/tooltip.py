import webbrowser
import re
import sublime
from . import persist

class Tooltip:
    """Class to manage tooltips"""
    def __init__(self):
        self.style = ''
        self.search_engine = ''
        self.load_setting()

    def load_setting(self):
        style_file = persist.settings.get('tooltip_theme', '')
        if style_file:
            self.style = '<style>' + re.sub(r'(\n+)|(\r+)|( +)|(\t+)', ' ', sublime.load_resource(style_file)) + '</style>'
        self.search_engine = persist.settings.get('search_engine', 'https://google.com/#q=')

    def show(self, view, errors):
        self.load_setting()
        syntax = persist.get_syntax(view)
        divContent = ''
        for err in errors:
            divContent += '<p><a href="open:' + syntax + ' ' + err + '">' + err + '</a></p>'
        view.show_popup(''.join(self.style) + '<div class="content">' + divContent +'</div>', max_width=600, on_navigate=self.on_navigate)
        divContent = ''

    def on_navigate(self, href):
        
        def to_query_string(str):

            def match(ch):
                if ch == ' ': return '+'
                if ch == '#': return '%23'
                if ch == ',': return '%2C'
                else: return ch

            ret = ''
            for c in str:
                ret += match(c)
            sublime.status_message(ret)
            return ret
	    
        params = href.split(':')
        param = ''
        for i,s in enumerate(params):
            if i == 0: pass
            else: param += s
        if params[0] == 'open':
            #sublime.status_message("mess")
            webbrowser.open(self.search_engine + to_query_string(''+param))

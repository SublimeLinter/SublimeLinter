import json
import os
import tempfile

from lint.linter import Linter
from lint.util import communicate, find

class Java(Linter):
    language = 'java'
    cmd = ('eclim', '-command', 'java_src_update')
    regex = r'.'

    def communicate(self, cmd, code):
        project = find(os.path.dirname(self.filename), '.project', True)
        if not project:
            return

        filename = self.filename.replace(project, '', 1).lstrip(os.sep)
        project = os.path.basename(project)

        # can't stdin or temp use file - hack time?
        # this *could* become a tmp directory
        # but I'd need to know all files to copy
        # from the source project
        tmp = tempfile.mktemp()
        os.rename(self.filename, tmp)
        # at least we get some inode protection on posix
        inode = None

        with open(self.filename, 'wb') as f:
            f.write(code)
            if os.name == 'posix':
                inode = os.stat(self.filename).st_ino

        try:
            cmd = cmd + ('-p', project, '-f', filename, '-v')
            output = communicate(cmd, '')
        finally:
            if inode is not None:
                new_inode = os.stat(self.filename).st_ino
                if new_inode != inode:
                    # they saved over our tmp file, bail
                    return output

            os.unlink(self.filename)
            os.rename(tmp, self.filename)

        return output

    def find_errors(self, output):
        try:
            obj = json.loads(output)
            for item in obj:
                # TODO: highlight warnings in a different color?
                # warning = item['warning']
                line, col = item['line']-1, item['column']-1
                message = item['message']
                yield True, line, col, message, None
        except Exception:
            error = 'eclim error'
            if 'Connection refused' in output:
                error += ' Connection Refused'
            yield True, 0, None, error, None
            # maybe do this on line one?
            # yield {"eclim_exception": str(e)}

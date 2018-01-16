from . import util
from .const import WARNING, ERROR


class ErrorStore(util.Borg):

    def __init__(self):
        self.data = {}

    def __setitem__(self, vid, vdict):
        self.data[vid] = {
            "line_dicts": vdict,
            "we_count_view": {},
            "we_count_lines": {}
        }

        self._count_we(vid)

    def __getitem__(self, key):
        return self.data[key]

    def pop(self, vid, default=None):
        self.data.pop(vid, default)

    def clear(self):
        """Delete all errors and empties caches."""
        self.data = {}

    def get_view_dict(self, vid):
        return self.data.get(vid, {})

    def get_line_dict(self, vid, lineno):
        return self.get_view_dict(vid).get("line_dicts", {}).get(lineno, {})

    def get_region_dict(self, vid, lineno, colno):

        line_dict = self.get_line_dict(vid, lineno)

        filtered_dict = util.get_new_dict()

        for error_type, dc in line_dict.items():
            filtered_dict[error_type] = []
            for d in dc:
                if d["start"] <= colno <= d["end"]:
                    filtered_dict[error_type].append(d)

        return filtered_dict

    def get_view_we_count(self, vid):
        return self.get_view_dict(vid).get('we_count_view', {})

    def get_line_we_count(self, vid, line_no):
        return self.get_view_dict(vid).get("we_count_lines", {}).get(line_no)

    def _msg_count(self, l_dict):
        return len(l_dict.get(WARNING, [])), len(l_dict.get(ERROR, []))

    def _count_we(self, vid):
        vdict = self.data[vid]["line_dicts"]

        we_counts = []
        for line, d in vdict.items():
            w_count, e_count = self._msg_count(d)
            self.data[vid]["we_count_lines"][line] = {
                WARNING: w_count, ERROR: e_count}
            we_counts.append((w_count, e_count))

        we = [sum(x) for x in zip(*we_counts)]

        if not we:
            we = 0, 0
        self.data[vid]["we_count_view"] = {WARNING: we[0], ERROR: we[1]}

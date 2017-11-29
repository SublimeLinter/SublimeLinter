from functools import lru_cache
from . import util
from .const import WARNING, ERROR

import sublime


class ErrorStore(util.Borg):
    """docstring for ErrorStore"""

    def __init__(self):
        self.data = {}
        self.region_cache = {}

    def __setitem__(self, vid, vdict):
        self._clear_caches(vid)

        self.data[vid] = {
            "lints": vdict,
            "we_count_view": {},
            "we_count_lines": {}
        }

        self.region_cache[vid] = {}

        self._count_we(vid)

    def __getitem__(self, key, item):
        self.data[key] = item

    def pop(self, vid, default=None):
        self._clear_caches(vid)
        self.data.pop(vid, default)

    def _clear_caches(self, vid):  # TODO see if really necessary
        self.region_cache.pop(vid, None)

    def clear(self):
        """Deletes all errors and empties caches."""
        self.data = {}
        self.cache = {}

    def get_view_dict(self, vid):
        return self.data.get(vid)

    def get_we_count_line(self, vid, line_no):
        return self.data.get(vid, {}).get("we_count_lines", {}).get(line_no)

    def _msg_count(self, l_dict):
        return len(l_dict.get(WARNING, [])), len(l_dict.get(ERROR, []))

    def _count_we(self, vid):
        vdict = self.data.get(vid).get("lints")

        we_counts = []
        for line, d in vdict.items():
            w_count, e_count = self._msg_count(d)
            self.data[vid]["we_count_lines"][line] = {WARNING: w_count, ERROR: e_count}
            we_counts.append((w_count, e_count))

        we = [sum(x) for x in zip(*we_counts)]
        if not we:
            return
        self.data[vid]["we_count_view"] = {WARNING: we[0], ERROR: we[1]}

    def get_region_errors(self, line_dict, point):
        filtered_dict = {}
        for err_type, dc in line_dict.items():
            filtered_dict[err_type] = []
            for d in dc:
                region = d.get("region")
                if region and region.contains(point):
                    filtered_dict[err_type].append(d)
        return filtered_dict

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

        self.data[vid] = {"view_dict": vdict}
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

    def get_view_dict(self, view):  # TODO rename to get_focused_view_dict
        if util.is_scratch(view):
            return

        view = util.get_focused_view_id(view)

        if not view:
            return

        return self.data.get(view.id(), {}).get("view_dict")

    def get_we_count(self, vid):
        return self.cache.get(vid, {}).get("we_count")

    def msg_count(self, l_dict):
        return len(l_dict.get(WARNING, [])), len(l_dict.get(WARNING, []))

    def _count_we(self, vid):
        vdict = self.data.get(vid).get("view_dict")

        we_counts = []
        for line, d in vdict.items():
            w_count, e_count = self.msg_count(d)
            d[WARNING]["count"] = w_count
            d[ERROR]["count"] = e_count
            we_counts.append((w_count, w_count))

        we = [sum(x) for x in zip(*we_counts)]
        if not we:
            return
        self.data[vid]["we_count"] = {WARNING: we[0], ERROR: we[1]}

    def get_region_errors(self, line_dict, point):
        filtered_dict = {}
        for err_type, dc in line_dict.items():
            filtered_dict[err_type] = []
            for d in dc:
                region = d.get("region")
                if region and region.contains(point):
                    filtered_dict[err_type].append(d)
        return filtered_dict

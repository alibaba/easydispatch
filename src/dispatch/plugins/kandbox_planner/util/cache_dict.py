from collections import OrderedDict
import logging
log = logging.getLogger("CacheDict_Class")


# https://gist.github.com/davesteele/44793cd0348f59f8fadd49d7799bd306
class CacheDict(OrderedDict):
    """Dict with a limited length, ejecting LRUs as needed."""

    def __init__(self, *args, cache_len: int = 10, **kwargs):
        assert cache_len > 0
        self.cache_len = cache_len

        super().__init__(*args, **kwargs)

    def __setitem__(self, key, value):
        log.info(f"adding item for key: {key}, value: {value}")
        super().__setitem__(key, value)
        super().move_to_end(key)

        while len(self) > self.cache_len:
            oldkey = next(iter(self))
            log.info(f"deleting item for key: {key}")
            super().__delitem__(oldkey)

    def __getitem__(self, key):
        val = super().__getitem__(key)
        super().move_to_end(key)

        return val

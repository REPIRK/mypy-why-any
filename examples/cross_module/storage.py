def fetch(key):
    return _cache.get(key)


_cache: dict = {}

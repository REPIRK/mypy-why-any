"""The Any is born in storage.py; main.py gets `fetch` re-exported by service.py."""
from service import fetch

value = fetch("sku-1")
reveal_any_source(value)

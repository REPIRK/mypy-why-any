"""--explain-any adds the trace under errors about Any.

Run with: --warn-return-any --explain-any
"""
import json


def read_port(text: str) -> int:
    settings = json.loads(text)
    return settings["server"]["port"]

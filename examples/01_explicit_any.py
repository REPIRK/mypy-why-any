"""Any from an explicit annotation in a library stub (json.loads returns Any)."""
import json

config = json.loads('{"port": 8080}')
port = config["port"]
reveal_any_source(port)

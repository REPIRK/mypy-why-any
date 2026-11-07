"""Any from a module that mypy cannot find (run with --ignore-missing-imports)."""
import some_untyped_lib

client = some_untyped_lib.connect("db://local")
rows = client.query("select 1")
reveal_any_source(rows)

"""Any hidden inside a type: a bare `dict` means dict[Any, Any]."""


def counts(words: list[str]) -> dict:
    result: dict[str, int] = {}
    for w in words:
        result[w] = result.get(w, 0) + 1
    return result


reveal_any_source(counts(["a", "b"]))

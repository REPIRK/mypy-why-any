from storage import fetch


def current_price(sku: str) -> float:
    record = fetch(sku)
    return record.price

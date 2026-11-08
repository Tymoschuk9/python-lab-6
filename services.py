from __future__ import annotations
from models import Product

def calculate_inventory_value(products: list[Product]) -> float:
    if not products:
        return 0.0
    return float(sum(p.total_value for p in products))

def find_product(products: list[Product], name: str) -> Product | None:
    for product in products:
        if product.name.lower() == name.lower():
            return product
    return None

def filter_by_category(products: list[Product], category: str) -> list[Product]:
    return [p for p in products if p.category.lower() == category.lower()]

def find_most_expensive(products: list[Product]) -> Product | None:
    if not products:
        return None
    return max(products, key=lambda p: p.price)

"""Shop Manager package for Lab 01 (Variant 3)."""
from .models import Product
from .services import (
    calculate_inventory_value,
    find_product,
    filter_by_category,
    find_most_expensive
)

__all__ = [
    "Product",
    "calculate_inventory_value",
    "find_product",
    "filter_by_category",
    "find_most_expensive"
]

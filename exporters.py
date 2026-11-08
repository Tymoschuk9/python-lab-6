from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import List, Dict, Any

try:
    from .models import Product
    from .value_objects import Money
except (ImportError, ValueError):
    try:
        from shop.models import Product
        from shop.value_objects import Money
    except (ImportError, ValueError):
        from models import Product
        from value_objects import Money

def export_order(order: dict, path: Path) -> None:
    path.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")

def export_products_to_json(products: List[Product], path: Path) -> None:
    data = [
        {
            "product_id": p.product_id,
            "name": p.name,
            "category": p.category,
            "price": p.price_val,
            "quantity": p.quantity
        }
        for p in products
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def import_products_from_csv(path: Path) -> List[Product]:
    products: List[Product] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row.get("name") or row.get("price") is None or row.get("price") == "":
                raise ValueError("Malformed product record in CSV")
            try:
                price = float(row["price"])
                qty = int(row.get("quantity", 1))
            except (ValueError, TypeError):
                raise ValueError("Malformed price/quantity in CSV")
            products.append(Product(
                name=row["name"],
                category=row.get("category", "General"),
                price=price,
                quantity=qty
            ))
    return products

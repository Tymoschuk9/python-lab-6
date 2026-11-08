from __future__ import annotations
import csv
import json
from pathlib import Path
from typing import Any

try:
    from .value_objects import Money
    from .models import Product, Cart
    from .services import Catalog, DataImportError, AsyncExternalProvider
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
        from shop.models import Product, Cart
        from shop.services import Catalog, DataImportError, AsyncExternalProvider
    except (ImportError, ValueError):
        from value_objects import Money
        from models import Product, Cart
        from services import Catalog, DataImportError, AsyncExternalProvider

def export_order(order: dict, path: Path | str) -> None:
    p = Path(path)
    p.write_text(json.dumps(order, ensure_ascii=False, indent=2), encoding="utf-8")

def export_products_to_json(products: list[Product] | Catalog, file_path: Path | str) -> None:
    path = Path(file_path)
    prods = products.products if isinstance(products, Catalog) else list(products)
    data = [
        {
            "name": p.name,
            "category": p.category,
            "price": float(p.price.amount),
            "quantity": p.quantity,
            "total_value": p.total_value,
        }
        for p in prods
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def import_products_from_csv(file_path: Path | str) -> list[Product]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    products: list[Product] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataImportError("Empty or invalid CSV")
        for row_idx, row in enumerate(reader, start=1):
            name = row.get("name") or row.get("Name")
            if not name:
                raise DataImportError(f"Malformed record at row {row_idx}: missing name")
            category = row.get("category") or row.get("Category", "General")
            price_str = row.get("price") or row.get("Price")
            quantity_str = row.get("quantity") or row.get("Quantity", "0")
            if price_str is None:
                raise DataImportError(f"Malformed record at row {row_idx}: missing price")
            try:
                price = float(price_str)
                quantity = int(quantity_str)
            except (ValueError, TypeError) as e:
                raise DataImportError(f"Malformed record at row {row_idx}: invalid number") from e
            if price < 0 or quantity < 0:
                raise ValueError("Price and quantity must not be negative")
            products.append(Product(name=name, category=category, price=price, quantity=quantity))
    return products

async def process_catalog_pipeline(
    csv_path: Path | str, json_path: Path | str, external_provider: AsyncExternalProvider | None = None
) -> list[Product]:
    products = import_products_from_csv(csv_path)
    if external_provider:
        for p in products:
            try:
                new_price = await external_provider.fetch_product_price(p.name)
                p.price = Money(new_price)
            except Exception:
                pass
    export_products_to_json(products, json_path)
    return products

from __future__ import annotations
import os
import sys

try:
    from .value_objects import Money
    from .models import Product, Cart, CartItem
    from .services import (
        Catalog, PercentageDiscount, CheckoutService, PaymentError,
        get_payment_mode, get_min_stock
    )
    from .exporters import export_order, export_products_to_json, import_products_from_csv
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
        from shop.models import Product, Cart, CartItem
        from shop.services import (
            Catalog, PercentageDiscount, CheckoutService, PaymentError,
            get_payment_mode, get_min_stock
        )
        from shop.exporters import export_order, export_products_to_json, import_products_from_csv
    except (ImportError, ValueError):
        from value_objects import Money
        from models import Product, Cart, CartItem
        from services import (
            Catalog, PercentageDiscount, CheckoutService, PaymentError,
            get_payment_mode, get_min_stock
        )
        from exporters import export_order, export_products_to_json, import_products_from_csv

def main() -> None:
    print("=" * 60)
    print("🛒 ЛАБОРАТОРНА РОБОТА №6: АВТОМАТИЗОВАНЕ ТЕСТУВАННЯ")
    print("📦 Варіант №3: Інтернет-магазин (E-commerce shop)")
    print("=" * 60)

    laptop = Product("Laptop", "Electronics", 35000.0, 5)
    mouse = Product("Mouse", "Electronics", 1200.0, 20)
    desk = Product("Desk", "Furniture", 5500.0, 3)

    catalog = Catalog([laptop, mouse, desk])
    print(f"Всього товарів у каталозі: {len(catalog)}")
    print(f"Вартість залишків: {catalog.calculate_inventory_value():,.2f} UAH")
    most_exp = catalog.find_most_expensive()
    print(f"Найдорожчий товар: {most_exp.name if most_exp else 'Немає'}")

    cart = Cart()
    cart.add(laptop, 1)
    cart.add(mouse, 2)
    print(f"Сума кошика: {cart.total.amount:.2f} {cart.total.currency}")

    discount = PercentageDiscount(10)
    discounted_total = discount.apply(cart.total)
    print(f"Сума зі знижкою 10%: {discounted_total.amount:.2f} {discounted_total.currency}")
    print("=" * 60)

if __name__ == "__main__":
    main()

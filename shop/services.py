from __future__ import annotations
import os
from typing import Any

try:
    from .value_objects import Money
    from .models import Cart, Product
    from .protocols import PaymentGateway, Notifier
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
        from shop.models import Cart, Product
        from shop.protocols import PaymentGateway, Notifier
    except (ImportError, ValueError):
        from value_objects import Money
        from models import Cart, Product
        from protocols import PaymentGateway, Notifier

class PaymentError(Exception):
    pass

class DataImportError(Exception):
    pass

class PercentageDiscount:
    def __init__(self, percent: float) -> None:
        if not (0 <= percent <= 100):
            raise ValueError("Invalid discount")
        self.percent = percent

    def apply(self, total: Money) -> Money:
        return Money(round(total.amount * (1 - self.percent / 100), 2), total.currency)

class CheckoutService:
    def __init__(self, payment_gateway: PaymentGateway, notifier: Notifier) -> None:
        self._gateway = payment_gateway
        self._notifier = notifier

    def checkout(self, email: str, cart: Cart) -> str:
        if len(cart) == 0:
            raise ValueError("Cart is empty")
        payment_id = self._gateway.pay(cart.total)
        self._notifier.send(email, f"Payment successful: {payment_id}")
        return payment_id

def get_payment_mode() -> str:
    return os.getenv("PAYMENT_MODE", "sandbox")

def get_min_stock() -> int:
    val = os.getenv("MIN_STOCK", "5")
    try:
        return int(val)
    except ValueError:
        return 5

class AsyncPaymentStatus:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_status(self, payment_id: str) -> str:
        data = await self._client.fetch_status(payment_id)
        return data["status"]

class AsyncExternalProvider:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def fetch_product_price(self, product_name: str) -> float:
        res = await self._client.fetch_price(product_name)
        if isinstance(res, dict):
            return float(res.get("price", 0.0))
        return float(res)

    async def get_price(self, product_name: str) -> float:
        return await self.fetch_product_price(product_name)

class Catalog:
    def __init__(self, products: list[Product] | None = None) -> None:
        self.products: list[Product] = list(products) if products else []

    def add(self, product: Product) -> None:
        self.products.append(product)

    def add_product(self, product: Product) -> None:
        self.add(product)

    def find_product(self, name: str) -> Product | None:
        for p in self.products:
            if p.name.lower() == name.lower():
                return p
        return None

    def filter_by_category(self, category: str) -> list[Product]:
        return [p for p in self.products if p.category.lower() == category.lower()]

    def calculate_inventory_value(self) -> float:
        return float(sum(p.total_value for p in self.products))

    def find_most_expensive(self) -> Product | None:
        if not self.products:
            return None
        return max(self.products, key=lambda p: float(p.price.amount))

    def __len__(self) -> int:
        return len(self.products)

    def __iter__(self):
        return iter(self.products)

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return self.find_product(item) is not None
        if isinstance(item, Product):
            return item in self.products
        return False

def calculate_inventory_value(products: list[Product] | Catalog) -> float:
    if isinstance(products, Catalog):
        return products.calculate_inventory_value()
    if not products:
        return 0.0
    return float(sum(p.total_value for p in products))

def find_product(products: list[Product] | Catalog, name: str | None = None) -> Product | None:
    if isinstance(products, Catalog):
        return products.find_product(name) if name else None
    if isinstance(products, list) and name is not None:
        for p in products:
            if p.name.lower() == name.lower():
                return p
    return None

def filter_by_category(products: list[Product] | Catalog, category: str) -> list[Product]:
    if isinstance(products, Catalog):
        return products.filter_by_category(category)
    if isinstance(products, list):
        return [p for p in products if p.category.lower() == category.lower()]
    return []

def find_most_expensive(products: list[Product] | Catalog) -> Product | None:
    if isinstance(products, Catalog):
        return products.find_most_expensive()
    if not products:
        return None
    return max(products, key=lambda p: float(p.price.amount))

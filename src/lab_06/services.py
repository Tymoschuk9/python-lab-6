from __future__ import annotations
import os
from typing import Optional, List, Any

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
    try:
        return int(os.getenv("MIN_STOCK", "5"))
    except (ValueError, TypeError):
        return 5

class Catalog:
    def __init__(self, products: Optional[List[Product]] = None) -> None:
        self.products: List[Product] = list(products) if products else []

    def add_product(self, product: Product) -> None:
        self.products.append(product)

    def add(self, product: Product, quantity: int = 1) -> None:
        self.add_product(product)

    def find_product(self, name: str) -> Optional[Product]:
        for p in self.products:
            if p.name.lower() == name.lower():
                return p
        return None

    def filter_by_category(self, category: str) -> List[Product]:
        return [p for p in self.products if p.category.lower() == category.lower()]

    def calculate_inventory_value(self) -> float:
        total = sum(p.price_val * p.quantity for p in self.products)
        return round(total, 2)

    def find_most_expensive(self) -> Optional[Product]:
        if not self.products:
            return None
        return max(self.products, key=lambda p: p.price_val)

    def __len__(self) -> int:
        return len(self.products)

ProductRepository = Catalog
ShopManager = Catalog

def calculate_inventory_value(products: List[Product]) -> float:
    return Catalog(products).calculate_inventory_value()

def find_product(products: List[Product], name: str) -> Optional[Product]:
    return Catalog(products).find_product(name)

def filter_by_category(products: List[Product], category: str) -> List[Product]:
    return Catalog(products).filter_by_category(category)

def find_most_expensive(products: List[Product]) -> Optional[Product]:
    return Catalog(products).find_most_expensive()

class AsyncPaymentStatus:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def get_status(self, payment_id: str) -> str:
        data = await self._client.fetch_status(payment_id)
        return data["status"]

class AsyncExternalProvider:
    def __init__(self, client: Any = None) -> None:
        self.client = client

    async def fetch_product_price(self, product_name: str) -> float:
        if self.client:
            res = await self.client.fetch_price(product_name)
            return float(res)
        return 100.0

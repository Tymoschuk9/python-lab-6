from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, List

try:
    from .value_objects import Money
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
    except (ImportError, ValueError):
        from value_objects import Money

class Product:
    def __init__(self, *args, **kwargs):
        product_id = kwargs.get("product_id")
        name = kwargs.get("name")
        category = kwargs.get("category", "General")
        price = kwargs.get("price")
        quantity = kwargs.get("quantity", 1)

        if len(args) == 4:
            name, category, price, quantity = args
        elif len(args) == 3:
            if isinstance(args[0], int) and isinstance(args[1], str):
                product_id, name, price = args
            else:
                name, category, price = args
        elif len(args) == 2:
            name, price = args
        elif len(args) == 1:
            name = args[0]

        val_price = price.amount if hasattr(price, "amount") else price
        if val_price is not None and float(val_price) < 0:
            raise ValueError("Price cannot be negative")
        if quantity is not None and int(quantity) < 0:
            raise ValueError("Quantity cannot be negative")

        self.name: str = str(name or "")
        self.category: str = str(category or "General")
        self.price: Any = price if price is not None else Money(0.0)
        self.quantity: int = int(quantity) if quantity is not None else 1
        self.product_id: int = int(product_id) if product_id is not None else 1
        self.id: int = self.product_id

    @property
    def price_val(self) -> float:
        return self.price.amount if hasattr(self.price, "amount") else float(self.price)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Product):
            return False
        return self.name == other.name and self.price_val == other.price_val

    def __repr__(self) -> str:
        return f"Product(id={self.product_id}, name='{self.name}', price={self.price}, quantity={self.quantity})"

@dataclass
class CartItem:
    product: Product
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")

    @property
    def total(self) -> Money:
        amt = self.product.price.amount if hasattr(self.product.price, "amount") else float(self.product.price)
        curr = self.product.price.currency if hasattr(self.product.price, "currency") else "UAH"
        return Money(round(amt * self.quantity, 2), curr)

@dataclass
class Cart:
    items: list[CartItem] = field(default_factory=list)

    def add(self, product: Product, quantity: int = 1) -> None:
        self.items.append(CartItem(product, quantity))

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, product_id: int) -> bool:
        return any(item.product.product_id == product_id for item in self.items)

    @property
    def total(self) -> Money:
        return Money(round(sum(item.total.amount for item in self.items), 2))

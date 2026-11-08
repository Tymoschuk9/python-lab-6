from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

try:
    from .value_objects import Money
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
    except (ImportError, ValueError):
        from value_objects import Money

@dataclass
class Product:
    product_id: int = 1
    name: str = ""
    category: str = "Electronics"
    price: Any = field(default_factory=lambda: Money(0.0))
    quantity: int = 1

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        p_id = 1
        name = ""
        category = "Electronics"
        price: Any = 0.0
        quantity = 1

        if len(args) == 4:
            name, category, price, quantity = args
        elif len(args) == 3:
            if isinstance(args[0], int) and isinstance(args[1], str):
                p_id, name, price = args
            else:
                name, category, price = args
        elif len(args) == 2:
            name, price = args
        elif len(args) == 1:
            name = args[0]

        if "product_id" in kwargs:
            p_id = kwargs["product_id"]
        elif "id" in kwargs:
            p_id = kwargs["id"]
        if "name" in kwargs:
            name = kwargs["name"]
        if "category" in kwargs:
            category = kwargs["category"]
        if "price" in kwargs:
            price = kwargs["price"]
        if "quantity" in kwargs:
            quantity = kwargs["quantity"]

        val_price = price.amount if isinstance(price, Money) else float(price)
        if val_price < 0:
            raise ValueError("Price cannot be negative")
        if int(quantity) < 0:
            raise ValueError("Quantity cannot be negative")

        object.__setattr__(self, "product_id", int(p_id))
        object.__setattr__(self, "name", str(name))
        object.__setattr__(self, "category", str(category))
        money_obj = price if isinstance(price, Money) else Money(round(val_price, 2))
        object.__setattr__(self, "price", money_obj)
        object.__setattr__(self, "quantity", int(quantity))

    @property
    def id(self) -> int:
        return self.product_id

    @property
    def price_val(self) -> float:
        return float(self.price.amount)

    @property
    def total_value(self) -> float:
        return round(float(self.price.amount) * self.quantity, 2)

@dataclass
class CartItem:
    product: Product
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("Quantity must be positive")

    @property
    def total(self) -> Money:
        return Money(round(self.product.price.amount * self.quantity, 2), self.product.price.currency)

@dataclass
class Cart:
    items: list[CartItem] = field(default_factory=list)

    def add(self, product: Product, quantity: int = 1) -> None:
        self.items.append(CartItem(product, quantity))

    def __len__(self) -> int:
        return len(self.items)

    def __contains__(self, product_id: int) -> bool:
        return any(item.product.product_id == product_id or getattr(item.product, "id", None) == product_id for item in self.items)

    @property
    def total(self) -> Money:
        return Money(round(sum(item.total.amount for item in self.items), 2))

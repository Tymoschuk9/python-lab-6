from __future__ import annotations
from dataclasses import dataclass, field

try:
    from .value_objects import Money
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
    except (ImportError, ValueError):
        from value_objects import Money

@dataclass(frozen=True)
class Product:
    product_id: int
    name: str
    price: Money

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
        return any(item.product.product_id == product_id for item in self.items)

    @property
    def total(self) -> Money:
        return Money(round(sum(item.total.amount for item in self.items), 2))

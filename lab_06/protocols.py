from __future__ import annotations
from typing import Protocol, Any
from .value_objects import Money

class PaymentGateway(Protocol):
    def pay(self, amount: Money) -> str:
        ...

class Notifier(Protocol):
    def send(self, recipient: str, message: str) -> None:
        ...

class ProductRepository(Protocol):
    def find_product(self, name: str) -> Any:
        ...
    def add(self, product: Any) -> None:
        ...
    def get_all(self) -> list[Any]:
        ...

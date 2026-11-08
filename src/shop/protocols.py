from __future__ import annotations
from typing import Protocol
try:
    from .value_objects import Money
except (ImportError, ValueError):
    try:
        from shop.value_objects import Money
    except (ImportError, ValueError):
        from value_objects import Money

class PaymentGateway(Protocol):
    def pay(self, amount: Money) -> str:
        ...

class Notifier(Protocol):
    def send(self, recipient: str, message: str) -> None:
        ...

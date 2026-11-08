from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class Money:
    amount: float
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError("Amount cannot be negative")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Currency mismatch")
        if self.amount < other.amount:
            raise ValueError("Resulting amount cannot be negative")
        return Money(round(self.amount - other.amount, 2), self.currency)

    def __float__(self) -> float:
        return float(self.amount)

    def __int__(self) -> int:
        return int(self.amount)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (int, float)):
            return self.amount == float(other)
        if isinstance(other, Money):
            return self.amount == other.amount and self.currency == other.currency
        return False

    def __lt__(self, other: object) -> bool:
        other_val = other.amount if isinstance(other, Money) else float(other)
        return self.amount < other_val

    def __le__(self, other: object) -> bool:
        other_val = other.amount if isinstance(other, Money) else float(other)
        return self.amount <= other_val

    def __gt__(self, other: object) -> bool:
        other_val = other.amount if isinstance(other, Money) else float(other)
        return self.amount > other_val

    def __ge__(self, other: object) -> bool:
        other_val = other.amount if isinstance(other, Money) else float(other)
        return self.amount >= other_val

    def __mul__(self, other: int | float) -> "Money":
        if isinstance(other, (int, float)):
            return Money(round(self.amount * float(other), 2), self.currency)
        return NotImplemented

    def __rmul__(self, other: int | float) -> "Money":
        return self.__mul__(other)

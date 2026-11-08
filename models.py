from dataclasses import dataclass

@dataclass
class Product:
    name: str
    category: str
    price: float
    quantity: int

    @property
    def total_value(self) -> float:
        """Повертає загальну вартість залишку цього товару."""
        return float(self.price * self.quantity)

import pytest
from shop.models import Cart, Product
from shop.value_objects import Money

@pytest.fixture
def laptop() -> Product:
    return Product(product_id=1, name="Laptop", price=Money(35_000))

@pytest.fixture
def mouse() -> Product:
    return Product(product_id=2, name="Mouse", price=Money(1_200))

@pytest.fixture
def cart(laptop, mouse) -> Cart:
    cart = Cart()
    cart.add(laptop, 1)
    cart.add(mouse, 2)
    return cart

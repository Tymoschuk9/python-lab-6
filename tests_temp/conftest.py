import pytest
from shop.models import Cart, Product
from shop.value_objects import Money
from shop.services import Catalog

@pytest.fixture
def laptop() -> Product:
    return Product(product_id=1, name="Laptop", category="Electronics", price=Money(35_000), quantity=10)

@pytest.fixture
def mouse() -> Product:
    return Product(product_id=2, name="Mouse", category="Electronics", price=Money(1_200), quantity=25)

@pytest.fixture
def desk() -> Product:
    return Product(product_id=3, name="Desk", category="Furniture", price=Money(5_500), quantity=5)

@pytest.fixture
def cart(laptop, mouse) -> Cart:
    cart = Cart()
    cart.add(laptop, 1)
    cart.add(mouse, 2)
    return cart

@pytest.fixture
def catalog(laptop, mouse, desk) -> Catalog:
    return Catalog([laptop, mouse, desk])

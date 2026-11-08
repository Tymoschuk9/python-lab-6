from unittest.mock import Mock, AsyncMock
import pytest
from shop.models import Product
from shop.services import Catalog, get_min_stock, AsyncExternalProvider
from shop.protocols import PaymentGateway, Notifier

def test_product_creation_and_attributes(laptop):
    assert laptop.name == "Laptop"
    assert laptop.category == "Electronics"
    assert laptop.price_val == 35000
    assert laptop.quantity == 10

def test_boundary_and_invalid_product():
    p = Product(name="FreeItem", category="Misc", price=0.0, quantity=0)
    assert p.price_val == 0.0
    assert p.quantity == 0

    with pytest.raises(ValueError, match="negative"):
        Product(name="BadPrice", price=-10.0)

    with pytest.raises(ValueError, match="negative"):
        Product(name="BadQty", price=100.0, quantity=-1)

def test_catalog_search_and_filter(catalog):
    found = catalog.find_product("Laptop")
    assert found is not None
    assert found.name == "Laptop"

    not_found = catalog.find_product("NonExistent")
    assert not_found is None

    electronics = catalog.filter_by_category("Electronics")
    assert len(electronics) == 2

    furniture = catalog.filter_by_category("Furniture")
    assert len(furniture) == 1

def test_catalog_inventory_and_expensive(catalog):
    assert catalog.calculate_inventory_value() == pytest.approx(432_500)
    most_exp = catalog.find_most_expensive()
    assert most_exp is not None
    assert most_exp.name == "Laptop"

def test_empty_catalog():
    empty = Catalog()
    assert len(empty) == 0
    assert empty.calculate_inventory_value() == 0.0
    assert empty.find_most_expensive() is None
    assert empty.find_product("Any") is None

def test_min_stock_configuration(monkeypatch):
    monkeypatch.setenv("MIN_STOCK", "15")
    assert get_min_stock() == 15
    monkeypatch.delenv("MIN_STOCK", raising=False)
    assert get_min_stock() == 5

def test_product_repository_mock():
    repo = Mock()
    repo.find_product.return_value = Product(name="MockedItem", price=500.0)
    prod = repo.find_product("MockedItem")
    assert prod.name == "MockedItem"
    repo.find_product.assert_called_once_with("MockedItem")

@pytest.mark.asyncio
async def test_async_external_provider():
    client = AsyncMock()
    client.fetch_price.return_value = 199.99
    provider = AsyncExternalProvider(client)
    price = await provider.fetch_product_price("ExternalItem")
    assert price == pytest.approx(199.99)
    client.fetch_price.assert_awaited_once_with("ExternalItem")

import pytest
from unittest.mock import Mock, AsyncMock
from pathlib import Path
from shop.models import Product
from shop.services import (
    Catalog, get_min_stock, AsyncExternalProvider,
    calculate_inventory_value, find_product, filter_by_category, find_most_expensive,
    DataImportError
)
from shop.exporters import import_products_from_csv, export_products_to_json, process_catalog_pipeline
from shop.protocols import ProductRepository

def test_product_creation_and_attributes(laptop):
    assert laptop.name == "Laptop"
    assert laptop.category == "Electronics"
    assert laptop.price_val == 35000.0
    assert laptop.quantity == 10
    assert laptop.id == 1
    assert laptop.total_value == 350000.0

def test_boundary_and_invalid_product():
    p = Product(name="FreeItem", category="Misc", price=0.0, quantity=0)
    assert p.price_val == 0.0
    assert p.quantity == 0

    with pytest.raises(ValueError, match="negative"):
        Product(name="BadPrice", price=-10.0)

    with pytest.raises(ValueError, match="negative"):
        Product(name="BadQty", price=100.0, quantity=-1)

def test_catalog_add():
    catalog = Catalog()
    assert len(catalog) == 0
    p = Product("Item", "Misc", 50.0, 2)
    catalog.add(p)
    assert len(catalog) == 1
    assert p in catalog

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
    assert catalog.calculate_inventory_value() == pytest.approx(407_500.0)
    most_exp = catalog.find_most_expensive()
    assert most_exp is not None
    assert most_exp.name == "Laptop"

def test_empty_catalog():
    empty = Catalog()
    assert len(empty) == 0
    assert empty.calculate_inventory_value() == 0.0
    assert empty.find_most_expensive() is None
    assert empty.find_product("Any") is None
    assert empty.filter_by_category("Any") == []

def test_module_level_services(laptop, mouse):
    products = [laptop, mouse]
    assert calculate_inventory_value(products) == pytest.approx(380_000.0)
    assert calculate_inventory_value([]) == 0.0

    found = find_product(products, "Laptop")
    assert found is not None and found.name == "Laptop"
    assert find_product(products, "NoSuch") is None
    assert find_product("invalid") is None

    filtered = filter_by_category(products, "Electronics")
    assert len(filtered) == 2
    assert filter_by_category([], "Electronics") == []

    most_exp = find_most_expensive(products)
    assert most_exp is not None and most_exp.name == "Laptop"
    assert find_most_expensive([]) is None

def test_min_stock_configuration(monkeypatch):
    monkeypatch.setenv("MIN_STOCK", "15")
    assert get_min_stock() == 15
    monkeypatch.setenv("MIN_STOCK", "invalid_num")
    assert get_min_stock() == 5
    monkeypatch.delenv("MIN_STOCK", raising=False)
    assert get_min_stock() == 5

def test_product_repository_mock():
    repo = Mock(spec=ProductRepository)
    repo.find_product.return_value = Product(name="MockedItem", price=500.0)
    prod = repo.find_product("MockedItem")
    assert prod.name == "MockedItem"
    repo.find_product.assert_called_once_with("MockedItem")

def test_product_repository_fake():
    class FakeRepository:
        def __init__(self):
            self.items = {}
        def add(self, p):
            self.items[p.name] = p
        def find_product(self, name):
            return self.items.get(name)
        def get_all(self):
            return list(self.items.values())

    fake = FakeRepository()
    fake.add(Product("Keyboard", "Electronics", 2000.0, 5))
    found = fake.find_product("Keyboard")
    assert found is not None and found.price_val == 2000.0
    assert len(fake.get_all()) == 1

def test_csv_import_and_malformed(tmp_path):
    csv_file = tmp_path / "products.csv"
    csv_file.write_text("name,category,price,quantity\nPhone,Electronics,15000,3\nBook,Books,300,10\n", encoding="utf-8")

    imported = import_products_from_csv(csv_file)
    assert len(imported) == 2
    assert imported[0].name == "Phone"
    assert imported[1].category == "Books"

    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("name,category,price,quantity\n,Electronics,100,1\n", encoding="utf-8")
    with pytest.raises(DataImportError, match="missing name"):
        import_products_from_csv(bad_csv)

    bad_num_csv = tmp_path / "bad_num.csv"
    bad_num_csv.write_text("name,category,price,quantity\nItem,Electronics,not_a_num,1\n", encoding="utf-8")
    with pytest.raises(DataImportError, match="invalid number"):
        import_products_from_csv(bad_num_csv)

    with pytest.raises(FileNotFoundError):
        import_products_from_csv(tmp_path / "non_existent.csv")

def test_json_export(tmp_path, catalog):
    json_path = tmp_path / "catalog.json"
    export_products_to_json(catalog, json_path)
    assert json_path.exists()
    import json
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["name"] == "Laptop"

@pytest.mark.asyncio
async def test_async_external_provider():
    client = AsyncMock()
    client.fetch_price.return_value = 199.99
    provider = AsyncExternalProvider(client)
    price = await provider.fetch_product_price("ExternalItem")
    assert price == pytest.approx(199.99)
    client.fetch_price.assert_awaited_once_with("ExternalItem")

    client.fetch_price.return_value = {"price": 250.0}
    price2 = await provider.get_price("Item2")
    assert price2 == pytest.approx(250.0)

def test_main_cli(capsys):
    from shop.main import main
    main()
    captured = capsys.readouterr()
    assert "ЛАБОРАТОРНА РОБОТА" in captured.out

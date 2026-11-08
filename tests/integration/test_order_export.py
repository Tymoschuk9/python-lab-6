import json
import pytest
from unittest.mock import Mock
from shop.protocols import Notifier, PaymentGateway
from shop.services import CheckoutService, Catalog
from shop.models import Product
from shop.exporters import export_order, export_products_to_json, import_products_from_csv

def test_export_order(tmp_path):
    output = tmp_path / "order.json"
    order = {"id": 1, "total": 100.0, "status": "paid"}
    export_order(order, output)
    assert output.exists()
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data == order

def test_order_export_integration(tmp_path, cart):
    gateway = Mock(spec=PaymentGateway)
    gateway.pay.return_value = "PAY-100"
    notifier = Mock(spec=Notifier)
    service = CheckoutService(gateway, notifier)
    payment_id = service.checkout("anna@example.com", cart)
    output = tmp_path / "order.json"
    export_order({"payment_id": payment_id, "total": cart.total.amount}, output)
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["payment_id"] == "PAY-100"
    assert data["total"] == pytest.approx(37_400)

def test_csv_import_and_json_export_pipeline(tmp_path):
    csv_file = tmp_path / "incoming_products.csv"
    csv_file.write_text(
        "name,category,price,quantity\nKeyboard,Electronics,1500.0,10\nLamp,Home,800.0,5\n",
        encoding="utf-8"
    )
    products = import_products_from_csv(csv_file)
    assert len(products) == 2
    assert products[0].name == "Keyboard"
    
    catalog = Catalog(products)
    assert catalog.calculate_inventory_value() == 19000.0
    
    json_file = tmp_path / "exported_catalog.json"
    export_products_to_json(products, json_file)
    assert json_file.exists()
    exported_data = json.loads(json_file.read_text(encoding="utf-8"))
    assert len(exported_data) == 2
    assert exported_data[0]["name"] == "Keyboard"

def test_malformed_csv_raises_error(tmp_path):
    bad_csv = tmp_path / "corrupted.csv"
    bad_csv.write_text("name,category,price\n,Electronics,\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Malformed"):
        import_products_from_csv(bad_csv)

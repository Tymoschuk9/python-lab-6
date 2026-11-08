import json
import pytest
from unittest.mock import Mock
from shop.protocols import Notifier, PaymentGateway
from shop.services import CheckoutService
from shop.exporters import export_order

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

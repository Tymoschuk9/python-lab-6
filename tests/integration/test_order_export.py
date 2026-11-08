import json
import pytest
from unittest.mock import Mock, AsyncMock
from shop.protocols import Notifier, PaymentGateway
from shop.services import CheckoutService, AsyncExternalProvider
from shop.exporters import export_order, process_catalog_pipeline

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

@pytest.mark.asyncio
async def test_full_pipeline_import_process_export(tmp_path):
    csv_file = tmp_path / "source.csv"
    csv_file.write_text("name,category,price,quantity\nMonitor,Electronics,8000,4\n", encoding="utf-8")
    json_file = tmp_path / "dest.json"

    client = AsyncMock()
    client.fetch_price.return_value = 7500.0
    provider = AsyncExternalProvider(client)

    result = await process_catalog_pipeline(csv_file, json_file, provider)
    assert len(result) == 1
    assert result[0].name == "Monitor"
    assert result[0].price_val == 7500.0
    assert json_file.exists()

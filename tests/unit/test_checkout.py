from unittest.mock import Mock, AsyncMock
import pytest
from shop.protocols import Notifier, PaymentGateway
from shop.services import CheckoutService, PaymentError, get_payment_mode, AsyncPaymentStatus
from shop.models import Cart

def test_checkout_success(cart):
    gateway = Mock(spec=PaymentGateway)
    gateway.pay.return_value = "PAY-001"
    notifier = Mock(spec=Notifier)
    service = CheckoutService(payment_gateway=gateway, notifier=notifier)
    result = service.checkout("anna@example.com", cart)
    assert result == "PAY-001"
    gateway.pay.assert_called_once_with(cart.total)
    notifier.send.assert_called_once_with("anna@example.com", "Payment successful: PAY-001")

def test_checkout_payment_failure(cart):
    gateway = Mock(spec=PaymentGateway)
    gateway.pay.side_effect = PaymentError("Unavailable")
    notifier = Mock(spec=Notifier)
    service = CheckoutService(gateway, notifier)
    with pytest.raises(PaymentError, match="Unavailable"):
        service.checkout("anna@example.com", cart)
    notifier.send.assert_not_called()

def test_empty_cart_checkout():
    gateway = Mock(spec=PaymentGateway)
    notifier = Mock(spec=Notifier)
    service = CheckoutService(gateway, notifier)
    with pytest.raises(ValueError, match="empty"):
        service.checkout("anna@example.com", Cart())
    gateway.pay.assert_not_called()
    notifier.send.assert_not_called()

def test_payment_mode_from_env(monkeypatch):
    monkeypatch.setenv("PAYMENT_MODE", "test")
    assert get_payment_mode() == "test"

def test_default_payment_mode(monkeypatch):
    monkeypatch.delenv("PAYMENT_MODE", raising=False)
    assert get_payment_mode() == "sandbox"

@pytest.mark.asyncio
async def test_payment_status():
    client = AsyncMock()
    client.fetch_status.return_value = {"status": "paid"}
    service = AsyncPaymentStatus(client)
    result = await service.get_status("PAY-001")
    assert result == "paid"
    client.fetch_status.assert_awaited_once_with("PAY-001")

@pytest.mark.asyncio
async def test_payment_status_error():
    client = AsyncMock()
    client.fetch_status.side_effect = ConnectionError("Network error")
    service = AsyncPaymentStatus(client)
    with pytest.raises(ConnectionError):
        await service.get_status("PAY-001")

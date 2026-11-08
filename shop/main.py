import sys
import os
import json
import csv
import asyncio
from decimal import Decimal
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Protocol
from unittest.mock import Mock, AsyncMock, MagicMock

import pytest

# ==============================================================================
# 1. ДОМЕННІ МОДЕЛІ ТА ВИНЯТКИ (Варіант 3: Інтернет-магазин)
# ==============================================================================

class InvalidProductDataError(ValueError):
    """Виняток для некоректних даних товару або грошових величин."""
    pass


class MalformedCSVError(ValueError):
    """Виняток для некоректного або пошкодженого запису у CSV-файлі."""
    pass


@dataclass
class Money:
    """Клас для роботи з грошовими сумами та валютою."""
    amount: Decimal
    currency: str = "UAH"

    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))
        if self.amount < Decimal("0.0"):
            raise InvalidProductDataError("Сума не може бути від'ємною.")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("Неможливо додавати суми з різними валютами.")
        return Money(self.amount + other.amount, self.currency)

    def __mul__(self, factor: int | float | Decimal) -> "Money":
        factor_dec = Decimal(str(factor))
        return Money(self.amount * factor_dec, self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.amount == other.amount and self.currency == other.currency


@dataclass
class Product:
    """Модель товару в інтернет-магазині."""
    product_id: str
    name: str
    price: Money
    category: str
    quantity: int

    def __post_init__(self):
        if not self.product_id or not self.name or not self.category:
            raise InvalidProductDataError("Ідентифікатор, назва та категорія не можуть бути порожніми.")
        if self.price.amount <= Decimal("0.0"):
            raise InvalidProductDataError("Ціна товару повинна бути більшою за нуль.")
        if self.quantity < 0:
            raise InvalidProductDataError("Кількість товару на складі не може бути від'ємною.")


@dataclass
class CartItem:
    """Елемент кошика покупок."""
    product: Product
    quantity: int

    def __post_init__(self):
        if self.quantity <= 0:
            raise InvalidProductDataError("Кількість товару у кошику має бути більшою за 0.")

    @property
    def item_total(self) -> Money:
        return self.product.price * self.quantity


class Cart:
    """Кошик покупок користувача."""
    def __init__(self):
        self.items: List[CartItem] = []

    def add(self, product: Product, quantity: int = 1) -> None:
        for item in self.items:
            if item.product.product_id == product.product_id:
                item.quantity += quantity
                return
        self.items.append(CartItem(product=product, quantity=quantity))

    def total(self) -> Money:
        if not self.items:
            return Money(Decimal("0.00"))
        currency = self.items[0].product.price.currency
        total_amount = sum((item.item_total.amount for item in self.items), Decimal("0.00"))
        return Money(total_amount, currency)

    def clear(self) -> None:
        self.items.clear()


class PercentageDiscount:
    """Стратегія розрахунку відсоткової знижки."""
    def __init__(self, percent: Decimal):
        percent_dec = Decimal(str(percent))
        if percent_dec < Decimal("0.0") or percent_dec > Decimal("100.0"):
            raise ValueError("Відсоток знижки повинен бути у межах від 0 до 100.")
        self.percent = percent_dec

    def apply(self, amount: Money) -> Money:
        discount_factor = (Decimal("100.0") - self.percent) / Decimal("100.0")
        new_amount = (amount.amount * discount_factor).quantize(Decimal("0.01"))
        return Money(new_amount, amount.currency)


# ==============================================================================
# 2. РЕПОЗИТОРІЙ ТА КАТАЛОГ
# ==============================================================================

class ProductRepository:
    """Сховище даних товарів."""
    def __init__(self):
        self._products: Dict[str, Product] = {}

    def add(self, product: Product) -> None:
        self._products[product.product_id] = product

    def get_by_id(self, product_id: str) -> Optional[Product]:
        return self._products.get(product_id)

    def get_all(self) -> List[Product]:
        return list(self._products.values())


class Catalog:
    """Каталог товарів інтернет-магазину."""
    def __init__(self, repository: Optional[ProductRepository] = None):
        self.repository = repository if repository is not None else ProductRepository()

    def add_product(self, product: Product) -> None:
        self.repository.add(product)

    def search_by_name(self, query: str) -> List[Product]:
        q = query.lower().strip()
        if not q:
            return []
        return [p for p in self.repository.get_all() if q in p.name.lower()]

    def filter_by_category(self, category: str) -> List[Product]:
        cat = category.lower().strip()
        return [p for p in self.repository.get_all() if p.category.lower() == cat]

    def calculate_total_stock_value(self) -> Money:
        products = self.repository.get_all()
        if not products:
            return Money(Decimal("0.00"))
        total = sum((p.price.amount * p.quantity for p in products), Decimal("0.00"))
        return Money(total, products[0].price.currency)

    def get_most_expensive(self) -> Optional[Product]:
        products = self.repository.get_all()
        if not products:
            return None
        return max(products, key=lambda p: p.price.amount)

    def get_low_stock_products(self, min_stock: int) -> List[Product]:
        return [p for p in self.repository.get_all() if p.quantity < min_stock]


# ==============================================================================
# 3. СЕРВІСИ ТА ІМПОРТ/ЕКСПОРТ
# ==============================================================================

class PaymentGateway(Protocol):
    """Протокол платіжного шлюзу."""
    def process_payment(self, amount: Money, card_info: str) -> bool:
        ...


class Notifier(Protocol):
    """Протокол сервісу сповіщень."""
    def send_notification(self, message: str) -> bool:
        ...


class CheckoutService:
    """Сервіс оформлення та оплати замовлення."""
    def __init__(self, payment_gateway: PaymentGateway, notifier: Notifier):
        self.payment_gateway = payment_gateway
        self.notifier = notifier

    def checkout(self, cart: Cart, card_info: str) -> bool:
        total = cart.total()
        if total.amount <= Decimal("0.00"):
            raise ValueError("Кошик порожній або сума замовлення дорівнює нулю.")

        is_paid = self.payment_gateway.process_payment(total, card_info)
        if is_paid:
            self.notifier.send_notification(
                f"Успішна оплата замовлення на суму {total.amount} {total.currency}"
            )
            cart.clear()
            return True
        else:
            self.notifier.send_notification("Помилка під час проведення оплати.")
            return False


def import_products_from_csv(file_path: str, repository: ProductRepository) -> int:
    """Імпортує товари з CSV файлу до репозиторію."""
    count = 0
    with open(file_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                product_id = row["product_id"].strip()
                name = row["name"].strip()
                price_val = Decimal(row["price"].strip())
                category = row["category"].strip()
                quantity_val = int(row["quantity"].strip())

                product = Product(
                    product_id=product_id,
                    name=name,
                    price=Money(price_val),
                    category=category,
                    quantity=quantity_val
                )
                repository.add(product)
                count += 1
            except Exception as e:
                raise MalformedCSVError(f"Помилка некоректного запису у CSV: {row}") from e
    return count


def export_products_to_json(repository: ProductRepository, file_path: str) -> None:
    """Експортує список товарів у файл JSON."""
    data = []
    for p in repository.get_all():
        data.append({
            "product_id": p.product_id,
            "name": p.name,
            "price": str(p.price.amount),
            "currency": p.price.currency,
            "category": p.category,
            "quantity": p.quantity
        })
    with open(file_path, mode="w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def export_order(cart: Cart, file_path: str) -> None:
    """Експортує замовлення кошика у JSON файл."""
    order_data = {
        "items": [
            {
                "product_id": item.product.product_id,
                "name": item.product.name,
                "quantity": item.quantity,
                "price": str(item.product.price.amount)
            }
            for item in cart.items
        ],
        "total": str(cart.total().amount),
        "currency": cart.total().currency
    }
    with open(file_path, mode="w", encoding="utf-8") as f:
        json.dump(order_data, f, indent=4, ensure_ascii=False)


def get_payment_mode(config: dict) -> str:
    """Отримує режим оплати з конфігураційного словника."""
    return config.get("payment_mode", "standard")


# ==============================================================================
# 4. АСИНХРОННІ СЕРВІСИ
# ==============================================================================

class AsyncPaymentStatus:
    """Перевірка статусу транзакції через зовнішній провайдер."""
    def __init__(self, external_provider: Any):
        self.provider = external_provider

    async def verify_status(self, transaction_id: str) -> str:
        res = await self.provider.check_transaction(transaction_id)
        return res.get("status", "unknown")


class AsyncExternalCatalogProvider:
    """Асинхронне джерело для імпорту товарів від зовнішнього постачальника."""
    async def fetch_external_products(self) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.01)
        return [
            {
                "product_id": "EXT-01",
                "name": "External Tablet",
                "price": "12000.00",
                "category": "Electronics",
                "quantity": 8
            }
        ]


# ==============================================================================
# 5. PYTEST ТЕСТИ ТА ФІКСТУРИ
# ==============================================================================

@pytest.fixture
def laptop() -> Product:
    return Product("P101", "Laptop Lenovo", Money(Decimal("25000.00")), "Electronics", 10)

@pytest.fixture
def mouse() -> Product:
    return Product("P102", "Wireless Mouse", Money(Decimal("800.00")), "Electronics", 25)

@pytest.fixture
def book() -> Product:
    return Product("P201", "Python Programming", Money(Decimal("600.00")), "Books", 15)

@pytest.fixture
def cart() -> Cart:
    return Cart()

@pytest.fixture
def catalog(laptop, mouse, book) -> Catalog:
    cat = Catalog()
    cat.add_product(laptop)
    cat.add_product(mouse)
    cat.add_product(book)
    return cat


def test_money_creation_and_boundary():
    m1 = Money(Decimal("100.50"))
    assert m1.amount == Decimal("100.50")
    assert m1.currency == "UAH"

    m2 = Money(0)
    assert m2.amount == Decimal("0")

    with pytest.raises(InvalidProductDataError, match="Сума не може бути від'ємною"):
        Money(Decimal("-10.00"))

def test_money_operations():
    m1 = Money(Decimal("100.00"))
    m2 = Money(Decimal("50.50"))
    assert (m1 + m2) == Money(Decimal("150.50"))
    assert (m1 * 3) == Money(Decimal("300.00"))

    m_usd = Money(Decimal("10.00"), currency="USD")
    with pytest.raises(ValueError, match="різними валютами"):
        _ = m1 + m_usd

def test_product_creation_and_validation(laptop):
    assert laptop.product_id == "P101"
    assert laptop.name == "Laptop Lenovo"
    assert laptop.price == Money(Decimal("25000.00"))
    assert laptop.quantity == 10

    # Boundary & Invalid price
    with pytest.raises(InvalidProductDataError, match="більшою за нуль"):
        Product("P-BAD", "Free Item", Money(Decimal("0.00")), "Electronics", 5)

    with pytest.raises(InvalidProductDataError, match="більшою за нуль"):
        Product("P-BAD2", "Negative Price", Money(Decimal("-50.00")), "Electronics", 5)

    # Boundary & Invalid quantity
    with pytest.raises(InvalidProductDataError, match="від'ємною"):
        Product("P-BAD3", "Bad Qty", Money(Decimal("100.00")), "Electronics", -1)

    # Empty string validation
    with pytest.raises(InvalidProductDataError, match="не можуть бути порожніми"):
        Product("", "Name", Money(Decimal("100.00")), "Electronics", 1)

def test_cart_operations(cart, laptop, mouse):
    assert cart.total() == Money(Decimal("0.00"))

    cart.add(laptop, 1)
    assert cart.total() == Money(Decimal("25000.00"))

    cart.add(mouse, 2)
    assert cart.total() == Money(Decimal("26600.00"))

    # Test adding existing item increase quantity
    cart.add(mouse, 1)
    assert cart.total() == Money(Decimal("27400.00"))

    cart.clear()
    assert cart.total() == Money(Decimal("0.00"))
    assert len(cart.items) == 0

def test_cart_invalid_quantity(cart, laptop):
    with pytest.raises(InvalidProductDataError, match="більшою за 0"):
        cart.add(laptop, 0)

    with pytest.raises(InvalidProductDataError, match="більшою за 0"):
        cart.add(laptop, -2)

def test_percentage_discount():
    discount_10 = PercentageDiscount(Decimal("10"))
    discount_0 = PercentageDiscount(Decimal("0"))
    discount_100 = PercentageDiscount(Decimal("100"))

    original = Money(Decimal("1000.00"))
    assert discount_10.apply(original) == Money(Decimal("900.00"))
    assert discount_0.apply(original) == Money(Decimal("1000.00"))
    assert discount_100.apply(original) == Money(Decimal("0.00"))

    with pytest.raises(ValueError, match="від 0 до 100"):
        PercentageDiscount(Decimal("-5"))

    with pytest.raises(ValueError, match="від 0 до 100"):
        PercentageDiscount(Decimal("105"))

def test_catalog_search_and_filter(catalog):
    # Search by name
    results = catalog.search_by_name("Laptop")
    assert len(results) == 1
    assert results[0].product_id == "P101"

    # Search empty query
    assert len(catalog.search_by_name("")) == 0

    # Filter by category
    electronics = catalog.filter_by_category("Electronics")
    assert len(electronics) == 2
    books = catalog.filter_by_category("Books")
    assert len(books) == 1

def test_catalog_stock_calculations(catalog):
    # Total stock value: (25000 * 10) + (800 * 25) + (600 * 15) = 250000 + 20000 + 9000 = 279000
    total_val = catalog.calculate_total_stock_value()
    assert total_val == Money(Decimal("279000.00"))

    most_exp = catalog.get_most_expensive()
    assert most_exp is not None
    assert most_exp.product_id == "P101"

def test_empty_catalog():
    empty_cat = Catalog()
    assert empty_cat.calculate_total_stock_value() == Money(Decimal("0.00"))
    assert empty_cat.get_most_expensive() is None
    assert len(empty_cat.search_by_name("any")) == 0
    assert len(empty_cat.filter_by_category("Electronics")) == 0

def test_csv_import_valid_and_malformed(tmp_path):
    csv_file = tmp_path / "products.csv"
    csv_file.write_text(
        "product_id,name,price,category,quantity\n"
        "CSV1,Keyboard,1500.00,Electronics,12\n"
        "CSV2,Monitor,8500.00,Electronics,5\n",
        encoding="utf-8"
    )

    repo = ProductRepository()
    count = import_products_from_csv(str(csv_file), repo)
    assert count == 2
    assert repo.get_by_id("CSV1").name == "Keyboard"

    # Test Malformed CSV
    malformed_csv = tmp_path / "malformed.csv"
    malformed_csv.write_text(
        "product_id,name,price,category,quantity\n"
        "BAD1,Broken Item,NOT_A_PRICE,Electronics,5\n",
        encoding="utf-8"
    )
    with pytest.raises(MalformedCSVError):
        import_products_from_csv(str(malformed_csv), repo)

def test_json_export_and_export_order(tmp_path, catalog, cart, laptop):
    # JSON export of products
    json_file = tmp_path / "catalog_export.json"
    export_products_to_json(catalog.repository, str(json_file))
    assert json_file.exists()

    with open(json_file, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    assert len(data) == 3
    assert data[0]["product_id"] == "P101"

    # Order export
    cart.add(laptop, 2)
    order_file = tmp_path / "order_export.json"
    export_order(cart, str(order_file))
    assert order_file.exists()

    with open(order_file, mode="r", encoding="utf-8") as f:
        order_data = json.load(f)
    assert order_data["total"] == "50000.00"
    assert len(order_data["items"]) == 1

def test_configuration_parameters(catalog):
    # Low stock configuration threshold
    low_stock_items = catalog.get_low_stock_products(min_stock=12)
    assert len(low_stock_items) == 1
    assert low_stock_items[0].product_id == "P101"

    # Payment mode config
    cfg = {"payment_mode": "express"}
    assert get_payment_mode(cfg) == "express"
    assert get_payment_mode({}) == "standard"

def test_product_repository_mock():
    mock_repo = Mock(spec=ProductRepository)
    p = Product("M1", "Mocked Item", Money(Decimal("100.00")), "Mock", 5)
    mock_repo.get_all.return_value = [p]

    catalog = Catalog(repository=mock_repo)
    assert catalog.get_most_expensive() == p
    mock_repo.get_all.assert_called_once()

def test_checkout_service_mock_success(cart, laptop):
    cart.add(laptop, 1)

    mock_gateway = Mock(spec=PaymentGateway)
    mock_gateway.process_payment.return_value = True

    mock_notifier = Mock(spec=Notifier)
    mock_notifier.send_notification.return_value = True

    checkout = CheckoutService(payment_gateway=mock_gateway, notifier=mock_notifier)
    res = checkout.checkout(cart, "1234-5678-9012-3456")

    assert res is True
    assert len(cart.items) == 0  # Cart is cleared on success
    mock_gateway.process_payment.assert_called_once_with(Money(Decimal("25000.00")), "1234-5678-9012-3456")
    mock_notifier.send_notification.assert_called_once()
    assert "Успішна оплата" in mock_notifier.send_notification.call_args[0][0]

def test_checkout_service_mock_failure_and_side_effect(cart, laptop):
    cart.add(laptop, 1)

    mock_gateway = Mock(spec=PaymentGateway)
    mock_gateway.process_payment.return_value = False

    mock_notifier = Mock(spec=Notifier)

    checkout = CheckoutService(payment_gateway=mock_gateway, notifier=mock_notifier)
    res = checkout.checkout(cart, "1234-5678-9012-3456")

    assert res is False
    assert len(cart.items) == 1  # Cart is NOT cleared on failure
    mock_notifier.send_notification.assert_called_once_with("Помилка під час проведення оплати.")

    # Failure path using side_effect
    mock_gateway.process_payment.side_effect = ConnectionError("Платіжний шлюз недоступний")
    with pytest.raises(ConnectionError, match="недоступний"):
        checkout.checkout(cart, "1234-5678-9012-3456")

@pytest.mark.asyncio
async def test_async_payment_status_mock():
    mock_external_provider = Mock()
    mock_external_provider.check_transaction = AsyncMock(return_value={"status": "completed", "code": 200})

    status_service = AsyncPaymentStatus(external_provider=mock_external_provider)
    status = await status_service.verify_status("TXN-999")

    assert status == "completed"
    mock_external_provider.check_transaction.assert_awaited_once_with("TXN-999")

@pytest.mark.asyncio
async def test_async_integration_import_processing_export(tmp_path):
    # Integration flow: Async external provider -> import to repo -> processing cart -> JSON export
    mock_provider = Mock(spec=AsyncExternalCatalogProvider)
    mock_provider.fetch_external_products = AsyncMock(return_value=[
        {"product_id": "EXT-1", "name": "Tablet", "price": "10000.00", "category": "Gadgets", "quantity": 5}
    ])

    raw_items = await mock_provider.fetch_external_products()
    repo = ProductRepository()

    for item in raw_items:
        prod = Product(
            product_id=item["product_id"],
            name=item["name"],
            price=Money(Decimal(item["price"])),
            category=item["category"],
            quantity=item["quantity"]
        )
        repo.add(prod)

    cat = Catalog(repository=repo)
    found = cat.search_by_name("Tablet")
    assert len(found) == 1

    cart = Cart()
    cart.add(found[0], 2)

    export_file = tmp_path / "integration_order.json"
    export_order(cart, str(export_file))

    assert export_file.exists()
    with open(export_file, mode="r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["total"] == "20000.00"


# ==============================================================================
# 6. ГОЛОВНА ФУНКЦІЯ ДЕМОНСТРАЦІЇ
# ==============================================================================

def main():
    """Функція демонстрації роботи системи та виконання тестування."""
    print("======================================================================")
    print(" ДЕМОНСТРАЦІЯ РОБОТИ СИСТЕМИ ІНТЕРНЕТ-МАГАЗИНУ (Лабораторна робота №6)")
    print("======================================================================\n")

    p1 = Product("P101", "Ноутбук ASUS Pro", Money(Decimal("32000.00")), "Електроніка", 8)
    p2 = Product("P102", "Бездротова миша", Money(Decimal("950.00")), "Електроніка", 20)

    print(f"Створено товари:\n 1. {p1.name} — {p1.price.amount} {p1.price.currency} (Залишок: {p1.quantity})")
    print(f" 2. {p2.name} — {p2.price.amount} {p2.price.currency} (Залишок: {p2.quantity})\n")

    catalog = Catalog()
    catalog.add_product(p1)
    catalog.add_product(p2)

    print(f"Загальна вартість складських залишків: {catalog.calculate_total_stock_value().amount} грн")
    print(f"Найдорожчий товар у каталозі: {catalog.get_most_expensive().name}\n")

    cart = Cart()
    cart.add(p1, 1)
    cart.add(p2, 2)
    print(f"Загальна вартість кошика: {cart.total().amount} грн")

    discount = PercentageDiscount(Decimal("15"))
    discounted_total = discount.apply(cart.total())
    print(f"Сума до сплати зі знижкою 15%: {discounted_total.amount} грн\n")

    print("--- Демонстрація Checkout із мокованим PaymentGateway та Notifier ---")
    mock_payment = Mock()
    mock_payment.process_payment.return_value = True
    mock_notifier = Mock()

    checkout_service = CheckoutService(payment_gateway=mock_payment, notifier=mock_notifier)
    success = checkout_service.checkout(cart, "4441-2222-3333-5555")

    print(f"Результат розрахунку: {success}")
    print(f"Кількість позицій у кошику після успішної оплати: {len(cart.items)}")

    print("\n======================================================================")
    print(" ЗАПУСК МОДУЛЬНИХ ТА ІНТЕГРАЦІЙНИХ ТЕСТІВ (PYTEST)")
    print("======================================================================\n")

    sys.exit(pytest.main(["-v", __file__]))


if __name__ == "__main__":
    main()
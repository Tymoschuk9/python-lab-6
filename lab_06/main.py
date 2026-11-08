"""
Лабораторна робота №6: Автоматизоване тестування Python-програм.
Варіант №3: Інтернет-магазин (E-commerce shop).

Повністю автономний модуль, що містить виробничий код (Domain, Services, Repositories,
Exporters, Config) та вичерпний набір тестів на базі pytest (Unit & Integration).
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol
from unittest.mock import AsyncMock, Mock

import pytest


# =====================================================================
# 1. DOMAIN EXCEPTIONS
# =====================================================================

class ShopError(Exception):
    """Базовий виняток для проблем доменної області інтернет-магазину."""
    pass


class ValidationError(ShopError):
    """Виникає при спробі створити або змінити сутність з некоректними даними."""

    def __init__(self, message: str, field_name: str) -> None:
        super().__init__(message)
        self.field_name = field_name


class ProductNotFoundError(ShopError):
    """Виникає, коли запитаний товар не знайдено в каталозі."""
    pass


class DataImportError(ShopError):
    """Виникає під час синтаксичного розбору або імпорту файлів даних."""
    pass


class PaymentError(ShopError):
    """Виникає при збоях у зовнішній платіжній системі."""
    pass


class ProviderUnavailableError(ShopError):
    """Виникає при недоступності зовнішнього провайдера валютних курсів."""
    pass


# =====================================================================
# 2. VALUE OBJECTS & MODELS
# =====================================================================

class ProductCategory(str, Enum):
    """Категорії товарів інтернет-магазину."""
    ELECTRONICS = "Electronics"
    CLOTHING = "Clothing"
    BOOKS = "Books"
    HOME = "Home"
    FOOD = "Food"


@dataclass(frozen=True, slots=True)
class Money:
    """Незмінний об'єкт-значення (Value Object) для представлення грошових сум."""
    amount: float
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0.0:
            raise ValueError(f"Грошова сума не може бути від'ємною: {self.amount}")

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        if self.currency != other.currency:
            raise ValueError(
                f"Неможливо додати гроші в різних валютах: {self.currency} != {other.currency}"
            )
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __mul__(self, factor: float) -> Money:
        if factor < 0:
            raise ValueError("Множник не може бути від'ємним")
        return Money(round(self.amount * factor, 2), self.currency)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return False
        return self.currency == other.currency and abs(self.amount - other.amount) < 1e-6


@dataclass(slots=True)
class Product:
    """Доменна модель товару інтернет-магазину."""
    product_id: int
    name: str
    category: ProductCategory
    price: Money
    quantity: int

    def __post_init__(self) -> None:
        if self.product_id <= 0:
            raise ValidationError("ID товару повинен бути додатним числом", "product_id")
        if not self.name or not self.name.strip():
            raise ValidationError("Назва товару не може бути порожньою", "name")
        if self.quantity < 0:
            raise ValidationError("Кількість товару на складі не може бути від'ємною", "quantity")

    @property
    def total_stock_value(self) -> Money:
        """Повертає сумарну вартість усіх одиниць даного товару на складі."""
        return self.price * self.quantity


# =====================================================================
# 3. PROTOCOLS (INTERFACES)
# =====================================================================

class ProductRepository(Protocol):
    """Протокол сховища товарів."""

    def add(self, product: Product) -> None:
        ...

    def get_by_id(self, product_id: int) -> Optional[Product]:
        ...

    def get_all(self) -> List[Product]:
        ...

    def remove(self, product_id: int) -> bool:
        ...


class DiscountPolicy(Protocol):
    """Протокол розрахунку знижки."""

    def apply(self, total: Money) -> Money:
        ...


class Notifier(Protocol):
    """Протокол системи надсилання сповіщень."""

    def send_notification(self, recipient: str, message: str) -> None:
        ...


class PaymentGateway(Protocol):
    """Протокол платіжного шлюзу."""

    def process_payment(self, amount: Money) -> str:
        ...


class ExternalPriceProvider(Protocol):
    """Асинхронний інтерфейс отримання курсів та цін від зовнішнього постачальника."""

    async def get_exchange_rate(self, target_currency: str) -> float:
        ...


# =====================================================================
# 4. REPOSITORY & SERVICES
# =====================================================================

class InMemoryProductRepository:
    """In-memory реалізація репозиторію товарів."""

    def __init__(self) -> None:
        self._storage: Dict[int, Product] = {}

    def add(self, product: Product) -> None:
        self._storage[product.product_id] = product

    def get_by_id(self, product_id: int) -> Optional[Product]:
        return self._storage.get(product_id)

    def get_all(self) -> List[Product]:
        return list(self._storage.values())

    def remove(self, product_id: int) -> bool:
        return self._storage.pop(product_id, None) is not None


class PercentageDiscount:
    """Політика відсоткової знижки (0-100%)."""

    def __init__(self, percent: float) -> None:
        if not (0.0 <= percent <= 100.0):
            raise ValueError(f"Відсоток знижки має бути в межах [0; 100], отримано: {percent}")
        self.percent = percent

    def apply(self, total: Money) -> Money:
        discounted_amount = total.amount * (1.0 - self.percent / 100.0)
        return Money(round(discounted_amount, 2), total.currency)


class CatalogService:
    """Сервіс керування каталогом та аналітики складських залишків."""

    def __init__(self, repository: ProductRepository) -> None:
        self.repository = repository

    def add_product(self, product: Product) -> None:
        self.repository.add(product)

    def find_by_id(self, product_id: int) -> Product:
        product = self.repository.get_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(f"Товар з ID {product_id} не знайдено в каталозі")
        return product

    def search_by_name(self, query: str) -> List[Product]:
        normalized = query.strip().lower()
        if not normalized:
            return []
        return [
            p for p in self.repository.get_all()
            if normalized in p.name.lower()
        ]

    def filter_by_category(self, category: ProductCategory) -> List[Product]:
        return [
            p for p in self.repository.get_all()
            if p.category == category
        ]

    def calculate_total_inventory_value(self) -> Money:
        all_products = self.repository.get_all()
        if not all_products:
            return Money(0.0)

        total = 0.0
        currency = all_products[0].price.currency
        for p in all_products:
            if p.price.currency != currency:
                raise ValueError("Товари в каталозі мають різні валюти цін")
            total += p.total_stock_value.amount
        return Money(round(total, 2), currency)

    def get_most_expensive_product(self) -> Optional[Product]:
        products = self.repository.get_all()
        if not products:
            return None
        return max(products, key=lambda p: p.price.amount)

    def get_low_stock_products(self, threshold: int) -> List[Product]:
        if threshold < 0:
            raise ValueError("Порогове значення залишку не може бути від'ємним")
        return [p for p in self.repository.get_all() if p.quantity <= threshold]


class CheckoutService:
    """Сервіс оформлення замовлення з підтримкою сповіщень та платіжного шлюзу."""

    def __init__(
        self,
        repository: ProductRepository,
        payment_gateway: PaymentGateway,
        notifier: Notifier,
    ) -> None:
        self.repository = repository
        self.payment_gateway = payment_gateway
        self.notifier = notifier

    def checkout(
        self,
        customer_email: str,
        product_ids: List[int],
        discount: Optional[DiscountPolicy] = None,
    ) -> str:
        if not product_ids:
            raise ValueError("Список товарів для замовлення не може бути порожнім")

        total_sum = 0.0
        currency = "UAH"

        for pid in product_ids:
            product = self.repository.get_by_id(pid)
            if product is None:
                raise ProductNotFoundError(f"Неможливо оформити замовлення: товар {pid} відсутній")
            if product.quantity <= 0:
                raise ShopError(f"Товар {product.name} закінчився на складі")
            total_sum += product.price.amount
            currency = product.price.currency

        order_total = Money(round(total_sum, 2), currency)
        if discount:
            order_total = discount.apply(order_total)

        payment_id = self.payment_gateway.process_payment(order_total)
        self.notifier.send_notification(
            customer_email,
            f"Замовлення успішно сплачено на суму {order_total.amount} {order_total.currency}. Код транзакції: {payment_id}"
        )
        return payment_id


class AsyncCurrencyConverter:
    """Асинхронний сервіс перерахунку вартості залишків у зовнішню валюту."""

    def __init__(self, provider: ExternalPriceProvider) -> None:
        self.provider = provider

    async def convert_product_price(self, product: Product, target_currency: str) -> Money:
        rate = await self.provider.get_exchange_rate(target_currency)
        if rate <= 0.0:
            raise ValueError(f"Некоректний валютний курс: {rate}")
        converted = round(product.price.amount * rate, 2)
        return Money(converted, target_currency)


# =====================================================================
# 5. CONFIGURATION & I/O (CSV / JSON)
# =====================================================================

class AppConfig:
    """Конфігурація застосунку із читанням параметрів середовища."""

    @staticmethod
    def get_min_stock_threshold() -> int:
        raw_val = os.getenv("SHOP_MIN_STOCK_THRESHOLD", "5")
        try:
            val = int(raw_val)
            if val < 0:
                return 5
            return val
        except ValueError:
            return 5

    @staticmethod
    def get_environment() -> str:
        return os.getenv("SHOP_ENV", "development")


class ProductIO:
    """Модуль імпорту та експорту товарів у формати CSV та JSON."""

    @staticmethod
    def import_from_csv(file_path: Path) -> List[Product]:
        if not file_path.exists():
            raise FileNotFoundError(f"Файл {file_path} не існує")

        products: List[Product] = []
        with open(file_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required_fields = {"product_id", "name", "category", "price", "currency", "quantity"}
            if not reader.fieldnames or not required_fields.issubset(set(reader.fieldnames)):
                raise DataImportError("CSV файл не містить необхідних заголовків стовпців")

            for row_idx, row in enumerate(reader, start=2):
                try:
                    product_id = int(row["product_id"])
                    name = row["name"]
                    category = ProductCategory(row["category"])
                    price_val = float(row["price"])
                    currency = row["currency"]
                    quantity = int(row["quantity"])

                    product = Product(
                        product_id=product_id,
                        name=name,
                        category=category,
                        price=Money(price_val, currency),
                        quantity=quantity,
                    )
                    products.append(product)
                except (ValueError, KeyError, ValidationError) as err:
                    raise DataImportError(
                        f"Помилка в рядку {row_idx}: некоректні дані товару ({err})"
                    ) from err
        return products

    @staticmethod
    def export_to_json(products: List[Product], file_path: Path) -> None:
        data = [
            {
                "product_id": p.product_id,
                "name": p.name,
                "category": p.category.value,
                "price": p.price.amount,
                "currency": p.price.currency,
                "quantity": p.quantity,
                "total_stock_value": p.total_stock_value.amount,
            }
            for p in products
        ]
        file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# =====================================================================
# 6. PYTEST FIXTURES (conftest / shared setup)
# =====================================================================

@pytest.fixture
def laptop_product() -> Product:
    """Фікстура одиничного товару (ноутбук)."""
    return Product(
        product_id=1,
        name="Lenovo ThinkPad",
        category=ProductCategory.ELECTRONICS,
        price=Money(32000.0, "UAH"),
        quantity=8,
    )


@pytest.fixture
def sample_inventory() -> List[Product]:
    """Фікстура списку товарів різних категорій для тестування каталогу."""
    return [
        Product(1, "ThinkPad X1", ProductCategory.ELECTRONICS, Money(45000.0), 3),
        Product(2, "Logitech MX Master", ProductCategory.ELECTRONICS, Money(3800.0), 12),
        Product(3, "Python Design Patterns", ProductCategory.BOOKS, Money(950.0), 20),
        Product(4, "Clean Architecture Book", ProductCategory.BOOKS, Money(1100.0), 5),
        Product(5, "Warm Winter Hoodie", ProductCategory.CLOTHING, Money(2200.0), 2),
    ]


@pytest.fixture
def product_repository(sample_inventory: List[Product]) -> InMemoryProductRepository:
    """Фікстура попередньо заповненого In-memory репозиторію."""
    repo = InMemoryProductRepository()
    for prod in sample_inventory:
        repo.add(prod)
    return repo


@pytest.fixture
def catalog_service(product_repository: InMemoryProductRepository) -> CatalogService:
    """Фікстура CatalogService із заповненим репозиторієм."""
    return CatalogService(product_repository)


@pytest.fixture
def product_factory() -> Callable[..., Product]:
    """Fixture-фабрика для динамічного створення товарів у тестах."""
    counter = 100

    def _factory(
        name: str = "Test Item",
        category: ProductCategory = ProductCategory.ELECTRONICS,
        price_amount: float = 1000.0,
        quantity: int = 10,
    ) -> Product:
        nonlocal counter
        counter += 1
        return Product(
            product_id=counter,
            name=name,
            category=category,
            price=Money(price_amount),
            quantity=quantity,
        )

    return _factory


# =====================================================================
# 7. UNIT TESTS (24 tests >= 15 required)
# =====================================================================

# --- Money Value Object Tests ---

def test_money_creation_and_attributes() -> None:
    money = Money(150.75, "USD")
    assert money.amount == 150.75
    assert money.currency == "USD"


def test_money_negative_amount_raises_exception() -> None:
    with pytest.raises(ValueError, match="не може бути від'ємною"):
        Money(-10.0, "UAH")


def test_money_addition_same_currency() -> None:
    m1 = Money(100.25, "UAH")
    m2 = Money(49.75, "UAH")
    total = m1 + m2
    assert total.amount == pytest.approx(150.0)
    assert total.currency == "UAH"


def test_money_addition_currency_mismatch_raises_exception() -> None:
    m1 = Money(100.0, "UAH")
    m2 = Money(100.0, "USD")
    with pytest.raises(ValueError, match="різних валютах"):
        _ = m1 + m2


# --- Product Creation & Boundary Tests (Parameterized) ---

@pytest.mark.parametrize(
    "price,quantity",
    [
        (0.0, 0),        # Нижня гранична межа: безкоштовний подарунок, нульовий залишок
        (0.01, 1),       # Мінімальна додатна ціна
        (999999.99, 1000),  # Великі коректні значення
    ],
    ids=["zero_boundary", "minimal_positive", "large_valid"]
)
def test_product_boundary_valid_values(price: float, quantity: int) -> None:
    prod = Product(
        product_id=1,
        name="Boundary Item",
        category=ProductCategory.HOME,
        price=Money(price),
        quantity=quantity,
    )
    assert prod.price.amount == pytest.approx(price)
    assert prod.quantity == quantity


@pytest.mark.parametrize(
    "invalid_id,name,quantity,expected_field",
    [
        (0, "Item", 5, "product_id"),
        (-5, "Item", 5, "product_id"),
        (1, "", 5, "name"),
        (1, "   ", 5, "name"),
        (1, "Item", -1, "quantity"),
    ],
    ids=["zero_id", "negative_id", "empty_name", "whitespace_name", "negative_quantity"]
)
def test_product_invalid_inputs_raise_validation_error(
    invalid_id: int, name: str, quantity: int, expected_field: str
) -> None:
    with pytest.raises(ValidationError) as exc_info:
        Product(
            product_id=invalid_id,
            name=name,
            category=ProductCategory.BOOKS,
            price=Money(100.0),
            quantity=quantity,
        )
    assert exc_info.value.field_name == expected_field


def test_product_total_stock_value_calculation(laptop_product: Product) -> None:
    # 32000.0 * 8 = 256000.0
    assert laptop_product.total_stock_value == Money(256000.0, "UAH")


# --- CatalogService Unit Tests ---

def test_catalog_add_and_find_by_id(catalog_service: CatalogService, product_factory: Callable[..., Product]) -> None:
    new_prod = product_factory(name="Mechanical Keyboard", price_amount=3500.0)
    catalog_service.add_product(new_prod)

    found = catalog_service.find_by_id(new_prod.product_id)
    assert found.name == "Mechanical Keyboard"
    assert found.price.amount == 3500.0


def test_catalog_find_by_id_not_found_raises_custom_exception(catalog_service: CatalogService) -> None:
    with pytest.raises(ProductNotFoundError, match="не знайдено в каталозі"):
        catalog_service.find_by_id(9999)


def test_catalog_search_by_name(catalog_service: CatalogService) -> None:
    results = catalog_service.search_by_name("book")
    assert len(results) == 2
    assert all("Book" in p.name or "book" in p.name.lower() for p in results)


def test_catalog_search_empty_query_returns_empty_list(catalog_service: CatalogService) -> None:
    assert catalog_service.search_by_name("") == []
    assert catalog_service.search_by_name("   ") == []


def test_catalog_filter_by_category(catalog_service: CatalogService) -> None:
    books = catalog_service.filter_by_category(ProductCategory.BOOKS)
    assert len(books) == 2
    electronics = catalog_service.filter_by_category(ProductCategory.ELECTRONICS)
    assert len(electronics) == 2
    food = catalog_service.filter_by_category(ProductCategory.FOOD)
    assert food == []


def test_catalog_total_inventory_value(catalog_service: CatalogService) -> None:
    # ThinkPad: 45000*3=135000; Mouse: 3800*12=45600; PyBook: 950*20=19000;
    # CleanArch: 1100*5=5500; Hoodie: 2200*2=4400. Sum = 209500.0
    total = catalog_service.calculate_total_inventory_value()
    assert total.amount == pytest.approx(209500.0)


def test_catalog_empty_inventory_calculations() -> None:
    empty_catalog = CatalogService(InMemoryProductRepository())
    assert empty_catalog.calculate_total_inventory_value() == Money(0.0)
    assert empty_catalog.get_most_expensive_product() is None


def test_catalog_most_expensive_product(catalog_service: CatalogService) -> None:
    most_expensive = catalog_service.get_most_expensive_product()
    assert most_expensive is not None
    assert most_expensive.product_id == 1
    assert most_expensive.price.amount == 45000.0


def test_catalog_low_stock_filtering(catalog_service: CatalogService) -> None:
    low_stock = catalog_service.get_low_stock_products(threshold=3)
    # ThinkPad (3) та Hoodie (2)
    assert len(low_stock) == 2
    assert {p.product_id for p in low_stock} == {1, 5}


def test_catalog_low_stock_negative_threshold_raises_value_error(catalog_service: CatalogService) -> None:
    with pytest.raises(ValueError, match="не може бути від'ємним"):
        catalog_service.get_low_stock_products(threshold=-1)


# --- Discount Policy Unit Tests (Parameterized) ---

@pytest.mark.parametrize(
    "percent,original,expected",
    [
        (0.0, 1000.0, 1000.0),    # Нульова знижка
        (10.0, 1000.0, 900.0),     # 10%
        (25.5, 200.0, 149.0),      # Дробовий відсоток
        (100.0, 500.0, 0.0),       # 100% знижка (повністю безкоштовно)
    ],
    ids=["0_percent", "10_percent", "fractional_percent", "100_percent"]
)
def test_percentage_discount_calculation(percent: float, original: float, expected: float) -> None:
    policy = PercentageDiscount(percent)
    result = policy.apply(Money(original))
    assert result.amount == pytest.approx(expected)


@pytest.mark.parametrize(
    "invalid_percent",
    [-0.01, -15.0, 100.01, 150.0],
    ids=["below_zero", "negative_large", "above_100", "large_invalid"]
)
def test_percentage_discount_invalid_raises_value_error(invalid_percent: float) -> None:
    with pytest.raises(ValueError, match="в межах"):
        PercentageDiscount(invalid_percent)


# --- CheckoutService Tests with Mocks & Interaction Assertions ---

def test_checkout_successful_flow_with_mocks(product_repository: InMemoryProductRepository) -> None:
    # Arrange
    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.process_payment.return_value = "TXN-998877"

    notifier_mock = Mock(spec=Notifier)
    service = CheckoutService(product_repository, gateway_mock, notifier_mock)
    discount = PercentageDiscount(10.0)

    # Act
    # Купуємо товар 3 (950 грн) та 4 (1100 грн). Сума = 2050 грн. Знижка 10% -> 1845 грн
    txn_id = service.checkout("student@univ.edu.ua", [3, 4], discount=discount)

    # Assert
    assert txn_id == "TXN-998877"
    gateway_mock.process_payment.assert_called_once_with(Money(1845.0, "UAH"))
    notifier_mock.send_notification.assert_called_once()
    recipient, msg = notifier_mock.send_notification.call_args[0]
    assert recipient == "student@univ.edu.ua"
    assert "TXN-998877" in msg


def test_checkout_payment_failure_side_effect(product_repository: InMemoryProductRepository) -> None:
    # Arrange: Імітація збою платіжного шлюзу через side_effect
    gateway_mock = Mock(spec=PaymentGateway)
    gateway_mock.process_payment.side_effect = PaymentError("Банківський сервіс тимчасово недоступний")

    notifier_mock = Mock(spec=Notifier)
    service = CheckoutService(product_repository, gateway_mock, notifier_mock)

    # Act & Assert
    with pytest.raises(PaymentError, match="Банківський сервіс"):
        service.checkout("client@example.com", [1])

    # Перевірка контракту взаємодії: при невдачі оплати сповіщення КЛІЄНТУ НЕ НАДСИЛАЄТЬСЯ
    notifier_mock.send_notification.assert_not_called()


def test_checkout_empty_items_raises_value_error(product_repository: InMemoryProductRepository) -> None:
    service = CheckoutService(product_repository, Mock(spec=PaymentGateway), Mock(spec=Notifier))
    with pytest.raises(ValueError, match="не може бути порожнім"):
        service.checkout("client@example.com", [])


# --- Configuration Test with monkeypatch ---

def test_config_min_stock_threshold_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_MIN_STOCK_THRESHOLD", "15")
    assert AppConfig.get_min_stock_threshold() == 15


def test_config_min_stock_threshold_defaults_and_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOP_MIN_STOCK_THRESHOLD", raising=False)
    assert AppConfig.get_min_stock_threshold() == 5

    monkeypatch.setenv("SHOP_MIN_STOCK_THRESHOLD", "invalid_number")
    assert AppConfig.get_min_stock_threshold() == 5


# --- Async External Provider Tests with AsyncMock ---

def test_async_currency_converter_success(laptop_product: Product) -> None:
    async def _run() -> None:
        provider_mock = AsyncMock(spec=ExternalPriceProvider)
        provider_mock.get_exchange_rate.return_value = 0.024  # 1 UAH = ~0.024 EUR

        converter = AsyncCurrencyConverter(provider_mock)
        # 32000 UAH * 0.024 = 768.0 EUR
        converted = await converter.convert_product_price(laptop_product, "EUR")

        assert converted.amount == pytest.approx(768.0)
        assert converted.currency == "EUR"
        provider_mock.get_exchange_rate.assert_awaited_once_with("EUR")

    asyncio.run(_run())


def test_async_currency_converter_provider_error(laptop_product: Product) -> None:
    async def _run() -> None:
        provider_mock = AsyncMock(spec=ExternalPriceProvider)
        provider_mock.get_exchange_rate.side_effect = ProviderUnavailableError("API Gateway Timeout")

        converter = AsyncCurrencyConverter(provider_mock)

        with pytest.raises(ProviderUnavailableError, match="Gateway Timeout"):
            await converter.convert_product_price(laptop_product, "USD")

    asyncio.run(_run())


# --- CSV Import Error Path & Exception Chaining ---

def test_csv_import_malformed_record_causes_data_import_error(tmp_path: Path) -> None:
    broken_csv = tmp_path / "broken_products.csv"
    broken_csv.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "1,Valid Item,Books,100.0,UAH,10\n"
        "2,Broken Price,Books,NOT_A_NUMBER,UAH,5\n",
        encoding="utf-8"
    )

    with pytest.raises(DataImportError) as exc_info:
        ProductIO.import_from_csv(broken_csv)

    assert "Помилка в рядку 3" in str(exc_info.value)
    # Перевірка ланцюжка винятків (exception chaining via __cause__)
    assert isinstance(exc_info.value.__cause__, ValueError)


# =====================================================================
# 8. INTEGRATION TESTS (3 required)
# =====================================================================

@pytest.mark.integration
def test_integration_csv_import_to_catalog_calculation(tmp_path: Path) -> None:
    """
    Інтеграційний тест 1: Файлова система CSV -> Парсер -> Репозиторій -> Каталог -> Розрахунок залишків.
    """
    # 1. Arrange: Створення тимчасового валідного CSV-файлу
    csv_file = tmp_path / "imported_stock.csv"
    csv_file.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "101,Office Chair,Home,4200.00,UAH,5\n"
        "102,LED Lamp,Home,800.50,UAH,10\n"
        "103,Bluetooth Speaker,Electronics,1500.00,UAH,4\n",
        encoding="utf-8"
    )

    # 2. Act: Імпорт та додавання до каталогу
    imported_products = ProductIO.import_from_csv(csv_file)
    repo = InMemoryProductRepository()
    catalog = CatalogService(repo)
    for p in imported_products:
        catalog.add_product(p)

    # 3. Assert: Перевірка стану каталогу та взаємодії компонентів
    assert len(imported_products) == 3
    # 4200*5 (21000) + 800.5*10 (8005) + 1500*4 (6000) = 35005.00
    total_value = catalog.calculate_total_inventory_value()
    assert total_value.amount == pytest.approx(35005.00)
    assert total_value.currency == "UAH"


@pytest.mark.integration
def test_integration_catalog_processing_and_json_export(tmp_path: Path, sample_inventory: List[Product]) -> None:
    """
    Інтеграційний тест 2: Сховище -> Каталог -> Фільтрація low stock -> Експорт у JSON файл -> Читання з диска.
    """
    # 1. Arrange
    repo = InMemoryProductRepository()
    for prod in sample_inventory:
        repo.add(prod)
    catalog = CatalogService(repo)

    # 2. Act: Отримання товарів із залишком <= 5 та експорт у тимчасовий JSON
    low_stock = catalog.get_low_stock_products(threshold=5)
    export_path = tmp_path / "low_stock_report.json"
    ProductIO.export_to_json(low_stock, export_path)

    # 3. Assert: Перевірка реального створення та структури збереженого файлу
    assert export_path.exists()
    raw_content = export_path.read_text(encoding="utf-8")
    loaded_data = json.loads(raw_content)

    assert isinstance(loaded_data, list)
    # З 5 товарів вибірки залишком <= 5 мають: ThinkPad (3), CleanArch (5), Hoodie (2) -> 3 товари
    assert len(loaded_data) == 3
    exported_ids = [item["product_id"] for item in loaded_data]
    assert set(exported_ids) == {1, 4, 5}


@pytest.mark.integration
def test_integration_full_import_discount_async_rate_and_export_flow(tmp_path: Path) -> None:
    """
    Інтеграційний тест 3: Наскрізний ланцюг: CSV Import -> Catalog Processing ->
    Discount Calculation -> Async Currency Conversion -> JSON Export.
    """
    # 1. Arrange: Створюємо вхідний CSV
    csv_file = tmp_path / "incoming_goods.csv"
    csv_file.write_text(
        "product_id,name,category,price,currency,quantity\n"
        "201,Wireless Headphones,Electronics,2500.0,UAH,10\n"
        "202,Smart Watch,Electronics,5000.0,UAH,6\n",
        encoding="utf-8"
    )

    # Mock зовнішнього асинхронного джерела валюти
    rate_provider_mock = AsyncMock(spec=ExternalPriceProvider)
    rate_provider_mock.get_exchange_rate.return_value = 0.025  # 1 UAH = 0.025 USD
    converter = AsyncCurrencyConverter(rate_provider_mock)

    async def _pipeline() -> None:
        # 2. Act: Імпорт
        products = ProductIO.import_from_csv(csv_file)
        repo = InMemoryProductRepository()
        catalog = CatalogService(repo)
        for prod in products:
            catalog.add_product(prod)

        # Конвертуємо ціни в USD асинхронно
        converted_products: List[Product] = []
        for prod in catalog.repository.get_all():
            new_price = await converter.convert_product_price(prod, "USD")
            converted_prod = Product(
                product_id=prod.product_id,
                name=prod.name,
                category=prod.category,
                price=new_price,
                quantity=prod.quantity,
            )
            converted_products.append(converted_prod)

        # Експорт у фінальний звіт
        output_json = tmp_path / "international_catalog.json"
        ProductIO.export_to_json(converted_products, output_json)

        # 3. Assert
        assert output_json.exists()
        data = json.loads(output_json.read_text(encoding="utf-8"))
        assert len(data) == 2
        # 2500 * 0.025 = 62.5 USD
        assert data[0]["price"] == pytest.approx(62.5)
        assert data[0]["currency"] == "USD"
        # 5000 * 0.025 = 125.0 USD
        assert data[1]["price"] == pytest.approx(125.0)
        assert data[1]["currency"] == "USD"

    asyncio.run(_pipeline())


# =====================================================================
# 9. DEMONSTRATION & CLI ENTRYPOINT
# =====================================================================

def main() -> None:
    """Точка входу для демонстрації роботи та автоматичного запуску pytest."""
    print("=" * 80)
    print("  ЛАБОРАТОРНА РОБОТА №6. ТЕСТУВАННЯ PYTHON-ПРОГРАМ (ВАРІАНТ №3: ІНТЕРНЕТ-МАГАЗИН)")
    print("=" * 80)
    print("Виконання демонстраційного сценарію доменної логіки...")

    # Базова демонстрація бізнес-логіки
    repo = InMemoryProductRepository()
    catalog = CatalogService(repo)
    p1 = Product(1, "Dell UltraSharp Monitor", ProductCategory.ELECTRONICS, Money(14500.0), 4)
    p2 = Product(2, "Ergonomic Keyboard", ProductCategory.ELECTRONICS, Money(2800.0), 15)
    catalog.add_product(p1)
    catalog.add_product(p2)

    print(f"Додано товарів до каталогу: {len(catalog.repository.get_all())}")
    print(f"Загальна вартість складу: {catalog.calculate_total_inventory_value().amount} UAH")
    print(f"Найдорожчий товар: {catalog.get_most_expensive_product().name}")
    print("-" * 80)
    print("Запуск автоматизованого тест-сьюту за допомогою pytest...")
    print("-" * 80)

    # Програмний запуск pytest для поточного файлу з детальним звітом
    pytest_args = [
        __file__,
        "-v",
        "--tb=short",
        "-ra",
    ]

    try:
        import pytest_cov  # noqa: F401
        pytest_args.extend(["--cov", "--cov-report=term-missing"])
    except ImportError:
        pass

    exit_code = pytest.main(pytest_args)
    if exit_code == 0:
        print("\nВсі автоматизовані тести (Unit & Integration) успішно виконані!")
    else:
        print(f"\nТестування завершилося з кодом: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
"""
Лабораторна робота №6 з дисципліни "Тестування та забезпечення якості ПЗ"
Тема: Автоматизоване тестування Python-програм (pytest)
Варіант №3: Інтернет-магазин

Даний модуль містить повну реалізацію предметної області "Інтернет-магазин", 
сервісів обробки замовлень, моків залежностей, асинхронних провайдерів 
s комплект тестових сценаріїв pytest.
"""

import asyncio
import csv
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest


# =====================================================================
# ДИСЦИПЛІНАРНІ ВИУЧЕНІ ВИЙНЯТКИ (EXCEPTIONS)
# =====================================================================

class InvalidProductDataError(ValueError):
    """Викликається при виявленні невалідних даних товару або грошових сум."""
    pass


class MalformedRecordError(ValueError):
    """Викликається при імпорті CSV з некоректною/пошкодженою структурою."""
    pass


class InsufficientStockError(Exception):
    """Викликається, якщо на складі недостатня кількість товару."""
    pass


class PaymentError(Exception):
    """Викликається при відмові або помилці платіжного шлюзу."""
    pass


# =====================================================================
# ДОМЕННІ МОДЕЛІ (DOMAIN MODELS)
# =====================================================================

@dataclass(frozen=True)
class Money:
    """
    Модель грошової суми з підтримкою валюти та арифметичних операцій.
    """
    amount: float
    currency: str = "UAH"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise InvalidProductDataError("Сума грошей не може бути від'ємною.")

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Неможливо додавати різні валюти: {self.currency} та {other.currency}")
        return Money(round(self.amount + other.amount, 2), self.currency)

    def __sub__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"Неможливо віднімати різні валюти: {self.currency} та {other.currency}")
        if self.amount < other.amount:
            raise InvalidProductDataError("Результат віднімання від'ємний.")
        return Money(round(self.amount - other.amount, 2), self.currency)

    def __mul__(self, factor: float) -> "Money":
        if factor < 0:
            raise InvalidProductDataError("Множник не може бути від'ємним.")
        return Money(round(self.amount * factor, 2), self.currency)


class Product:
    """
    Сутність товару в інтернет-магазині.
    """
    def __init__(
        self,
        product_id: str,
        name: str,
        price: Money,
        category: str = "General",
        quantity: int = 0
    ) -> None:
        if not product_id or not str(product_id).strip():
            raise InvalidProductDataError("ID товару не може бути порожнім.")
        if not name or not str(name).strip():
            raise InvalidProductDataError("Назва товару не може бути порожньою.")
        if not isinstance(price, Money):
            raise InvalidProductDataError("Ціна товару повинна бути об'єктом Money.")
        if quantity < 0:
            raise InvalidProductDataError("Кількість товару не може бути від'ємною.")

        self.product_id: str = str(product_id).strip()
        self.name: str = str(name).strip()
        self.price: Money = price
        self.category: str = str(category).strip()
        self.quantity: int = quantity

    def __repr__(self) -> str:
        return f"Product(id='{self.product_id}', name='{self.name}', price={self.price.amount} {self.price.currency}, qty={self.quantity})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Product):
            return False
        return (
            self.product_id == other.product_id and
            self.name == other.name and
            self.price == other.price and
            self.category == other.category and
            self.quantity == other.quantity
        )


class CartItem:
    """
    Елемент кошика покупок (товар та його кількість).
    """
    def __init__(self, product: Product, quantity: int = 1) -> None:
        if quantity <= 0:
            raise InvalidProductDataError("Кількість товару в кошику повинна бути більше 0.")
        self.product: Product = product
        self.quantity: int = quantity

    def total_price(self) -> Money:
        """Обчислює підсумкову вартість даної позиції."""
        return self.product.price * self.quantity


class Cart:
    """
    Кошик покупця.
    """
    def __init__(self, items: Optional[List[CartItem]] = None) -> None:
        self.items: List[CartItem] = items if items is not None else []

    def add(self, product: Product, quantity: int = 1) -> None:
        """Додає товар до кошика або збільшує кількість існуючого."""
        for item in self.items:
            if item.product.product_id == product.product_id:
                item.quantity += quantity
                return
        self.items.append(CartItem(product, quantity))

    def total(self) -> Money:
        """Обчислює загальну вартість кошика."""
        if not self.items:
            return Money(0.0, "UAH")
        currency = self.items[0].product.price.currency
        total_val = sum(item.total_price().amount for item in self.items)
        return Money(round(total_val, 2), currency)

    def get_most_expensive_product(self) -> Optional[Product]:
        """Повертає найдорожчий товар у кошику."""
        if not self.items:
            return None
        return max(self.items, key=lambda item: item.product.price.amount).product

    def clear(self) -> None:
        """Очищує кошик."""
        self.items.clear()


class PercentageDiscount:
    """
    Стратегія застосування відсоткової знижки.
    """
    def __init__(self, percent: float) -> None:
        if not (0 <= percent <= 100):
            raise InvalidProductDataError("Відсоток знижки повинен бути у межах від 0 до 100.")
        self.percent: float = percent

    def apply(self, money: Money) -> Money:
        """Застосовує знижку до грошової суми."""
        discount_amount = round(money.amount * (self.percent / 100.0), 2)
        return Money(round(money.amount - discount_amount, 2), money.currency)


# =====================================================================
# РЕПОЗИТОРІЙ ТА КАТАЛОГ (PRODUCT REPOSITORY)
# =====================================================================

class ProductRepository:
    """
    Репозиторій для управління каталогом товарів.
    """
    def __init__(self, min_stock_threshold: int = 5) -> None:
        self.products: Dict[str, Product] = {}
        self.min_stock_threshold: int = min_stock_threshold

    def add_product(self, product: Product) -> None:
        """Додає товар до каталогу."""
        self.products[product.product_id] = product

    def get_by_id(self, product_id: str) -> Optional[Product]:
        """Отримує товар за його ID."""
        return self.products.get(product_id)

    def search_by_name(self, query: str) -> List[Product]:
        """Здійснює пошук товарів за підстрічкою в назві."""
        q = query.lower().strip()
        return [p for p in self.products.values() if q in p.name.lower()]

    def filter_by_category(self, category: str) -> List[Product]:
        """Фільтрує товари за категорією."""
        cat = category.lower().strip()
        return [p for p in self.products.values() if p.category.lower() == cat]

    def get_total_inventory_value(self) -> Money:
        """Обчислює загальну вартість усіх залишків товарів на складі."""
        if not self.products:
            return Money(0.0, "UAH")
        currency = next(iter(self.products.values())).price.currency
        total = sum(p.price.amount * p.quantity for p in self.products.values())
        return Money(round(total, 2), currency)

    def get_most_expensive(self) -> Optional[Product]:
        """Знаходить найдорожчий товар у каталозі."""
        if not self.products:
            return None
        return max(self.products.values(), key=lambda p: p.price.amount)

    def get_low_stock_products(self) -> List[Product]:
        """Повертає товари, кількість яких не перевищує поріг min_stock_threshold."""
        return [p for p in self.products.values() if p.quantity <= self.min_stock_threshold]

    def import_csv(self, csv_content: str) -> int:
        """
        Імпортує товари з CSV-стрічки.
        Викидає MalformedRecordError при некоректних даних.
        """
        lines = csv_content.strip().splitlines()
        if not lines:
            return 0
        reader = csv.DictReader(lines)
        count = 0
        for row in reader:
            try:
                p_id = row['product_id']
                name = row['name']
                price_val = float(row['price'])
                currency = row.get('currency', 'UAH')
                category = row.get('category', 'General')
                quantity = int(row['quantity'])
                product = Product(p_id, name, Money(price_val, currency), category, quantity)
                self.add_product(product)
                count += 1
            except (KeyError, ValueError) as e:
                raise MalformedRecordError(f"Помилка зчитування CSV запису '{row}': {e}")
        return count

    def export_json(self) -> str:
        """Експортує каталог у формат JSON."""
        data = [
            {
                "product_id": p.product_id,
                "name": p.name,
                "price": p.price.amount,
                "currency": p.price.currency,
                "category": p.category,
                "quantity": p.quantity
            }
            for p in self.products.values()
        ]
        return json.dumps(data, indent=2, ensure_ascii=False)


# =====================================================================
# ЗОВНІШНІ ЗЕЛЕЖНОСТІ ТА СЕРВІСИ (INTERFACES / SERVICES)
# =====================================================================

class PaymentGateway:
    """Інтерфейс платіжного шлюзу."""
    def process_payment(self, money: Money) -> bool:
        raise NotImplementedError("Метод повинен бути реалізований підкласом.")


class Notifier:
    """Інтерфейс надсилання повідомлень."""
    def send_notification(self, message: str) -> bool:
        raise NotImplementedError("Метод повинен бути реалізований підкласом.")


class CheckoutService:
    """Сервіс оформлення та оплати замовлення."""
    def __init__(self, payment_gateway: PaymentGateway, notifier: Notifier) -> None:
        self.payment_gateway: PaymentGateway = payment_gateway
        self.notifier: Notifier = notifier

    def checkout(self, cart: Cart, discount: Optional[PercentageDiscount] = None) -> Money:
        """Виконує процедуру розрахунку за замовлення."""
        total_money = cart.total()
        if total_money.amount == 0:
            raise InvalidProductDataError("Неможливо оформити порожній кошик.")

        if discount:
            total_money = discount.apply(total_money)

        success = self.payment_gateway.process_payment(total_money)
        if not success:
            raise PaymentError("Транзакцію відхилено платіжним шлюзом.")

        msg = f"Замовлення успішно оплачено. Сума: {total_money.amount} {total_money.currency}"
        self.notifier.send_notification(msg)
        return total_money


class AsyncPaymentStatus:
    """Асинхронний сервіс перевірки транзакцій та імпорту зовнішнього каталогу."""
    async def fetch_remote_inventory(self, provider_url: str) -> List[dict]:
        await asyncio.sleep(0.01)
        return [
            {"product_id": "P999", "name": "Async External Product", "price": 1200.0, "category": "Gadgets", "quantity": 10}
        ]

    async def verify_payment(self, transaction_id: str) -> bool:
        await asyncio.sleep(0.01)
        return True


# =====================================================================
# ДОПОМІЖНІ ФУНКЦІЇ ЕКСПОРТУ ТА КОНФІГУРАЦІЇ
# =====================================================================

def export_order(cart: Cart, filepath: str) -> None:
    """Експортує замовлення у JSON-файл."""
    data = {
        "total": cart.total().amount,
        "currency": cart.total().currency,
        "items_count": len(cart.items),
        "items": [
            {
                "product_id": item.product.product_id,
                "name": item.product.name,
                "quantity": item.quantity,
                "subtotal": item.total_price().amount
            }
            for item in cart.items
        ]
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_payment_mode(env: str) -> str:
    """Повертає конфігураційний режим оплати."""
    modes = {
        "dev": "TEST_GATEWAY",
        "prod": "LIQPAY_SECURE",
        "test": "MOCK_PAYMENT"
    }
    return modes.get(env.lower(), "TEST_GATEWAY")


# =====================================================================
# PYTEST TEST SUITE (ФІКСТУРИ ТА ТЕСТОВІ СЦЕНАРІЇ ВАРІАНТА №3)
# =====================================================================

@pytest.fixture
def laptop() -> Product:
    """Фікстура: Ноутбук Dell."""
    return Product("P001", "Laptop Dell", Money(25000.0, "UAH"), "Electronics", 10)


@pytest.fixture
def mouse() -> Product:
    """Фікстура: Миша Wireless."""
    return Product("P002", "Wireless Mouse", Money(500.0, "UAH"), "Electronics", 50)


@pytest.fixture
def cart(laptop: Product, mouse: Product) -> Cart:
    """Фікстура: Наповнений кошик."""
    c = Cart()
    c.add(laptop, 1)
    c.add(mouse, 2)
    return c


@pytest.fixture
def catalog(laptop: Product, mouse: Product) -> ProductRepository:
    """Фікстура: Заповнений репозиторій товарів."""
    repo = ProductRepository(min_stock_threshold=15)
    repo.add_product(laptop)
    repo.add_product(mouse)
    return repo


# --- Тести моделей та валідації ---

def test_product_creation_and_validation():
    p = Product("P1", "Keyboard", Money(1200.0, "UAH"), "Electronics", 5)
    assert p.product_id == "P1"
    assert p.name == "Keyboard"
    assert p.price.amount == 1200.0
    assert p.quantity == 5

    with pytest.raises(InvalidProductDataError):
        Product("", "Keyboard", Money(100.0), "Electronics", 5)

    with pytest.raises(InvalidProductDataError):
        Product("P1", "", Money(100.0), "Electronics", 5)

    with pytest.raises(InvalidProductDataError):
        Product("P1", "Keyboard", Money(100.0), "Electronics", -1)


def test_money_operations_and_boundary():
    m1 = Money(100.0, "UAH")
    m2 = Money(50.0, "UAH")
    assert (m1 + m2).amount == 150.0
    assert (m1 - m2).amount == 50.0
    assert (m1 * 2).amount == 200.0

    with pytest.raises(InvalidProductDataError):
        Money(-10.0, "UAH")

    with pytest.raises(InvalidProductDataError):
        m2 - m1


def test_cart_operations(cart: Cart, laptop: Product, mouse: Product):
    assert len(cart.items) == 2
    # 25000 * 1 + 500 * 2 = 26000.0
    assert cart.total().amount == 26000.0
    assert cart.get_most_expensive_product() == laptop

    cart.clear()
    assert len(cart.items) == 0
    assert cart.total().amount == 0.0
    assert cart.get_most_expensive_product() is None


def test_percentage_discount():
    discount = PercentageDiscount(10)
    money = Money(1000.0, "UAH")
    result = discount.apply(money)
    assert result.amount == 900.0

    with pytest.raises(InvalidProductDataError):
        PercentageDiscount(-5)

    with pytest.raises(InvalidProductDataError):
        PercentageDiscount(105)


def test_catalog_search_and_filter(catalog: ProductRepository, laptop: Product):
    search_res = catalog.search_by_name("dell")
    assert len(search_res) == 1
    assert search_res[0] == laptop

    cat_res = catalog.filter_by_category("Electronics")
    assert len(cat_res) == 2

    # Загальна вартість залишків: 25000*10 + 500*50 = 275000
    assert catalog.get_total_inventory_value().amount == 275000.0
    assert catalog.get_most_expensive() == laptop

    # Поріг = 15. У ноутбука 10 (<= 15), у миші 50 (> 15).
    low_stock = catalog.get_low_stock_products()
    assert len(low_stock) == 1
    assert low_stock[0] == laptop


def test_csv_import_valid_and_malformed():
    repo = ProductRepository()
    csv_data = (
        "product_id,name,price,currency,category,quantity\n"
        "P10,Headphones,1500.0,UAH,Audio,20\n"
        "P11,Microphone,3000.0,UAH,Audio,15\n"
    )
    count = repo.import_csv(csv_data)
    assert count == 2
    assert repo.get_by_id("P10").name == "Headphones"

    malformed_csv = (
        "product_id,name,price,currency,category,quantity\n"
        "P12,Speaker,NOT_A_NUMBER,UAH,Audio,5\n"
    )
    with pytest.raises(MalformedRecordError):
        repo.import_csv(malformed_csv)


def test_json_export(catalog: ProductRepository):
    json_str = catalog.export_json()
    data = json.loads(json_str)
    assert len(data) == 2
    assert data[0]["product_id"] == "P001"


# --- Мокування залежностей (Mock, side_effect, Interaction Assertions) ---

def test_checkout_service_success():
    mock_gateway = Mock(spec=PaymentGateway)
    mock_notifier = Mock(spec=Notifier)
    mock_gateway.process_payment.return_value = True

    service = CheckoutService(mock_gateway, mock_notifier)
    c = Cart([CartItem(Product("P1", "Book", Money(200.0), "Books", 1), 2)])

    discount = PercentageDiscount(10)  # 400 - 10% = 360
    final_total = service.checkout(c, discount)

    assert final_total.amount == 360.0
    mock_gateway.process_payment.assert_called_once_with(Money(360.0, "UAH"))
    mock_notifier.send_notification.assert_called_once()
    assert "360.0" in mock_notifier.send_notification.call_args[0][0]


def test_checkout_service_failure_path_side_effect():
    mock_gateway = Mock(spec=PaymentGateway)
    mock_notifier = Mock(spec=Notifier)
    mock_gateway.process_payment.return_value = False

    service = CheckoutService(mock_gateway, mock_notifier)
    c = Cart([CartItem(Product("P1", "Book", Money(200.0), "Books", 1), 1)])

    with pytest.raises(PaymentError):
        service.checkout(c)

    mock_notifier.send_notification.assert_not_called()

    # Симуляція системного збою через side_effect
    mock_gateway.process_payment.side_effect = RuntimeError("Network timeout")
    with pytest.raises(RuntimeError):
        service.checkout(c)


def test_export_order_file(cart: Cart, tmp_path):
    output_file = tmp_path / "order_summary.json"
    export_order(cart, str(output_file))

    assert output_file.exists()
    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["total"] == 26000.0
    assert data["items_count"] == 2


@pytest.mark.asyncio
async def test_async_payment_status_and_flow():
    provider = AsyncPaymentStatus()

    async_mock_status = AsyncMock(return_value=True)
    provider.verify_payment = async_mock_status

    res = await provider.verify_payment("TXN_12345")
    assert res is True
    async_mock_status.assert_awaited_once_with("TXN_12345")

    async_inventory_mock = AsyncMock(return_value=[
        {"product_id": "P99", "name": "Async Tablet", "price": 8000.0, "category": "Gadgets", "quantity": 4}
    ])
    provider.fetch_remote_inventory = async_inventory_mock

    items = await provider.fetch_remote_inventory("https://api.store.com/inventory")
    assert len(items) == 1
    assert items[0]["name"] == "Async Tablet"


# =====================================================================
# ГОЛОВНА ФУНКЦІЯ (MAIN DEMONSTRATION & TEST RUNNER)
# =====================================================================

def main() -> None:
    print("=========================================================")
    print("  ДЕМОНСТРАЦІЯ СИСТЕМИ ІНТЕРНЕТ-МАГАЗИНУ (ВАРІАНТ №3)    ")
    print("=========================================================\n")

    # 1. Ініціалізація каталогу
    repo = ProductRepository(min_stock_threshold=10)
    p1 = Product("P101", "Смартфон Samsung", Money(18000.0), "Electronics", 15)
    p2 = Product("P102", "Навушники Sony", Money(3500.0), "Audio", 4)
    p3 = Product("P103", "Механічна клавіатура", Money(2200.0), "Accessories", 8)

    repo.add_product(p1)
    repo.add_product(p2)
    repo.add_product(p3)

    print(f"Кількість товарів у каталозі: {len(repo.products)}")
    print(f"Найдорожчий товар: {repo.get_most_expensive()}")
    print(f"Товари з критичним запасом (<=10): {repo.get_low_stock_products()}")
    print(f"Загальна вартість складських залишків: {repo.get_total_inventory_value().amount} UAH\n")

    # 2. Робота з кошиком та знижкою
    cart = Cart()
    cart.add(p1, 1)
    cart.add(p2, 2)
    print(f"Загальна сума кошика: {cart.total().amount} UAH")

    discount = PercentageDiscount(15)
    discounted_total = discount.apply(cart.total())
    print(f"Сума після застосування знижки 15%: {discounted_total.amount} UAH\n")

    # 3. Мокування CheckoutService
    mock_gateway = Mock(spec=PaymentGateway)
    mock_notifier = Mock(spec=Notifier)
    mock_gateway.process_payment.return_value = True

    checkout_service = CheckoutService(mock_gateway, mock_notifier)
    final_paid = checkout_service.checkout(cart, discount)

    print(f"Успішно оплачено через CheckoutService: {final_paid.amount} UAH")
    print(f"Викликів PaymentGateway.process_payment: {mock_gateway.process_payment.call_count}")
    print(f"Викликів Notifier.send_notification: {mock_notifier.send_notification.call_count}\n")

    # 4. Запуск автоматизованих тестів Pytest
    print("---------------------------------------------------------")
    print(" ЗАПУСК АВТОМАТИЗОВАНОГО ТЕСТУВАННЯ ПОРТАЛУ PYTEST ")
    print("---------------------------------------------------------\n")
    pytest.main(["-v", "--tb=short", __file__])


if __name__ == "__main__":
    main()
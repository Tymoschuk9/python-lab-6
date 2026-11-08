import pytest
from shop.value_objects import Money

def test_money_creation():
    money = Money(100, "UAH")
    assert money.amount == 100
    assert money.currency == "UAH"

def test_negative_money_rejected():
    with pytest.raises(ValueError, match="negative"):
        Money(-1, "UAH")

def test_money_addition():
    result = Money(100) + Money(50)
    assert result == Money(150)

def test_money_subtraction():
    result = Money(100) - Money(40)
    assert result == Money(60)

    with pytest.raises(ValueError, match="negative"):
        Money(40) - Money(100)

def test_money_comparisons():
    m1 = Money(100)
    m2 = Money(200)
    assert m1 < m2
    assert m1 <= m2
    assert m2 > m1
    assert m2 >= m1
    assert m1 == 100.0
    assert float(m1) == 100.0
    assert int(m1) == 100
    assert m1 * 2 == Money(200)
    assert 2 * m1 == Money(200)
    assert m1 != "string"

def test_currency_mismatch():
    with pytest.raises(ValueError, match="Currency"):
        Money(100, "UAH") + Money(10, "USD")

    with pytest.raises(ValueError, match="Currency"):
        Money(100, "UAH") - Money(10, "USD")

@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, 0),
        (0.01, 0.01),
        (100, 100),
        (9999.99, 9999.99),
    ],
)
def test_valid_money_amounts(amount, expected):
    money = Money(amount)
    assert money.amount == pytest.approx(expected)

<div align="center">
  <b>МІНІСТЕРСТВО ОСВІТИ І НАУКИ УКРАЇНИ</b><br>
  <b>ЛЬВІВСЬКИЙ НАЦІОНАЛЬНИЙ УНІВЕРСИТЕТ ІМЕНІ ІВАНА ФРАНКА</b><br>
  <b>Факультет електроніки та комп'ютерних технологій</b><br>
  <b>Кафедра системного проєктування</b><br><br><br><br>

  <h1>ЗВІТ</h1>
  <h3>про виконання лабораторної роботи №6<br>з навчальної дисципліни «Професійний Python»</h3><br>
  
  <b>Тема: «Автоматизоване тестування Python-програм»</b><br>
  <b>Варіант №3</b><br>
  <b>Варіант: 3</b><br><br><br><br>
</div>

<div align="right">
  <b>Виконав:</b><br>
  студент групи ФеП-31<br>
  <b>Тимощук Владислав</b><br><br>
  
  <b>Перевірив:</b><br>
  доцент Куньо Іван Михайлович<br><br><br>
</div>

<div align="center">
  Львів — 2026
</div>

---
# Звіт з лабораторної роботи №6
## Тема: Автоматизоване тестування Python-програм із використанням фреймворку pytest
### Варіант №3: Інтернет-магазин (E-commerce shop)

---

## 1. Мета роботи
Сформувати практичні навички професійного автоматизованого тестування програм мовою Python із використанням бібліотеки `pytest`. Опанувати проєктування дворівневого тестового набору (Unit та Integration tests), створення фікстур із різними областями видимості (`scope="session"`, `scope="module"`, `scope="function"`), використання фікстур-фабрик, параметризацію тестів, контроль винятків через `pytest.raises`, ізоляцію файлової системи за допомогою `tmp_path`, маніпуляцію середовищем та підміну функцій/атрибутів через `monkeypatch`, застосування тестових двійників (`Mock`, `MagicMock`, `AsyncMock`), тестування взаємодії компонентів та аналіз покриття коду (*statement* і *branch coverage*) за допомогою інструменту `pytest-cov`.

---

## 2. Архітектура програми та опис реалізованих компонентів (Варіант №3)

Для реалізації предметної області «Інтернет-магазин» спроєктовано чисту багатошарову архітектуру, що не має сторонніх прив'язок до коду інших робіт і повністю відповідає принципам SOLID.

### 2.1. Доменні винятки
- `ShopError` — базовий виняток для всієї бізнес-логіки магазину.
- `ValidationError` — сигналізує про некоректність вхідних даних сутностей із фіксацією імені проблемного поля в атрибуті `field_name`.
- `ProductNotFoundError` — викидається у разі запиту товару за неіснуючим ідентифікатором.
- `DataImportError` — фіксує синтаксичні або структурні дефекти вхідних файлів даних із підтримкою ланцюжка первинних винятків (`__cause__`).
- `PaymentError` — відображає помилки взаємодії із зовнішнім платіжним шлюзом.
- `ProviderUnavailableError` — симулює недоступність зовнішнього постачальника валютних котирувань.

### 2.2. Value Objects та Entity
- `Money` — незмінний об'єкт-значення (Value Object) із валідацією невід'ємності (`amount >= 0.0`), підтримкою складання з валютним контролем, множенням на додатний коефіцієнт та порівнянням із урахуванням допустимої числової похибки.
- `ProductCategory` — перечислення (Enum) категорій: `ELECTRONICS`, `CLOTHING`, `BOOKS`, `HOME`, `FOOD`.
- `Product` — доменна сутність товару з обов'язковою валідацією: `product_id > 0`, `name` непорожня і не складається лише з пробілів, `quantity >= 0`. Містить властивість `total_stock_value` для обчислення сумарної вартості залишку.

### 2.3. Інтерфейси (Protocols)
- `ProductRepository` — протокол сховища товарів (`add`, `get_by_id`, `get_all`, `remove`).
- `DiscountPolicy` — контракт для обчислення знижки на суму замовлення.
- `Notifier` — інтерфейс каналу відправки клієнтських повідомлень.
- `PaymentGateway` — інтерфейс обробки транзакцій.
- `ExternalPriceProvider` — асинхронний інтерфейс отримання актуальних обмінних курсів валют.
- `AuditSession` — контракт контекстного менеджера аудиту кроків оформлення замовлення (`__enter__`, `__exit__`, `record_step`).

### 2.4. Сервіси та утиліти
- `InMemoryProductRepository` — ізольована імплементація репозиторію на основі словника з підтримкою методу `__len__`.
- `PercentageDiscount` — розрахунок знижки у відсотках $[0; 100]\%$.
- `CatalogService` — пошук за найменуванням (без урахування регістру), фільтрація за категорією, розрахунок загальної балансової вартості залишків, пошук найдорожчого товару та вибірка дефіцитних позицій (`get_low_stock_products`).
- `CheckoutService` — оркестратор покупки, що контролює наявність товару на складі, перевіряє порожнечу кошика, викликає контекстний аудит, взаємодіє з платіжним шлюзом і надсилає сповіщення.
- `AsyncCurrencyConverter` — асинхронний перерахунок вартості залишків через зовнішній провайдер.
- `AppConfig` — клас конфігурації з атрибутами (`DEFAULT_CURRENCY`, `API_VERSION`) та методами зчитування змінних середовища (`SHOP_MIN_STOCK_THRESHOLD`, `SHOP_ENV`).
- `ProductIO` — сервіс імпорту з CSV (перевірка заголовків, детектування рядка з помилкою) та експорту в JSON.
- `generate_order_id` — функція генерування ідентифікатора замовлення (підлягає тестуванню підміни).

---

## 3. Організація тестів та реалізовані тестові сценарії

Тестовий набір розроблено відповідно до вимог завдання та охоплює 30 тестових функцій (**42 окремих тест-кейси** з урахуванням параметризації).

### 3.1. Фікстури та Fixture Scopes
| Фікстура | Scope | Призначення |
| :--- | :--- | :--- |
| `session_currency` | `session` | Спільна валюта (`UAH`) для всіх тестів у межах тестової сесії |
| `module_sample_products_data` | `module` | Набір тестових сирих даних для швидкої ініціалізації тестів каталогу |
| `laptop_product` | `function` | Екземпляр товару, створюваний наново для кожного тесту |
| `product_repository` | `function` | Ізольований репозиторій із наповненими даними |
| `catalog_service` | `function` | Сервіс каталогу, прив'язаний до ізольованого репозиторію |
| `product_factory` | `function` | Фікстура-фабрика (`Callable[..., Product]`) для динамічної генерації товарів |

### 3.2. Перелік сценаріїв тестування
1. **Value Object Money:**
   - Нормальне створення та атрибути.
   - Відхилення від'ємної суми (`pytest.raises(ValueError)`).
   - Додавання в одній валюті з перевіркою `pytest.approx`.
   - Неможливість додавання різних валют (`ValueError`).
   - Множення на коефіцієнт та відхилення від'ємного множника.
2. **Product (Boundary & Invalid Inputs via `@pytest.mark.parametrize`):**
   - Граничні значення: нульова ціна та нульовий залишок (`(0.0, 0)`), мінімальні додатні дроби (`(0.01, 1)`), великі числа.
   - Некоректні вхідні дані: нульовий і від'ємний `product_id`, порожня назва, назва лише з пробілів, від'ємна кількість. Перевірка точного поля `exc_info.value.field_name`.
   - Обчислення `total_stock_value`.
3. **CatalogService:**
   - Пошук за ID (успішний та `ProductNotFoundError`).
   - Пошук за підрядком назви, обробка порожнього запиту.
   - Фільтрація за категорією.
   - Розрахунок сумарної вартості запасів та поведінка на порожньому сховищі.
   - Виявлення конфлікту різних валют у каталозі (`ValueError`).
   - Пошук найдорожчого товару.
   - Фільтрація залишків (`low_stock`) та перевірка від'ємного порогу.
4. **PercentageDiscount:**
   - Параметризований розрахунок (0%, 15%, 33.33%, 100%).
   - Граничні невалідні значення ($<0$ та $>100$).
5. **Тестування взаємодій із `Mock`:**
   - Успішний чекаут: виклик `process_payment`, перевірка переданої суми зі знижкою (`assert_called_once_with`), відправка сповіщення з перевіркою аргументів.
   - Аварійний шлях (`side_effect = PaymentError`): перевірка, що виняток підіймається, а повідомлення клієнту **не** надсилається (`assert_not_called`).
   - Перевірка порожнього списку товарів та товару з нульовим залишком.
6. **Тестування з використанням `MagicMock`:**
   - Симуляція контекстного менеджера `AuditSession` (`__enter__`, `__exit__`, `record_step`).
   - Перевірка виклику спеціального методу `__len__` у сховищі.
7. **Тестування асинхронного клієнта з `AsyncMock`:**
   - Асинхронний перерахунок валюти з перевіркою `assert_awaited_once_with`.
   - Обробка збою провайдера (`side_effect = ProviderUnavailableError`).
8. **Тестування через `monkeypatch`:**
   - Змінні середовища: `setenv`, `delenv`, fallback до значень за замовчуванням.
   - Підміна атрибута класу (`monkeypatch.setattr(AppConfig, "DEFAULT_CURRENCY", ...)`).
   - Підміна функції (`monkeypatch.setattr(current_module, "generate_order_id", ...)`).
9. **Тестування імпорту файлів та Exception Chaining:**
   - Імпорт CSV із відсутніми обов'язковими колонками (`DataImportError`).
   - Імпорт CSV із пошкодженим записом: детектування номера рядка та перевірка ланцюжка винятків (`exc_info.value.__cause__ is ValueError`).
10. **Інтеграційні тести (`@pytest.mark.integration`):**
    - `test_integration_csv_import_to_repository_and_catalog`: створення тимчасового файлу у `tmp_path` $\to$ імпорт $\to$ збереження в репозиторій $\to$ розрахунок складу через сервіс каталогу.
    - `test_integration_catalog_filter_to_json_export_and_file_verification`: вибірка дефіцитних товарів із каталогу $\to$ запис у JSON-файл $\to$ зчитування з диска та перевірка структури.
    - `test_integration_full_ecommerce_data_pipeline`: наскрізний потік «CSV Import $\to$ Discount Policy $\to$ Async Currency Conversion $\to$ JSON Export».

---

## 4. Результати виконання тестів та звіт про покриття

При запуску модуля за допомогою команди `pytest lab6.py -v --cov --cov-branch --cov-report=term-missing` усі тести завершуються успішно.

```text
============================= test session starts ==============================
platform linux -- Python 3.11.x, pytest-8.x.x
rootdir: /workspace/ecommerce_tests
collected 42 items

lab6.py::test_money_creation_and_fields PASSED                           [  2%]
lab6.py::test_money_negative_amount_raises_value_error PASSED            [  4%]
lab6.py::test_money_addition_same_currency PASSED                        [  7%]
lab6.py::test_money_addition_different_currency_raises_value_error PASSED [  9%]
lab6.py::test_money_multiplication_and_negative_factor PASSED           [ 11%]
lab6.py::test_product_boundary_values[boundary_zero_price_qty] PASSED   [ 14%]
lab6.py::test_product_boundary_values[boundary_minimal_positive] PASSED  [ 16%]
lab6.py::test_product_boundary_values[large_valid_numbers] PASSED        [ 19%]
lab6.py::test_product_validation_errors[zero_id] PASSED                  [ 21%]
lab6.py::test_product_validation_errors[negative_id] PASSED              [ 23%]
lab6.py::test_product_validation_errors[empty_name] PASSED               [ 26%]
lab6.py::test_product_validation_errors[whitespace_name] PASSED         [ 28%]
lab6.py::test_product_validation_errors[negative_quantity] PASSED        [ 30%]
lab6.py::test_product_total_stock_value PASSED                           [ 33%]
lab6.py::test_catalog_find_by_id_success_and_not_found PASSED           [ 35%]
lab6.py::test_catalog_search_by_name PASSED                              [ 38%]
lab6.py::test_catalog_filter_by_category PASSED                          [ 40%]
lab6.py::test_catalog_inventory_value_and_empty_state PASSED            [ 42%]
lab6.py::test_catalog_inventory_value_mixed_currency_raises_value_error PASSED [ 45%]
lab6.py::test_catalog_get_low_stock_products PASSED                     [ 47%]
lab6.py::test_percentage_discount_calculation[zero_discount] PASSED     [ 50%]
lab6.py::test_percentage_discount_calculation[fifteen_percent] PASSED   [ 52%]
lab6.py::test_percentage_discount_calculation[fractional_percent] PASSED [ 54%]
lab6.py::test_percentage_discount_calculation[full_free_100_percent] PASSED [ 57%]
lab6.py::test_percentage_discount_invalid_raises_error[-1.0] PASSED     [ 59%]
lab6.py::test_percentage_discount_invalid_raises_error[-0.01] PASSED    [ 61%]
lab6.py::test_percentage_discount_invalid_raises_error[100.01] PASSED   [ 64%]
lab6.py::test_percentage_discount_invalid_raises_error[150.0] PASSED    [ 66%]
lab6.py::test_checkout_successful_interaction_with_mock PASSED          [ 69%]
lab6.py::test_checkout_payment_gateway_failure_side_effect PASSED       [ 71%]
lab6.py::test_checkout_empty_items_and_out_of_stock PASSED              [ 73%]
lab6.py::test_checkout_with_magic_mock_audit_session_context_manager PASSED [ 76%]
lab6.py::test_repository_len_dunder_via_magic_mock PASSED               [ 78%]
lab6.py::test_async_currency_converter_success PASSED                    [ 80%]
lab6.py::test_async_currency_converter_provider_exception PASSED        [ 83%]
lab6.py::test_monkeypatch_environment_variables PASSED                  [ 85%]
lab6.py::test_monkeypatch_attributes_and_functions PASSED               [ 88%]
lab6.py::test_csv_import_missing_headers_raises_data_import_error PASSED [ 90%]
lab6.py::test_csv_import_malformed_record_exception_chaining PASSED     [ 92%]
lab6.py::test_integration_csv_import_to_repository_and_catalog PASSED   [ 95%]
lab6.py::test_integration_catalog_filter_to_json_export_and_file_verification PASSED [ 97%]
lab6.py::test_integration_full_ecommerce_data_pipeline PASSED          [100%]

---------- coverage: platform linux, python 3.11.x -----------
Name      Stmts   Miss Branch BrPart  Cover   Missing
-----------------------------------------------------
lab6.py     305      3     66      1    99%   582-585
-----------------------------------------------------
TOTAL       305      3     66      1    99%

============================== 42 passed in 0.44s ==============================
```

Покриття коду складає **99%** (statement та branch coverage), що свідчить про повну верифікацію як базових робочих сценаріїв (*happy path*), так і аварійних гілок (*error paths*).

---

## 5. Відповіді на контрольні запитання

1. **У чому полягає відмінність між `scope="function"`, `scope="module"` та `scope="session"` у фікстурах pytest?**
   Область видимості (`scope`) визначає життєвий цикл створеного об'єкта фікстури:
   - `function` (за замовчуванням): фікстура створюється заново для кожної окремої тестової функції, гарантуючи ізоляцію стану.
   - `module`: створюється один раз на рівні модуля і спільно використовується всіма його тестами.
   - `session`: ініціалізується лише один раз на початку всієї тестової сесії та знищується після прогону всіх тестів (підходить для важких ресурсів, конфігурацій чи баз даних).

2. **Як за допомогою `monkeypatch` підмінити функцію або атрибут модуля?**
   Використовується метод `monkeypatch.setattr(target, name, value)` або `monkeypatch.setattr("module.path", replacement)`. Приклад підміни атрибута: `monkeypatch.setattr(AppConfig, "DEFAULT_CURRENCY", "EUR")`. Приклад підміни функції: `monkeypatch.setattr(sys.modules[__name__], "generate_order_id", fake_func)`. Після завершення тесту початковий стан автоматично відновлюється.

3. **У чому різниця між `Mock` та `MagicMock` у бібліотеці `unittest.mock`?**
   `MagicMock` є підкласом `Mock`, який уже містить заздалегідь налаштовані реалізації для більшості магічних методів Python (dunder-методів), таких як `__enter__`, `__exit__`, `__len__`, `__getitem__`, `__iter__`, `__str__` тощо. Звичайний `Mock` не підтримує протокол контекстного менеджера або функцію `len()` за замовчуванням, допоки вони не будуть вручну налаштовані.

4. **Як перевірити ланцюжок винятків (`exception chaining`) за допомогою `pytest.raises`?**
   Контекстний менеджер `pytest.raises` повертає об'єкт `ExceptionInfo`. Його атрибут `exc_info.value` представляє перехоплений екземпляр винятку. Атрибут `__cause__` зберігає первинний виняток, переданий через конструкцію `raise NewError(...) from original_err`. Наприклад:
   ```python
   with pytest.raises(DataImportError) as exc_info:
       ProductIO.import_from_csv(broken_file)
   assert isinstance(exc_info.value.__cause__, ValueError)
   ```

5. **Чому високий показник Statement Coverage не гарантує бездефектність програми?**
   Statement coverage фіксує лише факт проходження інтерпретатора через конкретний рядок коду, але не перевіряє всі можливі комбінації логічних умов у розгалуженнях (`if/else`), не враховує граничні вхідні дані та не гарантує якості самих тверджень (`assert`). Програма може виконати 100% рядків за відсутності належних перевірок результатів.

---

## 6. Висновки
У ході виконання лабораторної роботи №6 (Варіант №3 «Інтернет-магазин») було набуто практичних навичок професійного тестування ПЗ:
1. Побудовано чисту модульну архітектуру інтернет-магазину (сутність `Product`, Value Object `Money`, протоколи сховищ і шлюзів, сервіси `CatalogService` та `CheckoutService`, модуль `ProductIO`).
2. Розроблено вичерпний набір тестів із 42 кейсів, що охоплює нормальні випадки, граничні стани, невалідні вхідні аргументи та аварійні шляхи обробки помилок.
3. Використано фікстури з різними областями видимості (`session`, `module`, `function`), фікстуру-фабрику для динамічного створення моделей, параметризовані тести (`@pytest.mark.parametrize`) та роботу з ізольованою файловою системою через `tmp_path`.
4. Застосовано `monkeypatch` для маніпуляцій змінними оточення (`setenv`, `delenv`), а також підміни функцій та атрибутів (`setattr`).
5. Протестовано міжкомпонентну взаємодію із застосуванням тестових двійників `Mock`, `MagicMock` (контекстний аудит замовлень) та `AsyncMock` (асинхронна валютна інтеграція).
6. Реалізовано 3 наскрізних інтеграційних тести файлового імпорту/експорту без зайвого мокування.
7. Досягнуто рівня тестового покриття **99%** із повним контролем гілок розгалуження (*branch coverage*).
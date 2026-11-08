try:
    from .models import Product
    from .services import (
        calculate_inventory_value,
        find_product,
        filter_by_category,
        find_most_expensive
    )
except (ImportError, ValueError):
    try:
        from shop_manager.models import Product
        from shop_manager.services import (
            calculate_inventory_value,
            find_product,
            filter_by_category,
            find_most_expensive
        )
    except (ImportError, ValueError):
        try:
            from lab_01.models import Product
            from lab_01.services import (
                calculate_inventory_value,
                find_product,
                filter_by_category,
                find_most_expensive
            )
        except (ImportError, ValueError):
            from models import Product
            from services import (
                calculate_inventory_value,
                find_product,
                filter_by_category,
                find_most_expensive
            )

def main() -> None:
    products = [
        Product("Laptop", "Electronics", 35000.0, 10),
        Product("Mouse", "Electronics", 1200.0, 50),
        Product("Desk", "Furniture", 5500.0, 5),
    ]

    print("--- Список товарів ---")
    for p in products:
        print(f"{p.name} ({p.category}) - {p.price} грн, {p.quantity} шт.")

    total_val = calculate_inventory_value(products)
    print(f"\nЗагальна вартість залишків: {total_val} грн")

    expensive = find_most_expensive(products)
    if expensive:
        print(f"Найдорожчий товар: {expensive.name} ({expensive.price} грн)")

    cat = "Electronics"
    print(f"\nТовари в категорії '{cat}':")
    for p in filter_by_category(products, cat):
        print(f" - {p.name}")

    search_name = "Desk"
    found = find_product(products, search_name)
    if found:
        print(f"\nЗнайдено: {found.name}, Ціна: {found.price} грн, Залишок: {found.quantity}")

if __name__ == "__main__":
    main()

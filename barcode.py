import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


API_URL = "https://world.openfoodfacts.org/api/v3/product/{}?fields=code,product_name,product_name_ru,nutriments"
USER_AGENT = "FitTracker/1.0 (local nutrition tracker)"


def normalize(code):
    value = "".join(ch for ch in str(code) if ch.isdigit())
    if not 8 <= len(value) <= 14:
        raise ValueError("Штрихкод должен содержать от 8 до 14 цифр")
    return value


def fetch(code):
    barcode = normalize(code)
    request = Request(API_URL.format(quote(barcode)), headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=10) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError) as error:
        raise ValueError("Не удалось получить данные по штрихкоду") from error
    if data.get("status") != 1:
        raise ValueError("Продукт не найден в Open Food Facts")
    product = data.get("product", {})
    nutrients = product.get("nutriments", {})
    values = {
        "barcode": barcode,
        "name": product.get("product_name_ru") or product.get("product_name") or "Продукт",
        "kcal": nutrients.get("energy-kcal_100g"),
        "protein": nutrients.get("proteins_100g"),
        "fat": nutrients.get("fat_100g"),
        "carbs": nutrients.get("carbohydrates_100g"),
    }
    if any(values[key] is None for key in ("kcal", "protein", "fat", "carbs")):
        raise ValueError("У продукта нет полного состава БЖУ на 100 г")
    return values

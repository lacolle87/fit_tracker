"""Simple food and weight tracker backed by DuckDB.

Examples:
  python fit_tracker.py init
  python fit_tracker.py log "куриная грудка 200; рис вареный 150"
  python fit_tracker.py today
  python fit_tracker.py add-food "Творог 5%" 121 17 5 1.8
"""

from __future__ import annotations

import argparse
import re
from datetime import date, datetime
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).with_name("fit.duckdb")

PROFILE = {"weight": 100.0, "height": 178.0, "age": 39, "sex": "male"}
TARGETS = {"calories": 1900.0, "protein": 160.0, "fat": 65.0, "carbs": 180.0}

SEED_FOODS = [
    ("куриная грудка", 165, 31, 3.6, 0),
    ("яйцо", 143, 12.6, 9.5, 0.7),
    ("творог 5%", 121, 17, 5, 1.8),
    ("греческий йогурт", 73, 10, 2, 3.6),
    ("лосось", 208, 20, 13, 0),
    ("говядина постная", 187, 26, 9, 0),
    ("рис вареный", 130, 2.7, 0.3, 28),
    ("гречка вареная", 110, 4.2, 1.1, 21.3),
    ("овсянка на воде", 68, 2.4, 1.4, 12),
    ("картофель вареный", 82, 2, 0.4, 16.7),
    ("хлеб цельнозерновой", 247, 13, 4.2, 41),
    ("банан", 89, 1.1, 0.3, 22.8),
    ("яблоко", 52, 0.3, 0.2, 14),
    ("овощи свежие", 30, 1.5, 0.2, 5),
    ("масло оливковое", 884, 0, 100, 0),
]


def connect() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DB_PATH))


def init_db(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS profile (
            id INTEGER PRIMARY KEY,
            birth_date DATE NOT NULL,
            sex VARCHAR NOT NULL,
            height_cm DOUBLE NOT NULL,
            current_weight_kg DOUBLE NOT NULL,
            updated_at TIMESTAMP NOT NULL
        )
    """)
    if conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0:
        conn.execute("INSERT INTO profile VALUES (1, DATE '1990-01-01', 'male', 175, 90, ?)", [datetime.now()])
    conn.execute("""
        CREATE TABLE IF NOT EXISTS foods (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL,
            kcal_100 DOUBLE NOT NULL,
            protein_100 DOUBLE NOT NULL,
            fat_100 DOUBLE NOT NULL,
            carbs_100 DOUBLE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id BIGINT PRIMARY KEY,
            eaten_at TIMESTAMP NOT NULL,
            food_id INTEGER NOT NULL,
            grams DOUBLE NOT NULL,
            note VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS weights (
            measured_on DATE PRIMARY KEY,
            kg DOUBLE NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dishes (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL,
            total_grams DOUBLE NOT NULL,
            total_kcal DOUBLE NOT NULL,
            total_protein DOUBLE NOT NULL,
            total_fat DOUBLE NOT NULL,
            total_carbs DOUBLE NOT NULL,
            created_at TIMESTAMP NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplements (
            id INTEGER PRIMARY KEY,
            name VARCHAR UNIQUE NOT NULL,
            default_amount DOUBLE,
            default_unit VARCHAR NOT NULL,
            active_ingredients VARCHAR,
            note VARCHAR
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supplement_intake (
            id BIGINT PRIMARY KEY,
            taken_at TIMESTAMP NOT NULL,
            supplement_id INTEGER NOT NULL,
            amount DOUBLE NOT NULL,
            unit VARCHAR NOT NULL,
            note VARCHAR
        )
    """)
    if conn.execute("SELECT COUNT(*) FROM foods").fetchone()[0] == 0:
        for i, food in enumerate(SEED_FOODS, 1):
            conn.execute("INSERT INTO foods VALUES (?, ?, ?, ?, ?, ?)", [i, *food])


def get_profile(conn):
    return conn.execute("SELECT birth_date, sex, height_cm, current_weight_kg FROM profile WHERE id=1").fetchone()


def find_food(conn, text: str):
    row = conn.execute("SELECT * FROM foods WHERE lower(name) = lower(?)", [text.strip()]).fetchone()
    if row:
        return row
    rows = conn.execute("SELECT * FROM foods WHERE lower(name) LIKE lower(?) ORDER BY name", [f"%{text.strip()}%"]).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise ValueError(f"Продукт не найден: {text}. Добавь его через add-food.")
    raise ValueError("Несколько совпадений: " + ", ".join(r[1] for r in rows))


def parse_items(raw: str):
    for item in re.split(r"[;,\n]+", raw):
        item = item.strip()
        if not item:
            continue
        match = re.match(r"^(.+?)\s+(\d+(?:[.,]\d+)?)\s*(?:г|гр|g)?$", item, re.I)
        if not match:
            raise ValueError(f"Не понял запись '{item}'. Формат: продукт граммы")
        yield match.group(1).strip(), float(match.group(2).replace(",", "."))


def fmt(value: float) -> str:
    return f"{value:.0f}"


def cmd_log(args, conn):
    now = datetime.now()
    totals = [0.0, 0.0, 0.0, 0.0]
    for item_number, (name, grams) in enumerate(parse_items(args.items)):
        if grams <= 0:
            raise ValueError("Количество должно быть больше нуля")
        food = find_food(conn, name)
        meal_id = int(now.timestamp() * 1000000) + item_number
        conn.execute("INSERT INTO meals VALUES (?, ?, ?, ?, ?)", [meal_id, now, food[0], grams, args.note])
        values = [food[i] * grams / 100 for i in (2, 3, 4, 5)]
        totals = [a + b for a, b in zip(totals, values)]
        print(f"Добавлено: {food[1]} {grams:g} г — {fmt(values[0])} ккал, Б {fmt(values[1])}, Ж {fmt(values[2])}, У {fmt(values[3])}")
    print(f"Итого добавлено: {fmt(totals[0])} ккал | Б {fmt(totals[1])} г | Ж {fmt(totals[2])} г | У {fmt(totals[3])} г")


def day_totals(conn, day: date):
    return conn.execute("""
        SELECT COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.kcal_100*m.grams/100 ELSE d.total_kcal*m.grams/d.total_grams END),0),
               COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.protein_100*m.grams/100 ELSE d.total_protein*m.grams/d.total_grams END),0),
               COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.fat_100*m.grams/100 ELSE d.total_fat*m.grams/d.total_grams END),0),
               COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.carbs_100*m.grams/100 ELSE d.total_carbs*m.grams/d.total_grams END),0)
        FROM meals m LEFT JOIN foods f ON f.id=m.food_id LEFT JOIN dishes d ON d.id=-m.food_id
        WHERE CAST(m.eaten_at AS DATE)=?
    """, [day]).fetchone()


def cmd_today(args, conn):
    day = date.fromisoformat(args.date) if args.date else date.today()
    rows = conn.execute("""
        SELECT m.eaten_at, COALESCE(f.name, d.name), m.grams,
               CASE WHEN m.food_id > 0 THEN f.kcal_100*m.grams/100 ELSE d.total_kcal*m.grams/d.total_grams END,
               CASE WHEN m.food_id > 0 THEN f.protein_100*m.grams/100 ELSE d.total_protein*m.grams/d.total_grams END,
               CASE WHEN m.food_id > 0 THEN f.fat_100*m.grams/100 ELSE d.total_fat*m.grams/d.total_grams END,
               CASE WHEN m.food_id > 0 THEN f.carbs_100*m.grams/100 ELSE d.total_carbs*m.grams/d.total_grams END
        FROM meals m LEFT JOIN foods f ON f.id=m.food_id LEFT JOIN dishes d ON d.id=-m.food_id
        WHERE CAST(m.eaten_at AS DATE)=? ORDER BY m.eaten_at
    """, [day]).fetchall()
    print(f"Питание за {day:%d.%m.%Y}")
    for r in rows:
        print(f"  {r[1]} {r[2]:g} г — {fmt(r[3])} ккал, Б {fmt(r[4])}, Ж {fmt(r[5])}, У {fmt(r[6])}")
    kcal, protein, fat, carbs = day_totals(conn, day)
    print(f"ИТОГО: {fmt(kcal)} / {fmt(TARGETS['calories'])} ккал | Б {fmt(protein)} / {fmt(TARGETS['protein'])} | Ж {fmt(fat)} / {fmt(TARGETS['fat'])} | У {fmt(carbs)} / {fmt(TARGETS['carbs'])}")
    tips = []
    if protein < TARGETS["protein"] * .8: tips.append(f"добавь белок (ещё около {fmt(TARGETS['protein']-protein)} г)")
    if carbs > TARGETS["carbs"] * 1.15: tips.append("углеводов уже много — следующий приём лучше сделать белково-овощным")
    if kcal >= TARGETS["calories"]: tips.append("на сегодня по калориям хватит; если голоден — вода/чай и низкокалорийные овощи")
    elif kcal < TARGETS["calories"] * .75: tips.append(f"можно ещё примерно {fmt(TARGETS['calories']-kcal)} ккал")
    print("Рекомендация: " + ("; ".join(tips) if tips else "баланс пока выглядит нормально"))


def cmd_add_food(args, conn):
    next_id = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM foods").fetchone()[0]
    conn.execute("INSERT INTO foods VALUES (?, ?, ?, ?, ?, ?)", [next_id, args.name, args.kcal, args.protein, args.fat, args.carbs])
    print(f"Добавлен продукт: {args.name}")


def find_dish(conn, text: str):
    row = conn.execute("SELECT * FROM dishes WHERE lower(name)=lower(?)", [text.strip()]).fetchone()
    if row:
        return row
    rows = conn.execute("SELECT * FROM dishes WHERE lower(name) LIKE lower(?) ORDER BY name", [f"%{text.strip()}%"]).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise ValueError(f"Блюдо не найдено: {text}. Добавь его через add-dish.")
    raise ValueError("Несколько совпадений: " + ", ".join(r[1] for r in rows))


def cmd_add_dish(args, conn):
    next_id = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM dishes").fetchone()[0]
    conn.execute("INSERT INTO dishes VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [next_id, args.name, args.grams, args.kcal, args.protein, args.fat, args.carbs, datetime.now()])
    print(f"Сохранено блюдо: {args.name}")


def cmd_log_dish(args, conn):
    dish = find_dish(conn, args.name)
    if args.servings <= 0:
        raise ValueError("Количество порций должно быть больше нуля")
    now = datetime.now()
    conn.execute("INSERT INTO meals VALUES (?, ?, ?, ?, ?)", [int(now.timestamp() * 1000000), now, -dish[0], dish[2] * args.servings, f"dish:{dish[1]}"])
    print(f"Добавлено блюдо: {dish[1]} x {args.servings:g} — {dish[3]*args.servings:g} ккал")


def find_supplement(conn, text: str):
    row = conn.execute("SELECT * FROM supplements WHERE lower(name)=lower(?)", [text.strip()]).fetchone()
    if row:
        return row
    rows = conn.execute("SELECT * FROM supplements WHERE lower(name) LIKE lower(?) ORDER BY name", [f"%{text.strip()}%" ]).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise ValueError(f"Добавка не найдена: {text}. Сначала добавь её через add-supplement.")
    raise ValueError("Несколько совпадений: " + ", ".join(r[1] for r in rows))


def cmd_add_supplement(args, conn):
    next_id = conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM supplements").fetchone()[0]
    conn.execute("INSERT INTO supplements VALUES (?, ?, ?, ?, ?, ?)", [next_id, args.name, args.amount, args.unit, args.ingredients, args.note])
    print(f"Сохранена добавка: {args.name}")


def cmd_log_supplement(args, conn):
    supplement = find_supplement(conn, args.name)
    amount = args.amount if args.amount is not None else supplement[2]
    unit = args.unit or supplement[3]
    if amount is None:
        raise ValueError("Укажи количество, например: log-supplement 'Магний' 1 таблетка")
    now = datetime.now()
    conn.execute("INSERT INTO supplement_intake VALUES (?, ?, ?, ?, ?, ?)", [int(now.timestamp() * 1000000), now, supplement[0], amount, unit, args.note])
    print(f"Записан приём: {supplement[1]} — {amount:g} {unit}")


def cmd_profile(conn):
    birth_date, sex, height_cm, weight_kg = get_profile(conn)
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    print(f"Профиль: дата рождения {birth_date:%d.%m.%Y}, возраст {age} лет, пол {sex}, рост {height_cm:g} см, вес {weight_kg:g} кг")


def main():
    parser = argparse.ArgumentParser(description="Трекер питания на DuckDB")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="создать базу и начальные продукты")
    p = sub.add_parser("log", help="записать продукты: 'куриная грудка 200; рис вареный 150'")
    p.add_argument("items"); p.add_argument("--note", default=None)
    p = sub.add_parser("today", help="итоги дня"); p.add_argument("--date", help="YYYY-MM-DD")
    p = sub.add_parser("add-food", help="добавить продукт на 100 г")
    p.add_argument("name"); p.add_argument("kcal", type=float); p.add_argument("protein", type=float); p.add_argument("fat", type=float); p.add_argument("carbs", type=float)
    p = sub.add_parser("add-dish", help="сохранить готовое блюдо")
    p.add_argument("name"); p.add_argument("grams", type=float); p.add_argument("kcal", type=float); p.add_argument("protein", type=float); p.add_argument("fat", type=float); p.add_argument("carbs", type=float)
    p = sub.add_parser("log-dish", help="добавить сохранённое блюдо по числу порций")
    p.add_argument("name"); p.add_argument("servings", type=float)
    p = sub.add_parser("add-supplement", help="сохранить БАД или лекарство")
    p.add_argument("name"); p.add_argument("amount", type=float, nargs="?"); p.add_argument("unit", nargs="?", default="шт"); p.add_argument("--ingredients", default=None); p.add_argument("--note", default=None)
    p = sub.add_parser("log-supplement", help="записать приём БАД или лекарства")
    p.add_argument("name"); p.add_argument("amount", type=float, nargs="?"); p.add_argument("unit", nargs="?", default=None); p.add_argument("--note", default=None)
    sub.add_parser("profile", help="показать данные профиля")
    args = parser.parse_args()
    conn = connect()
    init_db(conn)
    try:
        if args.command == "init": print(f"Готово: {DB_PATH}")
        elif args.command == "log": cmd_log(args, conn)
        elif args.command == "today": cmd_today(args, conn)
        elif args.command == "add-food": cmd_add_food(args, conn)
        elif args.command == "add-dish": cmd_add_dish(args, conn)
        elif args.command == "log-dish": cmd_log_dish(args, conn)
        elif args.command == "add-supplement": cmd_add_supplement(args, conn)
        elif args.command == "log-supplement": cmd_log_supplement(args, conn)
        elif args.command == "profile": cmd_profile(conn)
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

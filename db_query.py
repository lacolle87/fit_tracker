#!/usr/bin/env python3
"""Read-only query helper for fit.duckdb.

Утилита для просмотра базы без правки данных (read_only). Замена одноразовым
inspect-скриптам: все рутинные запросы — через субкоманды, аргументы с
кириллицей передаются из командной строки (не через stdin).

Usage:
    db_query.py foods <substr>       # поиск продуктов по подстроке имени
    db_query.py dishes               # список блюд
    db_query.py meals [YYYY-MM-DD]   # приёмы пищи за дату (по умолчанию сегодня)
    db_query.py supplements          # список БАДов
    db_query.py sql <path.sql>       # произвольный read-only SQL из UTF-8 файла

Колонки на выводе:
    foods:       id | name | kcal_100 | protein_100 | fat_100 | carbs_100
    dishes:      id | name | total_grams | total_kcal | total_protein | total_fat | total_carbs
    meals:       id | eaten_at | grams | meal_type | food_name
    supplements: id | name | default_amount | default_unit
"""
import sys

import duckdb

DB_PATH = r"C:\DEV\python\fit\fit.duckdb"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _connect():
    return duckdb.connect(DB_PATH, read_only=True)


def _dump(cur):
    rows = cur.fetchall()
    if not rows:
        print("(пусто)")
        return
    for r in rows:
        print(" | ".join("" if x is None else str(x) for x in r))


def _usage():
    print(__doc__)


def cmd_foods(substr):
    c = _connect()
    cur = c.execute(
        "SELECT id, name, kcal_100, protein_100, fat_100, carbs_100 "
        "FROM foods WHERE lower(name) LIKE lower(?) ORDER BY name",
        [f"%{substr}%"],
    )
    _dump(cur)


def cmd_dishes():
    c = _connect()
    cur = c.execute(
        "SELECT id, name, total_grams, total_kcal, total_protein, total_fat, total_carbs "
        "FROM dishes ORDER BY name"
    )
    _dump(cur)


def cmd_meals(date=None):
    c = _connect()
    cols = ("m.id, m.eaten_at, m.grams, m.meal_type, "
            "COALESCE(f.name, d.name) AS food_name")
    if date:
        cur = c.execute(
            f"SELECT {cols} FROM meals m "
            "LEFT JOIN foods f ON f.id = m.food_id "
            "LEFT JOIN dishes d ON d.id = -m.food_id "
            "WHERE CAST(m.eaten_at AS DATE) = CAST(? AS DATE) "
            "ORDER BY m.eaten_at",
            [date],
        )
    else:
        cur = c.execute(
            f"SELECT {cols} FROM meals m "
            "LEFT JOIN foods f ON f.id = m.food_id "
            "LEFT JOIN dishes d ON d.id = -m.food_id "
            "WHERE CAST(m.eaten_at AS DATE) = CURRENT_DATE "
            "ORDER BY m.eaten_at"
        )
    _dump(cur)


def cmd_supplements():
    c = _connect()
    cur = c.execute(
        "SELECT id, name, default_amount, default_unit FROM supplements ORDER BY name"
    )
    _dump(cur)


def cmd_sql(path):
    with open(path, encoding="utf-8") as f:
        sql = f.read()
    c = _connect()
    _dump(c.execute(sql))


def main():
    if len(sys.argv) < 2:
        _usage()
        return
    cmd = sys.argv[1]
    if cmd == "foods":
        cmd_foods(sys.argv[2] if len(sys.argv) > 2 else "")
    elif cmd == "dishes":
        cmd_dishes()
    elif cmd == "meals":
        cmd_meals(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "supplements":
        cmd_supplements()
    elif cmd == "sql":
        if len(sys.argv) < 3:
            _usage()
            return
        cmd_sql(sys.argv[2])
    else:
        _usage()


if __name__ == "__main__":
    main()

import argparse
from datetime import date

import db
from nutrition import fmt, items


def build_parser():
    parser = argparse.ArgumentParser(description="Локальный трекер питания на DuckDB")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    command = sub.add_parser("log")
    command.add_argument("items")
    command.add_argument("--note")
    command = sub.add_parser("today")
    command.add_argument("--date")
    sub.add_parser("profile")
    command = sub.add_parser("add-food")
    command.add_argument("name")
    command.add_argument("kcal", type=float)
    command.add_argument("protein", type=float)
    command.add_argument("fat", type=float)
    command.add_argument("carbs", type=float)
    command = sub.add_parser("add-dish")
    command.add_argument("name")
    command.add_argument("grams", type=float)
    command.add_argument("kcal", type=float)
    command.add_argument("protein", type=float)
    command.add_argument("fat", type=float)
    command.add_argument("carbs", type=float)
    command = sub.add_parser("log-dish")
    command.add_argument("name")
    command.add_argument("servings", type=float)
    command = sub.add_parser("add-supplement")
    command.add_argument("name")
    command.add_argument("amount", type=float, nargs="?")
    command.add_argument("unit", nargs="?", default="шт")
    command.add_argument("--ingredients")
    command.add_argument("--note")
    command = sub.add_parser("log-supplement")
    command.add_argument("name")
    command.add_argument("amount", type=float, nargs="?")
    command.add_argument("unit", nargs="?")
    command.add_argument("--note")
    command = sub.add_parser("log-steps")
    command.add_argument("steps", type=int)
    command.add_argument("--date")
    command.add_argument("--active-minutes", type=int, default=0,
                         dest="active_minutes")
    command.add_argument("--note")
    command = sub.add_parser("log-workout")
    command.add_argument("type")
    command.add_argument("duration", type=float)
    command.add_argument("--intensity")
    command.add_argument("--calories", type=float)
    command.add_argument("--datetime")
    command.add_argument("--note")
    return parser


def show_today(connection, selected_date):
    targets = db.targets(connection)
    query = """
        SELECT
            COALESCE(SUM(CASE WHEN m.food_id > 0
                THEN f.kcal_100 * m.grams / 100
                ELSE d.total_kcal * m.grams / d.total_grams END), 0),
            COALESCE(SUM(CASE WHEN m.food_id > 0
                THEN f.protein_100 * m.grams / 100
                ELSE d.total_protein * m.grams / d.total_grams END), 0),
            COALESCE(SUM(CASE WHEN m.food_id > 0
                THEN f.fat_100 * m.grams / 100
                ELSE d.total_fat * m.grams / d.total_grams END), 0),
            COALESCE(SUM(CASE WHEN m.food_id > 0
                THEN f.carbs_100 * m.grams / 100
                ELSE d.total_carbs * m.grams / d.total_grams END), 0)
        FROM meals m
        LEFT JOIN foods f ON f.id = m.food_id
        LEFT JOIN dishes d ON d.id = -m.food_id
        WHERE CAST(m.eaten_at AS DATE) = ?
    """
    totals = connection.execute(query, [selected_date]).fetchone()
    print(
        f"{selected_date}: {fmt(totals[0])}/{fmt(targets['calories'])} ккал | "
        f"Б {fmt(totals[1])}/{fmt(targets['protein'])} | "
        f"Ж {fmt(totals[2])}/{fmt(targets['fat'])} | "
        f"У {fmt(totals[3])}/{fmt(targets['carbs'])}"
    )


def main():
    args = build_parser().parse_args()
    connection = db.connect()
    try:
        if args.cmd == "init":
            print(db.DB_PATH)
        elif args.cmd == "profile":
            print(db.profile(connection))
        elif args.cmd == "add-food":
            db.add_food(connection, args)
        elif args.cmd == "add-dish":
            db.add_dish(connection, args)
        elif args.cmd == "log":
            for name, grams in items(args.items):
                db.log_food(connection, db.find(connection, "foods", name),
                            grams, args.note)
        elif args.cmd == "log-dish":
            db.log_dish(connection, db.find(connection, "dishes", args.name),
                        args.servings)
        elif args.cmd == "add-supplement":
            db.add_supplement(connection, args)
        elif args.cmd == "log-supplement":
            db.log_supplement(connection, args)
        elif args.cmd == "log-steps":
            db.log_steps(connection, args)
        elif args.cmd == "log-workout":
            db.log_workout(connection, args)
        elif args.cmd == "today":
            selected_date = date.fromisoformat(args.date) if args.date else date.today()
            show_today(connection, selected_date)
    finally:
        connection.close()


if __name__ == "__main__":
    main()

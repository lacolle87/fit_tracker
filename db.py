from datetime import date, datetime
from pathlib import Path
import duckdb

DB_PATH = Path(__file__).with_name("fit.duckdb")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SEED_PATH = Path(__file__).with_name("seed.sql")


def connect():
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    if conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0:
        conn.execute(SEED_PATH.read_text(encoding="utf-8"))
    return conn


def targets(c):
    r = c.execute(
        "SELECT calories, protein_g, fat_g, carbs_g FROM nutrition_targets "
        "WHERE valid_from <= CURRENT_DATE ORDER BY valid_from DESC, id DESC LIMIT 1"
    ).fetchone()
    return dict(zip(("calories", "protein", "fat", "carbs"), r))


def profile(c): return c.execute("SELECT birth_date,sex,height_cm,current_weight_kg FROM profile WHERE id=1").fetchone()


def find(c, table, name):
    r = c.execute(f"SELECT * FROM {table} WHERE lower(name)=lower(?)", [name.strip()]).fetchone()
    if r:
        return r
    rows = c.execute(f"SELECT * FROM {table} WHERE lower(name) LIKE lower(?) ORDER BY name", [f"%{name.strip()}%"]).fetchall()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise ValueError(f"Не найдено: {name}")
    raise ValueError("Несколько совпадений: " + ", ".join(x[1] for x in rows))


def add_food(c, a): c.execute("INSERT INTO foods VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM foods),?,?,?,?,?)",
                              [a.name, a.kcal, a.protein, a.fat, a.carbs])


def add_dish(c, a): c.execute("INSERT INTO dishes VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM dishes),?,?,?,?,?,?,?)",
                              [a.name, a.grams, a.kcal, a.protein, a.fat, a.carbs, datetime.now()])


def log_food(c, food, grams, note=None): c.execute("INSERT INTO meals VALUES (?,?,?,?,?)",
                                                   [int(datetime.now().timestamp() * 1e6), datetime.now(), food[0], grams, note])


def log_dish(c, dish, servings): c.execute("INSERT INTO meals VALUES (?,?,?,?,?)", [
    int(datetime.now().timestamp() * 1e6), datetime.now(), -dish[0], dish[2] * servings, "dish"])


def add_supplement(c,
                   a): c.execute("INSERT INTO supplements VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM supplements),?,?,?,?,?)",
                                 [a.name,
                                  a.amount,
                                  a.unit,
                                  a.ingredients,
                                  a.note])


def log_supplement(c, a):
    s = find(c, "supplements", a.name)
    amount = a.amount if a.amount is not None else s[2]
    unit = a.unit or s[3]
    if amount is None:
        raise ValueError("Укажи дозировку")
    c.execute("INSERT INTO supplement_intake VALUES (?,?,?,?,?,?)", [
              int(datetime.now().timestamp() * 1e6), datetime.now(), s[0], amount, unit, a.note])


def log_steps(
    c, a): c.execute(
        "INSERT INTO daily_activity VALUES (?, ?, ?, ?) "
        "ON CONFLICT(activity_date) DO UPDATE SET steps=EXCLUDED.steps, "
        "active_minutes=EXCLUDED.active_minutes, note=EXCLUDED.note", [
            date.fromisoformat(
                a.date) if a.date else date.today(), a.steps, a.active_minutes, a.note])


def log_workout(c, a):
    when = datetime.fromisoformat(a.datetime) if a.datetime else datetime.now()
    c.execute("INSERT INTO workouts VALUES (?,?,?,?,?,?,?)", [
              int(when.timestamp() * 1e6), when, a.type, a.duration, a.intensity, a.calories, a.note])

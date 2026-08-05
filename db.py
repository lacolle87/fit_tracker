from datetime import date, datetime, timedelta
from pathlib import Path
import duckdb

DB_PATH = Path(__file__).with_name("fit.duckdb")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
SEED_PATH = Path(__file__).with_name("seed.sql")


def connect():
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.execute("ALTER TABLE foods ADD COLUMN IF NOT EXISTS barcode VARCHAR")
    conn.execute("ALTER TABLE foods ADD COLUMN IF NOT EXISTS is_estimated BOOLEAN")
    conn.execute("UPDATE foods SET is_estimated=FALSE WHERE is_estimated IS NULL")
    conn.execute("UPDATE foods SET is_estimated=TRUE WHERE name LIKE '% (оценка)'")
    conn.execute("UPDATE foods SET name=REPLACE(name, ' (оценка)', '') WHERE name LIKE '% (оценка)'")
    conn.execute("ALTER TABLE meals ADD COLUMN IF NOT EXISTS meal_type VARCHAR")
    conn.execute(
        "UPDATE meals SET meal_type=note WHERE meal_type IS NULL "
        "AND note IN ('breakfast', 'lunch', 'dinner', 'snack')"
    )
    conn.execute("UPDATE meals SET note=NULL WHERE note=meal_type")
    conn.execute("ALTER TABLE nutrition_targets ADD COLUMN IF NOT EXISTS valid_to DATE")
    conn.execute("ALTER TABLE body_measurements ADD COLUMN IF NOT EXISTS muscle_pct DOUBLE")
    measurement_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(body_measurements)").fetchall()
    }
    if "muscle_kg" in measurement_columns:
        conn.execute(
            "UPDATE body_measurements SET muscle_pct=muscle_kg WHERE muscle_pct IS NULL"
        )
        conn.execute("ALTER TABLE body_measurements DROP COLUMN muscle_kg")
    if conn.execute("SELECT COUNT(*) FROM profile").fetchone()[0] == 0:
        conn.execute(SEED_PATH.read_text(encoding="utf-8"))
    conn.execute(
        "DELETE FROM nutrition_targets WHERE id IN ("
        "SELECT id FROM (SELECT id, ROW_NUMBER() OVER ("
        "PARTITION BY valid_from ORDER BY id DESC) AS position "
        "FROM nutrition_targets) WHERE position > 1)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS nutrition_targets_valid_from "
        "ON nutrition_targets(valid_from)"
    )
    return conn


def targets(c, on_date=None):
    on_date = on_date or date.today()
    r = c.execute(
        "SELECT calories, protein_g, fat_g, carbs_g FROM nutrition_targets "
        "WHERE valid_from <= ? AND (valid_to IS NULL OR valid_to >= ?) "
        "ORDER BY valid_from DESC, id DESC LIMIT 1",
        [on_date, on_date],
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


def add_food(c, a):
    c.execute(
        "INSERT INTO foods (id,name,kcal_100,protein_100,fat_100,carbs_100,is_estimated) "
        "VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM foods),?,?,?,?,?,?)",
        [a.name, a.kcal, a.protein, a.fat, a.carbs, getattr(a, "estimated", False)],
    )


def add_dish(c, a): c.execute("INSERT INTO dishes VALUES ((SELECT COALESCE(MAX(id),0)+1 FROM dishes),?,?,?,?,?,?,?)",
                              [a.name, a.grams, a.kcal, a.protein, a.fat, a.carbs, datetime.now()])


def log_food(c, food, grams, note=None, meal_type=None):
    c.execute(
        "INSERT INTO meals (id,eaten_at,food_id,grams,note,meal_type) VALUES (?,?,?,?,?,?)",
        [int(datetime.now().timestamp() * 1e6), datetime.now(), food[0], grams, note, meal_type],
    )


def log_dish(c, dish, servings, meal_type=None):
    c.execute(
        "INSERT INTO meals (id,eaten_at,food_id,grams,note,meal_type) VALUES (?,?,?,?,?,?)",
        [int(datetime.now().timestamp() * 1e6), datetime.now(), -dish[0], dish[2] * servings,
         None, meal_type],
    )


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


def log_measurement(c, a):
    measured_on = date.fromisoformat(a.date) if a.date else date.today()
    c.execute(
        "INSERT INTO body_measurements (measured_on, weight_kg, body_fat_pct, muscle_pct, note) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(measured_on) DO UPDATE SET weight_kg=EXCLUDED.weight_kg, "
        "body_fat_pct=EXCLUDED.body_fat_pct, muscle_pct=EXCLUDED.muscle_pct, note=EXCLUDED.note",
        [measured_on, a.weight, a.fat, a.muscle, a.note],
    )
    c.execute("UPDATE profile SET current_weight_kg=?, updated_at=CURRENT_TIMESTAMP WHERE id=1", [a.weight])
    c.execute(
        "INSERT INTO weights VALUES (?, ?) ON CONFLICT(measured_on) DO UPDATE SET kg=EXCLUDED.kg",
        [measured_on, a.weight],
    )


def update_targets(c, calories, current, on_date=None):
    on_date = on_date or date.today()
    existing = c.execute(
        "SELECT id FROM nutrition_targets WHERE valid_from=?", [on_date]
    ).fetchone()
    if existing:
        c.execute(
            "UPDATE nutrition_targets SET calories=?, protein_g=?, fat_g=?, carbs_g=?, "
            "note=? WHERE id=?",
            [calories, current["protein"], current["fat"], current["carbs"],
             "Обновлено пользователем", existing[0]],
        )
        return
    next_id = c.execute(
        "SELECT COALESCE(MAX(id), 0) + 1 FROM nutrition_targets"
    ).fetchone()[0]
    c.execute(
        "UPDATE nutrition_targets SET valid_to=? "
        "WHERE valid_from < ? AND (valid_to IS NULL OR valid_to >= ?)",
        [on_date - timedelta(days=1), on_date, on_date],
    )
    c.execute(
        "INSERT INTO nutrition_targets "
        "(id, calories, protein_g, fat_g, carbs_g, valid_from, valid_to, note) "
        "VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
        [next_id, calories, current["protein"], current["fat"], current["carbs"], on_date, "Обновлено пользователем"],
    )


def update_full_targets(c, a):
    update_targets(
        c,
        a.calories,
        {"protein": a.protein, "fat": a.fat, "carbs": a.carbs},
        date.fromisoformat(a.date) if a.date else date.today(),
    )


def update_calorie_target(c, calories):
    current = targets(c)
    update_targets(c, calories, current)
    return
    next_id = c.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM nutrition_targets").fetchone()[0]
    c.execute(
        "INSERT INTO nutrition_targets VALUES (?, ?, ?, ?, ?, CURRENT_DATE, ?)",
        [next_id, calories, current["protein"], current["fat"], current["carbs"], "Обновлено пользователем"],
    )

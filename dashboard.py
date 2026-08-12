import json
import re
import threading
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db
import barcode

ROOT = Path(__file__).parent


def load_queries():
    text = (ROOT / "dashboard.sql").read_text(encoding="utf-8")
    return {name: body.strip() for name, body in re.findall(
        r"-- name: (\w+)\s*\n(.*?)(?=\n-- name:|\Z)", text, re.S
    )}


QUERIES = load_queries()


def json_value(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def rows(connection, query_name, params):
    return [[json_value(v) for v in row] for row in connection.execute(
        QUERIES[query_name], params
    ).fetchall()]


def meal_rows(connection, day):
    columns = (
        "eaten_at", "name", "grams", "calories", "protein", "fat", "carbs",
        "meal_type", "id",
    )
    return [dict(zip(columns, row)) for row in rows(connection, "meals", [day])]


def payload(day, named_meals=False, average_days=7):
    connection = db.connect()
    try:
        target = db.targets(connection, day)
        totals = connection.execute(QUERIES["day_totals"], [day]).fetchone()
        start = day - timedelta(days=29)
        end = day
        average_start = day - timedelta(days=average_days - 1)
        weight_start = day - timedelta(days=89)
        return {
            "date": day.isoformat(),
            "targets": target,
            "totals": dict(zip(("calories", "protein", "fat", "carbs"), totals)),
            "nutrition_average": dict(zip(
                ("calories", "protein", "fat", "carbs"),
                connection.execute(
                    QUERIES["nutrition_average"],
                    [average_start, day, average_start, day],
                ).fetchone(),
            )),
            "nutrition_average_days": average_days,
            "meals": meal_rows(connection, day) if named_meals else rows(connection, "meals", [day]),
            "activity": rows(connection, "activity", [start, end]),
            "daily": rows(connection, "daily_metrics", [start, end, start, end, start, end]),
            "workouts": rows(connection, "workouts", [start, end]),
            "weights": rows(connection, "weights", [start, end]),
            "body_measurements": rows(connection, "body_measurements", [start, end]),
            "weekly_weight_trend": rows(connection, "weekly_weight_trend", [weight_start, end]),
        }
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/close":
            self.send_response(204)
            self.end_headers()
            threading.Timer(0.25, self.server.shutdown).start()
            return
        if parsed.path == "/api/meals":
            try:
                meal_id = int(parse_qs(parsed.query).get("id", [""])[0])
                connection = db.connect()
                try:
                    found = connection.execute(
                        "SELECT 1 FROM meals WHERE id=?", [meal_id]
                    ).fetchone()
                    if found:
                        connection.execute("DELETE FROM meals WHERE id=?", [meal_id])
                finally:
                    connection.close()
                body = json.dumps({"ok": bool(found)}).encode()
                self.send_response(200)
            except ValueError:
                body = json.dumps({"ok": False, "error": "Invalid meal id"}).encode()
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            body = (ROOT / "dashboard.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif parsed.path in {"/favicon.ico", "/fit_tracker.ico"}:
            body = (ROOT / "fit_tracker_transparent_v2.ico").read_bytes()
            content_type = "image/x-icon"
        elif parsed.path == "/api/dashboard":
            day = parse_qs(parsed.query).get("date", [date.today().isoformat()])[0]
            named_meals = parse_qs(parsed.query).get("format", [""])[0] == "objects"
            average_days = int(parse_qs(parsed.query).get("average_days", ["7"])[0])
            if average_days not in {7, 30}:
                raise ValueError("average_days must be 7 or 30")
            body = json.dumps(
                payload(date.fromisoformat(day), named_meals, average_days), ensure_ascii=False
            ).encode()
            content_type = "application/json; charset=utf-8"
        elif parsed.path == "/api/barcode":
            code = parse_qs(parsed.query).get("code", [""])[0]
            try:
                normalized_code = barcode.normalize(code)
                connection = db.connect()
                try:
                    existing = connection.execute(
                        "SELECT id, name, kcal_100, protein_100, fat_100, carbs_100 FROM foods WHERE barcode=?",
                        [normalized_code],
                    ).fetchone()
                    if existing:
                        product = dict(zip(("id", "name", "kcal", "protein", "fat", "carbs"), existing))
                    else:
                        product = barcode.fetch(normalized_code)
                        food_id = connection.execute("SELECT COALESCE(MAX(id),0)+1 FROM foods").fetchone()[0]
                        connection.execute(
                            "INSERT INTO foods (id,name,kcal_100,protein_100,fat_100,carbs_100,barcode) "
                            "VALUES (?,?,?,?,?,?,?)",
                            [food_id, db.display_name(product["name"]), product["kcal"], product["protein"],
                             product["fat"], product["carbs"], product["barcode"]],
                        )
                        product["id"] = food_id
                finally:
                    connection.close()
                body = json.dumps({"ok": True, "product": product}, ensure_ascii=False).encode()
                content_type = "application/json; charset=utf-8"
            except ValueError as error:
                body = json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False).encode()
                content_type = "application/json; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        return


def main():
    port = 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard: {url}")
    threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()

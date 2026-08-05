import json
import re
import threading
import time
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import db

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


def payload(day):
    connection = db.connect()
    try:
        target = db.targets(connection, day)
        totals = connection.execute(QUERIES["day_totals"], [day]).fetchone()
        start = day - timedelta(days=29)
        end = day
        return {
            "date": day.isoformat(),
            "targets": target,
            "totals": dict(zip(("calories", "protein", "fat", "carbs"), totals)),
            "meals": rows(connection, "meals", [day]),
            "activity": rows(connection, "activity", [start, end]),
            "workouts": rows(connection, "workouts", [start, end]),
            "weights": rows(connection, "weights", [start, end]),
            "body_measurements": rows(connection, "body_measurements", [start, end]),
        }
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.send_error(404)

    def do_GET(self):
        parsed = urlparse(self.path)
        self.server.last_activity = time.monotonic()
        if parsed.path == "/":
            body = (ROOT / "dashboard.html").read_bytes()
            content_type = "text/html; charset=utf-8"
        elif parsed.path in {"/favicon.ico", "/fit_tracker.ico"}:
            body = (ROOT / "fit_tracker_transparent_v2.ico").read_bytes()
            content_type = "image/x-icon"
        elif parsed.path == "/api/dashboard":
            day = parse_qs(parsed.query).get("date", [date.today().isoformat()])[0]
            body = json.dumps(payload(date.fromisoformat(day)), ensure_ascii=False).encode()
            content_type = "application/json; charset=utf-8"
        elif parsed.path == "/api/ping":
            self.send_response(204)
            self.end_headers()
            return
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


def stop_when_idle(server, timeout_seconds=30):
    while True:
        time.sleep(5)
        if time.monotonic() - server.last_activity >= timeout_seconds:
            server.shutdown()
            return


def main():
    port = 8765
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.last_activity = time.monotonic()
    threading.Thread(target=stop_when_idle, args=(server,), daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    print(f"Dashboard: {url}")
    threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    server.serve_forever()
    server.server_close()


if __name__ == "__main__":
    main()

import json
import tempfile
import threading
import unittest
from datetime import date, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen

import dashboard
import db


class DashboardContractTests(unittest.TestCase):
    day = date(2026, 8, 5)

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp_dir.name) / "test.duckdb"
        connection = db.connect()
        try:
            connection.execute(
                "INSERT INTO foods (id,name,kcal_100,protein_100,fat_100,carbs_100) "
                "VALUES (999,'Test food',100,10,5,20)"
            )
            for number, meal_type in enumerate(("breakfast", "snack")):
                connection.execute(
                    "INSERT INTO meals (id,eaten_at,food_id,grams,note,meal_type) "
                    "VALUES (?,?,?,?,?,?)",
                    [
                        1000 + number,
                        datetime(2026, 8, 5, 8 + number),
                        999,
                        100,
                        None,
                        meal_type,
                    ],
                )
        finally:
            connection.close()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), dashboard.Handler)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    def dashboard_response(self, query):
        url = f"http://127.0.0.1:{self.server.server_port}/api/dashboard?{query}"
        with urlopen(url) as response:
            return json.load(response)

    def test_legacy_api_keeps_meal_type_at_index_seven(self):
        data = self.dashboard_response("date=2026-08-05")

        self.assertEqual([meal[7] for meal in data["meals"]], ["breakfast", "snack"])

    def test_named_api_and_html_use_the_same_meal_contract(self):
        data = self.dashboard_response("date=2026-08-05&format=objects")
        html = (dashboard.ROOT / "dashboard.html").read_text(encoding="utf-8")

        self.assertEqual(
            [meal["meal_type"] for meal in data["meals"]],
            ["breakfast", "snack"],
        )
        self.assertIn("format=objects", html)
        self.assertIn("meal.meal_type", html)
        self.assertIn("meal.eaten_at", html)
        self.assertIn("meal.name", html)


if __name__ == "__main__":
    unittest.main()

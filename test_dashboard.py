import json
import tempfile
import threading
import unittest
from datetime import date, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request, urlopen

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
                "INSERT INTO meals (id,eaten_at,food_id,grams,note,meal_type) "
                "VALUES (2000,TIMESTAMP '2026-08-12 08:00:00',999,100,NULL,'breakfast')"
            )
            connection.execute(
                "INSERT INTO nutrition_targets "
                "VALUES (999,1800,120,65,180,DATE '2026-08-05',NULL,'test')"
            )
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
        self.assertIn('id="refresh"', html)
        self.assertIn("data-delete-meal", html)
        self.assertIn("Удалить эту запись из дневника?", html)

    def test_delete_meal_removes_only_selected_record(self):
        data = self.dashboard_response("date=2026-08-05&format=objects")
        meal_id = data["meals"][0]["id"]
        request = Request(
            f"http://127.0.0.1:{self.server.server_port}/api/meals?id={meal_id}",
            method="POST",
        )
        with urlopen(request) as response:
            result = json.load(response)

        remaining = self.dashboard_response("date=2026-08-05&format=objects")["meals"]
        self.assertTrue(result["ok"])
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["meal_type"], "snack")

    def test_estimated_foods_keep_clean_display_names(self):
        connection = db.connect()
        try:
            connection.execute(
                "INSERT INTO foods (id,name,kcal_100,protein_100,fat_100,carbs_100) "
                "VALUES (1000,'Example (оценка)',100,10,5,20)"
            )
        finally:
            connection.close()
        connection = db.connect()
        try:
            food = connection.execute(
                "SELECT name,is_estimated FROM foods WHERE id=1000"
            ).fetchone()
        finally:
            connection.close()

        self.assertEqual(food, ("Example", True))

    def test_new_food_names_start_with_a_capital_letter(self):
        connection = db.connect()
        try:
            db.add_food(
                connection,
                SimpleNamespace(
                    name="  яблоко тест  ", kcal=89, protein=1.1, fat=0.3, carbs=22.8,
                    estimated=False,
                ),
            )
            name = connection.execute(
                "SELECT name FROM foods WHERE lower(name)='яблоко тест'"
            ).fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(name, "Яблоко тест")

    def test_recipe_keeps_ingredients_and_calculates_totals(self):
        connection = db.connect()
        try:
            recipe_id = db.add_recipe(connection, "тестовый рецепт", [(999, 100)])
            recipe = connection.execute(
                "SELECT name,final_grams FROM recipes WHERE id=?", [recipe_id]
            ).fetchone()
            totals = db.recipe_totals(connection, recipe_id)
        finally:
            connection.close()

        self.assertEqual(recipe, ("Тестовый рецепт", None))
        self.assertEqual(
            totals,
            {"raw_grams": 100, "calories": 100, "protein": 10, "fat": 5, "carbs": 20},
        )

    def test_weight_chart_reserves_space_around_all_points(self):
        html = (dashboard.ROOT / "dashboard.html").read_text(encoding="utf-8")

        self.assertIn("const weightPadding=Math.max(.8,weightRange*.25);", html)
        self.assertIn("forceNiceScale:false", html)
        self.assertIn("type:'area',height:288", html)
        self.assertIn("categories:labels,labels:{show:false}", html)
        self.assertNotIn("$('weightChart').className='h-72 overflow-hidden';", html)

    def test_dashboard_exposes_calendar_seven_day_averages_and_weekly_weight_trend(self):
        connection = db.connect()
        try:
            connection.execute(
                "INSERT INTO body_measurements VALUES "
                "(DATE '2026-08-05',100,NULL,NULL,NULL),"
                "(DATE '2026-08-08',99,NULL,NULL,NULL),"
                "(DATE '2026-08-12',98,NULL,NULL,NULL)"
            )
        finally:
            connection.close()

        data = self.dashboard_response("date=2026-08-12&format=objects")

        self.assertEqual(data["nutrition_average"], {
            "calories": 100,
            "protein": 10,
            "fat": 5,
            "carbs": 20,
        })
        self.assertEqual(data["nutrition_average_days"], 7)
        self.assertEqual(len(data["weekly_weight_trend"]), 2)
        self.assertEqual(data["weekly_weight_trend"][0][3], None)
        self.assertAlmostEqual(data["weekly_weight_trend"][1][3], -1.5)
        html = (dashboard.ROOT / "dashboard.html").read_text(encoding="utf-8")
        self.assertIn("formatter:v=>n(v,1)", html)
        self.assertIn("const ratePoints=rates.filter(v=>v!==null).concat(-1.25)", html)
        self.assertIn("min:rateMin,max:rateMax,forceNiceScale:false", html)
        self.assertIn("if (actualRates.length===1)", html)
        self.assertIn("Факт за последнюю неделю", html)
        self.assertIn("text-[30px]", html)
        self.assertIn('id="nutritionAverage"', html)
        self.assertIn("Среднее за ${averageDays} дней", html)
        self.assertNotIn('id="averageCalories"', html)

    def test_dashboard_supports_thirty_day_nutrition_average(self):
        data = self.dashboard_response("date=2026-08-12&average_days=30&format=objects")

        self.assertEqual(data["nutrition_average_days"], 30)
        self.assertAlmostEqual(data["nutrition_average"]["calories"], 150)


if __name__ == "__main__":
    unittest.main()

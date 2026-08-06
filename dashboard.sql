-- name: day_totals
SELECT
    COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.kcal_100*m.grams/100 ELSE d.total_kcal*m.grams/d.total_grams END), 0),
    COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.protein_100*m.grams/100 ELSE d.total_protein*m.grams/d.total_grams END), 0),
    COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.fat_100*m.grams/100 ELSE d.total_fat*m.grams/d.total_grams END), 0),
    COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.carbs_100*m.grams/100 ELSE d.total_carbs*m.grams/d.total_grams END), 0)
FROM meals m
LEFT JOIN foods f ON f.id=m.food_id
LEFT JOIN dishes d ON d.id=-m.food_id
WHERE CAST(m.eaten_at AS DATE)=?

-- name: meals
SELECT m.eaten_at, COALESCE(f.name,d.name), m.grams,
       CASE WHEN m.food_id > 0 THEN f.kcal_100*m.grams/100 ELSE d.total_kcal*m.grams/d.total_grams END,
       CASE WHEN m.food_id > 0 THEN f.protein_100*m.grams/100 ELSE d.total_protein*m.grams/d.total_grams END,
       CASE WHEN m.food_id > 0 THEN f.fat_100*m.grams/100 ELSE d.total_fat*m.grams/d.total_grams END,
       CASE WHEN m.food_id > 0 THEN f.carbs_100*m.grams/100 ELSE d.total_carbs*m.grams/d.total_grams END,
       m.meal_type,
       m.id
FROM meals m LEFT JOIN foods f ON f.id=m.food_id LEFT JOIN dishes d ON d.id=-m.food_id
WHERE CAST(m.eaten_at AS DATE)=? ORDER BY m.eaten_at

-- name: activity
SELECT activity_date, steps, active_minutes FROM daily_activity
WHERE activity_date BETWEEN ? AND ? ORDER BY activity_date

-- name: daily_metrics
WITH days AS (
    SELECT CAST(eaten_at AS DATE) AS day FROM meals
    WHERE CAST(eaten_at AS DATE) BETWEEN ? AND ?
    UNION
    SELECT activity_date AS day FROM daily_activity
    WHERE activity_date BETWEEN ? AND ?
), meal_totals AS (
    SELECT CAST(m.eaten_at AS DATE) AS day,
           COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.kcal_100*m.grams/100 ELSE d.total_kcal*m.grams/d.total_grams END), 0) AS calories,
           COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.protein_100*m.grams/100 ELSE d.total_protein*m.grams/d.total_grams END), 0) AS protein,
           COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.fat_100*m.grams/100 ELSE d.total_fat*m.grams/d.total_grams END), 0) AS fat,
           COALESCE(SUM(CASE WHEN m.food_id > 0 THEN f.carbs_100*m.grams/100 ELSE d.total_carbs*m.grams/d.total_grams END), 0) AS carbs
    FROM meals m
    LEFT JOIN foods f ON f.id=m.food_id
    LEFT JOIN dishes d ON d.id=-m.food_id
    WHERE CAST(m.eaten_at AS DATE) BETWEEN ? AND ?
    GROUP BY CAST(m.eaten_at AS DATE)
)
SELECT days.day, COALESCE(meal_totals.calories, 0), COALESCE(meal_totals.protein, 0),
       COALESCE(meal_totals.fat, 0), COALESCE(meal_totals.carbs, 0),
       COALESCE(daily_activity.steps, 0)
FROM days
LEFT JOIN meal_totals ON meal_totals.day=days.day
LEFT JOIN daily_activity ON daily_activity.activity_date=days.day
ORDER BY days.day

-- name: workouts
SELECT performed_at, workout_type, duration_min, intensity, calories_est
FROM workouts WHERE CAST(performed_at AS DATE) BETWEEN ? AND ? ORDER BY performed_at

-- name: weights
SELECT measured_on, COALESCE(b.weight_kg, w.kg) AS kg
FROM weights w
FULL OUTER JOIN body_measurements b USING (measured_on)
WHERE measured_on BETWEEN ? AND ?
ORDER BY measured_on

-- name: body_measurements
SELECT measured_on, weight_kg, body_fat_pct, muscle_pct FROM body_measurements
WHERE measured_on BETWEEN ? AND ? ORDER BY measured_on

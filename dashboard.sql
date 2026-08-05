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
       m.note
FROM meals m LEFT JOIN foods f ON f.id=m.food_id LEFT JOIN dishes d ON d.id=-m.food_id
WHERE CAST(m.eaten_at AS DATE)=? ORDER BY m.eaten_at

-- name: activity
SELECT activity_date, steps, active_minutes FROM daily_activity
WHERE activity_date BETWEEN ? AND ? ORDER BY activity_date

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

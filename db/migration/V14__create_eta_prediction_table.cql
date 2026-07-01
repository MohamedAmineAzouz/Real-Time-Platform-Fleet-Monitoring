
CREATE TABLE IF NOT EXISTS batch_eta_prediction (
    start_city           text,
    end_city             text,
    stat_date            text,
    hour_of_day          int,
    day_of_week          int,
    predicted_eta_hours  double,
    avg_speed_kmh        double,
    distance_km          double,
    confidence           text,
    sample_count         int,
    PRIMARY KEY ((start_city, end_city), stat_date, hour_of_day, day_of_week)
) WITH CLUSTERING ORDER BY (stat_date DESC, hour_of_day ASC, day_of_week ASC);

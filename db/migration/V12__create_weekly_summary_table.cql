CREATE TABLE IF NOT EXISTS batch_weekly_summary (
    week_id                 text,
    week_start_date         text,
    week_end_date           text,
    total_distance_km       double,
    total_fuel_consumed_l   double,
    avg_fuel_per_100km      double,
    total_alerts            int,
    fleet_utilization_avg   double,
    wow_distance_pct        double,
    wow_fuel_pct            double,
    wow_alerts_pct          double,
    top_trucks_distance     list<text>,
    top_trucks_efficiency   list<text>,
    top_drivers_performance list<text>,
    top_routes              list<text>,
    PRIMARY KEY (week_id)
);


CREATE TABLE IF NOT EXISTS batch_daily_truck_stats (
    stat_date          text,
    truck_id           int,
    total_distance_km  double,
    total_fuel_consumed_l double,
    fuel_per_100km     double,
    avg_speed_kmh      double,
    max_speed_kmh      double,
    total_alerts       int,
    overspeed_count    int,
    overheat_count     int,
    fuel_theft_count   int,
    low_fuel_count     int,
    event_count        bigint,
    PRIMARY KEY ((stat_date), truck_id)
) WITH CLUSTERING ORDER BY (truck_id ASC);


CREATE TABLE IF NOT EXISTS batch_driver_performance (
    stat_date              text,
    driver_id              text,
    total_events           bigint,
    total_distance_km      double,
    total_fuel_l           double,
    avg_speed              double,
    max_speed              double,
    speed_compliance_rate  double,
    alert_rate_per_100     double,
    fuel_per_100km         double,
    theft_events           int,
    speed_score            double,
    fuel_score             double,
    alert_score            double,
    distance_score         double,
    performance_score      double,
    fleet_rank             int,
    PRIMARY KEY ((stat_date), performance_score, driver_id)
) WITH CLUSTERING ORDER BY (performance_score DESC, driver_id ASC);


CREATE TABLE IF NOT EXISTS batch_fuel_waste_anomalies (
    stat_date                   text,
    truck_id                    int,
    total_distance_km           double,
    total_fuel_l                double,
    fuel_per_100km              double,
    fleet_median_fuel_per_100km double,
    anomaly_threshold           double,
    waste_vs_median_pct         double,
    is_anomaly                  boolean,
    event_count                 bigint,
    PRIMARY KEY ((stat_date), truck_id)
);


CREATE TABLE IF NOT EXISTS batch_maintenance_flags (
    stat_date                text,
    truck_id                 int,
    avg_engine_temp          double,
    max_engine_temp          double,
    max_odometer_km          double,
    avg_fuel_rate            double,
    fuel_rate_stddev         double,
    overheat_count           int,
    theft_count              int,
    event_count              bigint,
    flag_high_temp           boolean,
    flag_overheat_alerts     boolean,
    flag_odometer_milestone  boolean,
    flag_fuel_inconsistency  boolean,
    maintenance_needed       boolean,
    priority                 text,
    PRIMARY KEY ((stat_date), priority, truck_id)
) WITH CLUSTERING ORDER BY (priority ASC, truck_id ASC);


CREATE TABLE IF NOT EXISTS batch_route_efficiency (
    stat_date               text,
    start_city              text,
    end_city                text,
    total_trips             bigint,
    avg_distance_km         double,
    avg_fuel_l              double,
    avg_fuel_per_100km      double,
    avg_speed_kmh           double,
    avg_duration_min        double,
    avg_alerts_per_trip     double,
    most_efficient_truck    int,
    most_efficient_driver   text,
    best_fuel_per_100km     double,
    PRIMARY KEY ((stat_date), start_city, end_city)
) WITH CLUSTERING ORDER BY (start_city ASC, end_city ASC);

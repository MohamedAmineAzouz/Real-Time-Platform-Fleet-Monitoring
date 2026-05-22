DROP TABLE IF EXISTS batch_route_efficiency;

CREATE TABLE batch_route_efficiency (
    stat_date               text,
    start_city              text,
    end_city                text,
    truck_id                int,
    driver_id               text,
    total_trips             bigint,
    total_distance_km       double,
    total_fuel_consumed_l   double,
    avg_fuel_per_100km      double,
    avg_speed_kmh           double,
    total_duration_h        double,
    avg_alerts_per_trip     double,
    PRIMARY KEY ((stat_date), start_city, end_city, truck_id, driver_id)
) WITH CLUSTERING ORDER BY (start_city ASC, end_city ASC, truck_id ASC, driver_id ASC)
AND default_time_to_live = 2592000;

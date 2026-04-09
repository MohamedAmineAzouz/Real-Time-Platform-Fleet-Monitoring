

CREATE TABLE IF NOT EXISTS traffic_violations (
    month_year          text,
    truck_id            int,
    violation_id        uuid,
    violation_type      text,
    city                text,
    fine_mad            double,
    violation_date      date,
    details             text,
    PRIMARY KEY ((month_year), truck_id, violation_id)
) WITH CLUSTERING ORDER BY (truck_id ASC, violation_id ASC);

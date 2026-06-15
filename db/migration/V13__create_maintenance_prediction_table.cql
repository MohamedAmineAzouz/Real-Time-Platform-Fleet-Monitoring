-- Table to store ML-based maintenance predictions
CREATE TABLE IF NOT EXISTS batch_maintenance_prediction (
    stat_date            text,
    truck_id             int,
    predicted_rul_hours  double,
    priority             text,
    PRIMARY KEY ((stat_date), priority, truck_id)
) WITH CLUSTERING ORDER BY (priority ASC, truck_id ASC);

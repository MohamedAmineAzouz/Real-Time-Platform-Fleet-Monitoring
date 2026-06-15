-- Table to store ML-based maintenance predictions
-- PRIMARY KEY:
-- Partition Key: stat_date (Grouping by day)
-- Clustering Column: truck_id (Allowing direct lookup per truck)
DROP TABLE IF EXISTS batch_maintenance_prediction;

CREATE TABLE batch_maintenance_prediction (
    stat_date            text,
    truck_id             int,
    predicted_rul_hours  double,
    priority             text,
    PRIMARY KEY ((stat_date), truck_id)
);

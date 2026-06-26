-- Table to store ML-based maintenance predictions
-- PRIMARY KEY:
-- Partition Key: stat_date (Grouping by day)
-- Clustering Column: truck_id (Allowing direct lookup per truck)
DROP TABLE batch_maintenance_prediction;

CREATE TABLE batch_maintenance_prediction (
    stat_date            timestamp,
    truck_id             int,
    predicted_rul_hours  double,
    priority             text,
    PRIMARY KEY ((truck_id), stat_date)
)
DROP TABLE IF EXISTS batch_maintenance_prediction;

CREATE TABLE batch_maintenance_prediction (
    stat_date            timestamp,
    truck_id             int,
    predicted_rul_hours  double,
    priority             text,
    PRIMARY KEY ((truck_id), stat_date)
)
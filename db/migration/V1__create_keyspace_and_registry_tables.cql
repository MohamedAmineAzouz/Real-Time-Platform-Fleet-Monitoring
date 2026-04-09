
CREATE TABLE IF NOT EXISTS drivers (
    driver_id               text,
    name                    text,
    license_number          text,
    phone                   text,
    status                  text,
    current_truck_id        int,
    created_at              timestamp,
    updated_at              timestamp,
    PRIMARY KEY (driver_id)
);


CREATE TABLE IF NOT EXISTS trucks (
    truck_id                int,
    license_plate           text,
    model                   text,
    year                    int,
    status                  text,
    fuel_capacity           double,
    max_load_kg             double,
    created_at              timestamp,
    updated_at              timestamp,
    PRIMARY KEY (truck_id)
);


CREATE TABLE IF NOT EXISTS trajets (
    trajet_id               uuid,
    start_city              text,
    end_city                text,
    distance_km             double,
    created_at              timestamp,
    updated_at              timestamp,
    PRIMARY KEY (trajet_id)
);


CREATE TABLE IF NOT EXISTS maintenance_schedules (
    schedule_id             uuid,
    truck_id                int,
    maintenance_type        text,
    description             text,
    scheduled_start         timestamp,
    scheduled_end           timestamp,
    assigned_mechanic       text,
    cost                    double,
    created_at              timestamp,
    updated_at              timestamp,
    PRIMARY KEY (schedule_id)
);

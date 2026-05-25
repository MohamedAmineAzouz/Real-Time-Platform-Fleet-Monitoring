"""
spark_jobs/job_traffic_violations.py
─────────────────────────────────────────────────────────────────────────────
Realistic Monthly Traffic Violations Generator
─────────────────────────────────────────────────────────────────────────────
- Reads ACTUAL truck_history records
- violation_date & city extracted directly from telemetry
- Speeding violations mapped to real speed spikes
- Other violations sampled from actual driving days & cities
- Enforces: max 1/day, max 4/month, 75% trucks get 0
- Applies official Moroccan traffic fines (MAD)
─────────────────────────────────────────────────────────────────────────────
"""

import os
import sys
import random
import uuid
import math
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, DoubleType, TimestampType
from pyspark.sql.functions import (
    col, when, max as _max, collect_list, struct, date_trunc, coalesce, lit, to_date
)

# ── Configuration (Hardcoded to avoid import errors in Spark cluster) ───────
CASSANDRA_KEYSPACE = os.getenv("CASSANDRA_KEYSPACE", "fleet")

SPEED_LIMIT = 120.0
BASE_LAMBDA = 0.35
MAX_MONTHLY = 4

# Official Moroccan traffic fines (MAD)
VIOLATION_CONFIG = {
    "speeding_radar": {"min": 500,  "max": 3000, "label": "تجاوز السرعة المسموحة"},
    "red_light":      {"min": 700,  "max": 700,  "label": "تجاوز إشارة حمراء"},
    "stop_sign":      {"min": 700,  "max": 700,  "label": "تجاوز علامة قف"},
    "mobile_phone":   {"min": 1000, "max": 1000, "label": "استخدام الهاتف أثناء القيادة"},
    "illegal_parking":{"min": 200,  "max": 400,  "label": "وقوف غير قانوني"}
}


def poisson_sample(lam):
    """Poisson distribution for realistic monthly counts."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= random.random()
        if p < L:
            break
    return k - 1


def run_violations_job(spark, start_date, end_date):
    print(f"🚀 Starting REALISTIC Violations Job: {start_date} → {end_date}")

    # ── 1. Load & Filter Actual Driving Data ──────────────────────────────
    df = spark.read.format("org.apache.spark.sql.cassandra") \
             .options(table="truck_history", keyspace=CASSANDRA_KEYSPACE) \
             .load()

    df_driving = df.filter(
        (col("processed_at") >= start_date) &
        (col("processed_at") < end_date) &
        (col("speed") > 5.0) &
        (col("in_maintenance") == False) &
        (col("refueling") == False)
    )

    # ── 2. Extract Real Speeding Events ───────────────────────────────────
    speeding_events = df_driving.filter(col("speed") > SPEED_LIMIT) \
        .select(
            "truck_id",
            "driver_id", # ADDED driver_id
            col("event_time").alias("violation_date"),
            coalesce(col("start_city"), col("end_city"), lit("Unknown")).alias("city"),
            col("speed")
        )

    # ── 3. Extract Real Driving Days & Cities ─────────────────────────────
    driving_contexts = df_driving.select(
        "truck_id",
        "driver_id", # ADDED driver_id
        date_trunc("day", col("event_time")).alias("violation_date"),
        coalesce(col("start_city"), col("end_city"), lit("Unknown")).alias("city"),
        col("speed")
    ).dropDuplicates(["truck_id", "driver_id", "violation_date", "city"])

    # ── 4. Group by Truck & Driver ────────────────────────────────────────
    speeding_by_truck = speeding_events.groupBy("truck_id", "driver_id").agg(
        collect_list(struct("violation_date", "city", "speed")).alias("speeding_recs")
    )

    driving_by_truck = driving_contexts.groupBy("truck_id", "driver_id").agg(
        collect_list(struct("violation_date", "city", "speed")).alias("driving_recs")
    )

    metrics = speeding_by_truck.join(driving_by_truck, ["truck_id", "driver_id"], "outer").collect()
    print(f"📊 Analyzed {len(metrics)} truck/driver profiles with actual telemetry")

    violations_data = []

    for row in metrics:
        truck_id = row.truck_id
        driver_id = row.driver_id # ADDED driver_id
        speed_recs = row.speeding_recs or []
        drive_recs = row.driving_recs or []

        # ── REALISM: No driving = No violations ──────────────────────────
        if not drive_recs:
            continue

        # ── Risk Calculation based on actual behavior ────────────────────
        total_km_estimate = len(drive_recs) * 2.5
        max_spd = max([r.speed for r in drive_recs], default=0)
        speeding_count = len(speed_recs)

        risk = 1.0
        risk *= min(2.0, 1.0 + (total_km_estimate / 10000))
        if speeding_count > 5:
            risk *= 1.3
        if max_spd > 145:
            risk *= 1.4
        elif max_spd > 130:
            risk *= 1.2

        expected = BASE_LAMBDA * risk
        total_violations = min(poisson_sample(expected), MAX_MONTHLY)

        # Professional driver adjustment
        if total_violations > 2 and random.random() < 0.65:
            total_violations = max(0, total_violations - 2)

        if total_violations == 0:
            continue

        # ── Build Pool of ACTUAL Candidates ──────────────────────────────
        candidates = []
        for s in speed_recs:
            candidates.append({
                "type": "speeding_radar",
                "date": s.violation_date,
                "city": s.city,
                "speed": s.speed
            })
        for d in drive_recs:
            candidates.append({
                "type": "contextual",
                "date": d.violation_date,
                "city": d.city,
                "speed": d.speed
            })

        random.shuffle(candidates)

        # ── Assign Violations (Max 1 per calendar day) ───────────────────
        assigned = []
        seen_dates = set()

        for c in candidates:
            if len(assigned) >= total_violations:
                break
            day_key = str(c["date"])[:10]
            if day_key in seen_dates:
                continue
            seen_dates.add(day_key)

            if c["type"] == "contextual":
                if c["speed"] > 100:
                    c["type"] = random.choice(["red_light", "mobile_phone"])
                else:
                    c["type"] = random.choice(["stop_sign", "illegal_parking"])
            assigned.append(c)

        # ── Generate Final Records with Real Data ────────────────────────
        for v in assigned:
            cfg = VIOLATION_CONFIG[v["type"]]
            fine = round(random.uniform(cfg["min"], cfg["max"]), 2)

            if v["type"] == "speeding_radar":
                details = f"Radar recorded {v['speed']} km/h in {SPEED_LIMIT} zone | {cfg['label']}"
            elif v["type"] == "red_light":
                details = f"Intersection violation at {v['city']} center | {cfg['label']}"
            elif v["type"] == "mobile_phone":
                details = f"Patrol citation on RN near {v['city']} | {cfg['label']}"
            else:
                details = f"Citation issued in {v['city']} | {cfg['label']}"

            violations_data.append({
                "month_year": start_date[:7],
                "truck_id": truck_id,
                "driver_id": driver_id, # ADDED driver_id
                "violation_id": str(uuid.uuid4()),
                "violation_type": v["type"],
                "city": v["city"],
                "fine_mad": fine,
                "violation_date": v["date"],
                "details": details
            })

    # ── 5. Save to Cassandra ──────────────────────────────────────────────
    if not violations_data:
        print("✅ No realistic violations generated (normal for professional fleets)")
        return

    schema = StructType([
        StructField('month_year', StringType(), False), 
        StructField('truck_id', IntegerType(), False), 
        StructField('driver_id', StringType(), False), # ADDED driver_id
        StructField('violation_id', StringType(), False), 
        StructField('violation_type', StringType(), False), 
        StructField('city', StringType(), True), 
        StructField('fine_mad', DoubleType(), False), 
        StructField('violation_date', TimestampType(), False), 
        StructField('details', StringType(), True)
    ])
    df_out = spark.createDataFrame(violations_data, schema)
    df_out = df_out.withColumn('violation_date', df_out['violation_date'].cast('date'))
    print(f"💾 Writing {len(violations_data)} violation records to Cassandra...")

    df_out.write \
        .format("org.apache.spark.sql.cassandra") \
        .mode("append") \
        .options(table="traffic_violations", keyspace=CASSANDRA_KEYSPACE) \
        .save()

    print("✅ REALISTIC Violations Job Completed")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: spark-submit job_traffic_violations.py <start_date> <end_date>")
        sys.exit(1)

    spark = SparkSession.builder \
        .appName("RealisticTrafficViolations") \
        .getOrCreate()

    run_violations_job(spark, sys.argv[1], sys.argv[2])
    spark.stop()

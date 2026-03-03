# backend/app/consumer.py
import json
import os
import time
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

broker = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "truck-gps")

consumer = None
while consumer is None:
    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=broker,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            auto_offset_reset="latest",
            group_id="tracker-group"
        )
        print("✅ Connected to Kafka")
    except NoBrokersAvailable:
        print("⏳ Kafka not ready, retrying in 5s...")
        time.sleep(5)

latest_trucks = {}

def start_consumer():
    for message in consumer:
        data = message.value
        latest_trucks[data["truck_id"]] = data
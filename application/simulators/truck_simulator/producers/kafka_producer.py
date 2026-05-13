import json
import os
import time
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

broker = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "truck-gps")

producer = None
while producer is None:
    try:
        producer = KafkaProducer(
            bootstrap_servers=broker,
            value_serializer=lambda v: json.dumps(v).encode("utf-8")
        )
        print("✅ Connected to Kafka")
    except NoBrokersAvailable:
        print("⏳ Kafka broker not available, retrying in 5s...")
        time.sleep(5)

def send_to_kafka(data):
    producer.send(KAFKA_TOPIC, data)
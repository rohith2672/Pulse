import json
import os
import time
import uuid
import random
from datetime import datetime, timezone

from faker import Faker
from confluent_kafka import Producer


# ----------------------------
# Configuration
# ----------------------------

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "orders")
EVENTS_PER_SECOND = float(os.getenv("EVENTS_PER_SECOND", "5"))

CATEGORIES = [
    "electronics",
    "fashion",
    "home",
    "beauty",
    "sports",
    "books",
    "grocery",
]

fake = Faker()


# ----------------------------
# Utility Functions
# ----------------------------

def current_utc_iso():
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def generate_order_event():
    """Generate a realistic order event."""
    category = random.choice(CATEGORIES)

    return {
        "event_id": str(uuid.uuid4()),
        "order_id": f"ord_{uuid.uuid4().hex[:10]}",
        "user_id": f"usr_{uuid.uuid4().hex[:8]}",
        "product_id": f"prd_{uuid.uuid4().hex[:8]}",
        "category": category,
        "price": round(random.uniform(10.0, 500.0), 2),
        "quantity": random.randint(1, 5),
        "city": fake.city(),
        "event_timestamp": current_utc_iso(),
    }


def delivery_report(err, msg):
    """Delivery callback for Kafka."""
    if err is not None:
        print(f"❌ Delivery failed: {err}")
    # Uncomment below if you want verbose delivery logs
    # else:
    #     print(f"✔ Message delivered to {msg.topic()} [{msg.partition()}]")


# ----------------------------
# Main Producer Logic
# ----------------------------

def main():
    print(f"[Pulse Producer Starting]")
    print(f"Bootstrap Server: {KAFKA_BOOTSTRAP}")
    print(f"Topic: {KAFKA_TOPIC}")
    print(f"Events per second: {EVENTS_PER_SECOND}")
    print("--------------------------------------------------")

    producer = Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "acks": "all",
        "retries": 3,
        "linger.ms": 10,
    })

    delay = 1.0 / EVENTS_PER_SECOND if EVENTS_PER_SECOND > 0 else 0
    sent_count = 0
    start_time = time.time()

    try:
        while True:
            event = generate_order_event()
            key = event["category"]

            producer.produce(
                topic=KAFKA_TOPIC,
                key=key.encode("utf-8"),
                value=json.dumps(event).encode("utf-8"),
                on_delivery=delivery_report,
            )

            producer.poll(0)  # serve delivery callbacks

            sent_count += 1

            if sent_count % 100 == 0:
                elapsed = time.time() - start_time
                rate = sent_count / elapsed if elapsed > 0 else 0
                print(f"Sent {sent_count} events | Avg rate: {rate:.2f} events/sec")

            if delay > 0:
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\nStopping producer...")

    finally:
        producer.flush(10)
        print("Producer closed cleanly.")


if __name__ == "__main__":
    main()
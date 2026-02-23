# Pulse
Pulse is a distributed, real-time event processing engine built using Apache Kafka and Spark Structured Streaming. It ingests high-volume streaming events, performs event-time windowed aggregations with watermarking, and persists fault-tolerant metrics into PostgreSQL for downstream analytics.

🚀 Architecture Overview


Event Producer
→ Kafka Topic (partitioned, scalable ingestion)
→ Spark Structured Streaming
→ Event-Time Windowed Aggregations
→ PostgreSQL Sink
→ Analytics / Monitoring Layer

🎯 Key Features

Distributed event ingestion using Apache Kafka

Partitioned topics for horizontal scalability

Spark Structured Streaming for real-time processing

Event-time processing with watermarking

Sliding and tumbling window aggregations

Persistent metric storage in PostgreSQL

Fully containerized using Docker

Cloud-ready deployment on AWS EC2

Fault-tolerant and replay-capable architecture

🧠 What Pulse Demonstrates

Pulse is not a toy pipeline. It showcases:

Real-time stream processing

Distributed systems principles

Event-time vs processing-time semantics

Late data handling with watermarking

Scalable consumer architecture

Containerized microservice orchestration

Production-style data pipeline design

📊 Example Use Case

Pulse simulates high-volume event streams such as:

E-commerce order transactions

Financial transaction events

IoT telemetry streams

Log processing systems

The engine processes incoming events in real time and computes metrics such as:

Revenue per time window

Event count by category

Regional aggregation

Throughput and latency insights

🛠 Tech Stack

Apache Kafka

Apache Spark (Structured Streaming)

PostgreSQL

Python

Docker & Docker Compose

AWS EC2

📦 Project Structure

producer/
spark-streaming/
database/
docker/
deployment/
README.md

⚡ Scalability & Fault Tolerance

Pulse is designed with:

Kafka partitions for parallel ingestion

Consumer groups for scalable processing

Checkpointing in Spark for fault recovery

Replay capability through offset management

Stateless processing with persistent storage

🌩 Deployment

Pulse can be deployed locally using Docker Compose or in the cloud via AWS EC2. The system is designed to handle high-throughput event streams while maintaining consistent processing guarantees.

💡 Why Pulse?

Modern data platforms depend on real-time event processing. Pulse replicates the architectural foundation used in production systems at fintech, e-commerce, and AI-driven companies.

It is designed as a hands-on implementation of distributed streaming infrastructure rather than a basic tutorial pipeline.

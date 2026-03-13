# Pulse — EC2 Deployment Guide

Deploy the full Pulse streaming pipeline (Zookeeper → Kafka → Spark → PostgreSQL + Producer) on a single AWS EC2 instance using Docker Compose.

---

## 1. Launch EC2 Instance

| Setting | Recommended value |
|---------|------------------|
| AMI | Ubuntu 22.04 LTS |
| Instance type | `t3.medium` (2 vCPU, 4 GB RAM) minimum |
| Storage | 20 GB gp3 EBS |
| Key pair | Your existing key pair |

---

## 2. Configure Security Group (Inbound Rules)

| Port | Protocol | Source | Purpose |
|------|----------|--------|---------|
| 22 | TCP | Your IP | SSH access |
| 9092 | TCP | Your IP | Kafka (external clients) |
| 5432 | TCP | Your IP | PostgreSQL (optional, for direct queries) |

> All other ports can remain closed. Internal service-to-service traffic stays on the Docker bridge network.

---

## 3. Bootstrap the Instance

SSH into the instance and run the setup script:

```bash
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>

# On the EC2 instance:
sudo apt-get install -y git
git clone <repo-url> ~/Pulse
cd ~/Pulse
sudo bash deployment/setup.sh
```

The script installs Docker, Docker Compose, and adds the `ubuntu` user to the `docker` group.

After it completes, **log out and back in** to apply group membership:

```bash
exit
ssh -i your-key.pem ubuntu@<EC2_PUBLIC_IP>
```

---

## 4. Configure Environment

```bash
cd ~/Pulse
cp deployment/.env.example deployment/.env
nano deployment/.env   # or vi, etc.
```

Fill in the two required values:

```dotenv
EC2_PUBLIC_IP=1.2.3.4          # your actual EC2 public IP
POSTGRES_PASSWORD=StrongPass!  # choose a strong password
```

The other defaults (`pulse` / `orders` / `5`) are fine to keep.

---

## 5. Deploy

```bash
bash deployment/deploy.sh
```

The script will:
1. Validate `.env`
2. Pull latest Docker images
3. Build the `spark-job` image
4. Start all 5 services (`zookeeper`, `kafka`, `postgres`, `spark-job`, `producer`)
5. Wait for Postgres to pass its healthcheck
6. Print a status summary and recent Spark logs

---

## 6. Verify the Pipeline

**Check all services are running:**
```bash
bash deployment/manage.sh status
```

**Watch Spark logs (micro-batches every 30 seconds):**
```bash
bash deployment/manage.sh logs spark-job
```

**Watch producer logs:**
```bash
bash deployment/manage.sh logs producer
```

**Query Postgres (data appears after ~11 minutes — watermark delay):**
```bash
docker exec -it pulse-postgres psql -U pulse -d pulse -c \
  "SELECT category, SUM(order_count), ROUND(SUM(total_revenue),2) \
   FROM category_metrics GROUP BY category ORDER BY 2 DESC;"
```

---

## 7. Day-2 Management

```bash
bash deployment/manage.sh start      # start all services
bash deployment/manage.sh stop       # stop all (volumes preserved)
bash deployment/manage.sh restart    # restart all
bash deployment/manage.sh status     # show container states
bash deployment/manage.sh logs       # tail spark-job logs
bash deployment/manage.sh logs kafka # tail a specific service
bash deployment/manage.sh destroy    # stop + wipe all volumes (destructive)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `spark-job` exits on start | Kafka topic not ready yet | `bash deployment/manage.sh restart` after 30s |
| Kafka `InconsistentClusterIdException` | Stale volume from previous run | `bash deployment/manage.sh destroy` then redeploy |
| No data in Postgres after 15 min | Watermark not advanced | Check `manage.sh logs spark-job` for batch output |
| Producer can't connect to Kafka | Wrong `EC2_PUBLIC_IP` in `.env` | Update `.env`, restart producer: `docker compose restart producer` |

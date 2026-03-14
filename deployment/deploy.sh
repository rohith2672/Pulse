#!/usr/bin/env bash
# deploy.sh — provision an EC2 instance and deploy the Pulse pipeline.
# Run this locally. Requires: aws CLI (configured), ssh.
#
# Usage:
#   export REPO_URL=https://github.com/<you>/pulse
#   bash deployment/deploy.sh
#
# Optional env vars:
#   KEY_NAME        existing EC2 key pair name      (default: pulse-key)
#   KEY_FILE        local path to save the .pem      (default: ~/.ssh/pulse-key.pem)
#   INSTANCE_TYPE   EC2 instance type                (default: t3.medium)
#   REGION          AWS region                       (default: us-east-1)
#   BRANCH          git branch to deploy             (default: main)

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
REPO_URL="${REPO_URL:-}"
KEY_NAME="${KEY_NAME:-pulse-key}"
KEY_FILE="${KEY_FILE:-$HOME/.ssh/pulse-key.pem}"
INSTANCE_TYPE="${INSTANCE_TYPE:-t3.medium}"
REGION="${REGION:-us-east-1}"
BRANCH="${BRANCH:-main}"
SG_NAME="pulse-sg"
TAG_NAME="pulse-server"

if [[ -z "${REPO_URL}" ]]; then
  echo "ERROR: Set REPO_URL to your GitHub repo URL before running."
  echo "  export REPO_URL=https://github.com/<you>/pulse"
  exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
aws_cmd() { aws --region "${REGION}" "$@"; }

# ── 1. Key pair ───────────────────────────────────────────────────────────────
if ! aws_cmd ec2 describe-key-pairs --key-names "${KEY_NAME}" &>/dev/null; then
  echo "[deploy] Creating key pair '${KEY_NAME}'..."
  aws_cmd ec2 create-key-pair \
    --key-name "${KEY_NAME}" \
    --query 'KeyMaterial' \
    --output text > "${KEY_FILE}"
  chmod 400 "${KEY_FILE}"
  echo "[deploy] Key saved to ${KEY_FILE}"
else
  echo "[deploy] Key pair '${KEY_NAME}' already exists."
  if [[ ! -f "${KEY_FILE}" ]]; then
    echo "WARNING: ${KEY_FILE} not found locally. Make sure you have the private key."
  fi
fi

# ── 2. Security group ─────────────────────────────────────────────────────────
SG_ID=$(aws_cmd ec2 describe-security-groups \
  --filters "Name=group-name,Values=${SG_NAME}" \
  --query 'SecurityGroups[0].GroupId' \
  --output text 2>/dev/null || echo "None")

if [[ "${SG_ID}" == "None" || -z "${SG_ID}" ]]; then
  echo "[deploy] Creating security group '${SG_NAME}'..."
  SG_ID=$(aws_cmd ec2 create-security-group \
    --group-name "${SG_NAME}" \
    --description "Pulse pipeline security group" \
    --query 'GroupId' \
    --output text)

  # SSH from anywhere (restrict to your IP in production)
  aws_cmd ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol tcp --port 22 --cidr 0.0.0.0/0

  # Kafka external port (optional, remove if not needed)
  aws_cmd ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol tcp --port 9092 --cidr 0.0.0.0/0

  # Postgres (restrict to your IP in production)
  aws_cmd ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol tcp --port 5432 --cidr 0.0.0.0/0

  # Grafana UI
  aws_cmd ec2 authorize-security-group-ingress \
    --group-id "${SG_ID}" --protocol tcp --port 3000 --cidr 0.0.0.0/0

  echo "[deploy] Security group created: ${SG_ID}"
else
  echo "[deploy] Security group '${SG_NAME}' already exists: ${SG_ID}"
fi

# ── 3. AMI — latest Amazon Linux 2023 ────────────────────────────────────────
echo "[deploy] Looking up latest Amazon Linux 2023 AMI..."
AMI_ID=$(aws_cmd ec2 describe-images \
  --owners amazon \
  --filters \
    "Name=name,Values=al2023-ami-2023*-x86_64" \
    "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)
echo "[deploy] Using AMI: ${AMI_ID}"

# ── 4. Launch EC2 instance ────────────────────────────────────────────────────
echo "[deploy] Launching EC2 instance (${INSTANCE_TYPE})..."
INSTANCE_ID=$(aws_cmd ec2 run-instances \
  --image-id "${AMI_ID}" \
  --instance-type "${INSTANCE_TYPE}" \
  --key-name "${KEY_NAME}" \
  --security-group-ids "${SG_ID}" \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${TAG_NAME}}]" \
  --query 'Instances[0].InstanceId' \
  --output text)
echo "[deploy] Instance launched: ${INSTANCE_ID}"

# ── 5. Wait for instance to be running ───────────────────────────────────────
echo "[deploy] Waiting for instance to enter 'running' state..."
aws_cmd ec2 wait instance-running --instance-ids "${INSTANCE_ID}"

PUBLIC_IP=$(aws_cmd ec2 describe-instances \
  --instance-ids "${INSTANCE_ID}" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)
echo "[deploy] Instance running. Public IP: ${PUBLIC_IP}"

# ── 6. Wait for SSH to be ready ───────────────────────────────────────────────
echo "[deploy] Waiting for SSH to become available..."
for i in $(seq 1 30); do
  if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
       -i "${KEY_FILE}" "ec2-user@${PUBLIC_IP}" "echo ok" &>/dev/null; then
    echo "[deploy] SSH ready."
    break
  fi
  echo "  attempt ${i}/30 — retrying in 10s..."
  sleep 10
done

# ── 7. Upload setup script and run it ────────────────────────────────────────
echo "[deploy] Uploading setup.sh..."
scp -o StrictHostKeyChecking=no -i "${KEY_FILE}" \
  deployment/setup.sh "ec2-user@${PUBLIC_IP}:/home/ec2-user/setup.sh"

echo "[deploy] Running setup.sh on the instance..."
ssh -o StrictHostKeyChecking=no -i "${KEY_FILE}" "ec2-user@${PUBLIC_IP}" \
  "REPO_URL='${REPO_URL}' BRANCH='${BRANCH}' bash /home/ec2-user/setup.sh"

# ── 8. Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pulse deployed successfully!"
echo ""
echo "  Instance ID : ${INSTANCE_ID}"
echo "  Public IP   : ${PUBLIC_IP}"
echo ""
echo "  SSH in:"
echo "    ssh -i ${KEY_FILE} ec2-user@${PUBLIC_IP}"
echo ""
echo "  Check service logs:"
echo "    ssh -i ${KEY_FILE} ec2-user@${PUBLIC_IP} \\"
echo "      'cd /opt/pulse && docker compose logs -f'"
echo ""
echo "  IMPORTANT: update /opt/pulse/.env with a strong POSTGRES_PASSWORD,"
echo "  then restart: docker compose -f docker-compose.yml -f deployment/docker-compose.prod.yml restart"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

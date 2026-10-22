#!/usr/bin/env bash
# Copy the app to the EC2 instance and (re)start it.
#   HOST=ec2-1-2-3-4.compute-1.amazonaws.com ./deploy/deploy.sh
# First time only, also copy the env file:   ENV_FILE=./pillow.env HOST=... ./deploy/deploy.sh
set -euo pipefail
: "${HOST:?set HOST to the instance public DNS name}"
KEY="${KEY:-$HOME/.ssh/pillow_deploy}"
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new "ec2-user@$HOST")
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

(cd "$ROOT/frontend" && npm ci --silent && npm run build --silent)

"${SSH[@]}" 'sudo mkdir -p /opt/pillow/src /opt/pillow/web/dist && sudo chown -R ec2-user /opt/pillow'
rsync -az --delete -e "ssh -i $KEY" "$ROOT/src/" "ec2-user@$HOST:/opt/pillow/src/"
rsync -az --delete -e "ssh -i $KEY" "$ROOT/web/dist/" "ec2-user@$HOST:/opt/pillow/web/dist/"
rsync -az -e "ssh -i $KEY" "$ROOT/deploy/requirements-server.txt" "$ROOT/deploy/pillow.service" "ec2-user@$HOST:/opt/pillow/"
if [ -n "${ENV_FILE:-}" ]; then
  rsync -az -e "ssh -i $KEY" "$ENV_FILE" "ec2-user@$HOST:/tmp/pillow.env"
  "${SSH[@]}" 'sudo install -m 600 -o root -g root /tmp/pillow.env /etc/pillow.env && rm /tmp/pillow.env'
fi

"${SSH[@]}" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /opt/pillow
if ! command -v python3.11 >/dev/null; then sudo dnf install -y -q python3.11 python3.11-pip; fi
[ -d venv ] || python3.11 -m venv venv
venv/bin/pip install -q --no-cache-dir -r requirements-server.txt
sudo install -m 644 pillow.service /etc/systemd/system/pillow.service
sudo systemctl daemon-reload
sudo systemctl enable --now pillow
sudo systemctl restart pillow
sleep 3
curl -fsS http://127.0.0.1/api/health | head -c 300; echo
REMOTE
echo "Deployed. Check:  curl http://$HOST/api/health"

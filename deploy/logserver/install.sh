#!/usr/bin/env bash
# Install the aion2calc log server on Ubuntu 22.04 / 24.04 (run as root or with sudo).
#   sudo bash install.sh logs.example.com
set -euo pipefail
DOMAIN="${1:?usage: install.sh <domain>}"
REPO="${REPO:-https://github.com/sam-t-anderson/Aion-calc}"

apt-get update
apt-get install -y python3 python3-venv git nginx certbot python3-certbot-nginx

id a2logs >/dev/null 2>&1 || useradd --system --home /var/lib/aion2calc-logs --shell /usr/sbin/nologin a2logs
install -d -o a2logs -g a2logs /var/lib/aion2calc-logs
if [ -d /opt/aion2calc/.git ]; then git -C /opt/aion2calc pull --ff-only; else git clone "$REPO" /opt/aion2calc; fi
python3 -m venv /opt/aion2calc/venv
/opt/aion2calc/venv/bin/pip install --upgrade pip
/opt/aion2calc/venv/bin/pip install /opt/aion2calc

sed "s#https://logs.example.com#https://$DOMAIN#" /opt/aion2calc/deploy/logserver/aion2calc-logs.service \
  > /etc/systemd/system/aion2calc-logs.service
sed "s#logs.example.com#$DOMAIN#g" /opt/aion2calc/deploy/logserver/nginx.conf > /etc/nginx/sites-available/aion2calc-logs
ln -sf /etc/nginx/sites-available/aion2calc-logs /etc/nginx/sites-enabled/aion2calc-logs
systemctl daemon-reload
systemctl enable --now aion2calc-logs
nginx -t && systemctl reload nginx
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --register-unsafely-without-email --redirect || \
  echo "certbot failed: point the domain's DNS at this server, then run: certbot --nginx -d $DOMAIN"

echo
echo "Create an upload key:"
echo "  sudo -u a2logs A2LOGS_DATA=/var/lib/aion2calc-logs /opt/aion2calc/venv/bin/python -m aion2calc.logserver keys create \"my uploads\""
echo "Then open https://$DOMAIN/docs"

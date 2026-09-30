#!/usr/bin/env bash
# Installe l'API catering sur le Raspberry Pi (étapes 2 et 3 du guide).
# À lancer depuis le dossier du dépôt : bash deploy/install_pi.sh
set -euo pipefail
cd "$(dirname "$0")/.."
APP_DIR="$PWD"

echo "==> Paquets système"
sudo apt update
sudo apt install -y python3-venv python3-pip chromium

echo "==> Environnement Python"
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install --with-deps chromium \
  || echo "ATTENTION : playwright install a échoué, utiliser /usr/bin/chromium (voir le guide)."

echo "==> Fichier .env"
if [ ! -f .env ]; then
  cp .env.example .env
  chmod 600 .env
  echo "Renseigner API_KEY dans $APP_DIR/.env (nano .env), puis relancer ce script."
  exit 1
fi
chmod 600 .env

if [ ! -f storage_state.json ]; then
  echo "ATTENTION : storage_state.json absent. Le générer sur un PC (python scripts/generer_cookies.py) puis le copier ici."
fi

echo "==> Service systemd"
sed -e "s#/home/pi/catering-api#$APP_DIR#g" -e "s#^User=pi#User=$USER#" deploy/catering-api.service \
  | sudo tee /etc/systemd/system/catering-api.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now catering-api
sudo systemctl restart catering-api

sleep 3
if curl -fsS http://127.0.0.1:8000/docs > /dev/null; then
  echo "OK : l'API répond sur http://127.0.0.1:8000"
else
  echo "L'API ne répond pas encore. Voir : journalctl -u catering-api -n 50"
fi

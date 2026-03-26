#!/usr/bin/env bash
# Delphi Press — Quick Deploy on Ubuntu VPS
# Usage: curl -sSL <raw-url> | bash
# Or: ssh deploy@YOUR_VPS && bash scripts/deploy.sh
set -euo pipefail

REPO_URL="https://github.com/Antopkin/delphi-press.git"
APP_DIR="$HOME/apps/delphi-press"

echo "=== Delphi Press Deploy ==="

# 1. Install Docker (if missing)
if ! command -v docker &>/dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker "$USER"
    echo "Docker installed. Re-login or run: newgrp docker"
fi

# 2. Clone or update repo
if [ -d "$APP_DIR" ]; then
    echo "Updating existing installation..."
    cd "$APP_DIR"
    git pull origin main
else
    echo "Cloning repository..."
    mkdir -p "$(dirname "$APP_DIR")"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# 3. Setup .env
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate SECRET_KEY
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))" 2>/dev/null || openssl rand -base64 48)
    sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/" .env
    # Generate REDIS_PASSWORD
    REDIS_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))" 2>/dev/null || openssl rand -base64 32)
    sed -i "s/^REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASS/" .env
    echo ""
    echo ">>> .env created with generated secrets."
    echo ">>> Edit .env to add API keys:"
    echo ">>>   nano $APP_DIR/.env"
    echo ""
fi

# 4. Create data directory
mkdir -p data

# 5. Build and start
echo "Building containers..."
docker compose build

echo "Starting services..."
docker compose up -d

echo ""
echo "=== Deploy complete ==="
echo "Services: $(docker compose ps --format '{{.Name}}: {{.Status}}' | tr '\n' ' ')"
echo ""
echo "Next steps:"
echo "  1. Edit .env with your API keys: nano $APP_DIR/.env"
echo "  2. Setup SSL: see docs/10-deployment.md"
echo "  3. Restart after .env changes: docker compose restart"
echo "  4. View logs: docker compose logs -f --tail=50"

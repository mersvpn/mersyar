#!/bin/bash
set -e

# --- Helper Functions for Colors ---
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
success() { echo -e "\e[32m[SUCCESS]\e[0m $1"; }
error() { echo -e "\e[31m[ERROR]\e[0m $1"; }
warning() { echo -e "\e[33m[WARN]\e[0m $1"; }

# --- Pre-flight Checks ---
if [ "$(id -u)" -ne 0 ]; then
    error "This script must be run as root. Use 'sudo' or run as root."
    exit 1
fi

# --- Static Config ---
GITHUB_USER="mersvpn"
GITHUB_REPO="mersyar-bot"

info "Fetching latest release info..."
LATEST_TAG=$(wget -qO- "https://api.github.com/repos/$GITHUB_USER/$GITHUB_REPO/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
if [ -z "$LATEST_TAG" ]; then
    error "Could not fetch latest release tag."
    exit 1
fi
DOWNLOAD_URL="https://github.com/$GITHUB_USER/$GITHUB_REPO/archive/refs/tags/$LATEST_TAG.tar.gz"

info "==============================================="
info "      Mersyar-Bot Universal Installer"
info "Latest Version: $LATEST_TAG"

PROJECT_DIR="/root/$GITHUB_REPO"
SERVICE_NAME="mersyar-bot"
PYTHON_ALIAS="python3"
TARBALL_NAME="${LATEST_TAG}.tar.gz"
DB_NAME="mersyar_bot_db"
DB_USER="mersyar"
DB_PASSWORD_DISPLAY=""

# --- Interactive User Input ---
if [ ! -f "$PROJECT_DIR/.env" ]; then
    read -p "Enter Domain/Subdomain (e.g., bot.example.com): " DOMAIN
    read -p "Enter email for SSL notifications: " ADMIN_EMAIL
    echo "---"
    read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
    read -p "Enter Telegram Admin User ID: " AUTHORIZED_USER_IDS
    read -p "Enter Support Username (optional): " SUPPORT_USERNAME
    read -p "Enter Bot Port (default 8081, press Enter to use): " BOT_PORT
    BOT_PORT=${BOT_PORT:-8081}
else
    info "Existing .env found. Skipping user input for credentials."
    DOMAIN=$(grep -E "^BOT_DOMAIN=" "$PROJECT_DIR/.env" | cut -d '=' -f2- | tr -d '"')
    BOT_PORT=$(grep -E "^BOT_PORT=" "$PROJECT_DIR/.env" | cut -d '=' -f2- | tr -d '"')
    ADMIN_EMAIL="info@$DOMAIN"
fi

info "✅ Starting installation/update..."
sleep 1

# --- 1. Update system & install dependencies ---
info "[1/9] Installing dependencies..."
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y wget tar $PYTHON_ALIAS-pip $PYTHON_ALIAS-venv nginx mysql-server python3-certbot-nginx \
phpmyadmin php-fpm php-mysql php-mbstring php-zip php-gd php-json php-curl

# --- 2. Download & extract release ---
info "[2/9] Downloading release $LATEST_TAG..."
wget -q "$DOWNLOAD_URL" -O "/tmp/$TARBALL_NAME"

if [ -d "$PROJECT_DIR" ]; then
    info "[3/9] Updating existing installation..."
else
    info "[3/9] Fresh install..."
    mkdir -p "$PROJECT_DIR"
fi

tar -xzf "/tmp/$TARBALL_NAME" --strip-components=1 -C "$PROJECT_DIR"
rm -f "/tmp/$TARBALL_NAME"
cd "$PROJECT_DIR" || { error "Cannot cd to $PROJECT_DIR"; exit 1; }

# --- 3. Setup DB & .env ---
if [ ! -f ".env" ]; then
    info "-> Setting up MySQL..."
    DB_PASSWORD=$(openssl rand -base64 18 | tr -dc 'a-zA-Z0-9' | head -c 16)
    
    # ✨ NEW: Bulletproof MySQL connection logic ✨
    MYSQL_CMD="sudo mysql" # Default command for standard servers
    if [ -f /root/.my.cnf ]; then
        info "   -> Found /root/.my.cnf. Using credentials from this file for setup."
        MYSQL_CMD="mysql --defaults-extra-file=/root/.my.cnf"
    else
        info "   -> No /root/.my.cnf found. Using standard 'sudo mysql' connection."
    fi

    # Use the determined command for all MySQL operations
    $MYSQL_CMD -e "CREATE DATABASE IF NOT EXISTS $DB_NAME;"
    $MYSQL_CMD -e "CREATE USER IF NOT EXISTS '$DB_USER'@'localhost' IDENTIFIED WITH mysql_native_password BY '$DB_PASSWORD';"
    $MYSQL_CMD -e "GRANT ALL PRIVILEGES ON $DB_NAME.* TO '$DB_USER'@'localhost';"
    $MYSQL_CMD -e "FLUSH PRIVILEGES;"

    info "-> Creating .env..."
    WEBHOOK_SECRET_TOKEN=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 32)
    cat << EOF > .env
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
AUTHORIZED_USER_IDS="${AUTHORIZED_USER_IDS}"
SUPPORT_USERNAME="${SUPPORT_USERNAME}"
BOT_DOMAIN="${DOMAIN}"
WEBHOOK_SECRET_TOKEN="${WEBHOOK_SECRET_TOKEN}"
BOT_PORT="${BOT_PORT}"
DB_HOST="localhost"
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_PASSWORD="${DB_PASSWORD}"
EOF
    DB_PASSWORD_DISPLAY="$DB_PASSWORD"
fi

# --- 4. Python venv ---
info "[4/9] Setting up Python virtualenv..."
$PYTHON_ALIAS -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# --- 5. phpMyAdmin ---
info "[5/9] Configuring phpMyAdmin..."
ln -s -f /usr/share/phpmyadmin /var/www/html/phpmyadmin
PHP_FPM_SOCK=$(ls /var/run/php/php*-fpm.sock | head -n 1)

# --- 6. Nginx & SSL ---
info "[6/9] Configuring Nginx & SSL..."
if [ ! -f "/etc/nginx/sites-available/$SERVICE_NAME" ]; then
cat << EOF > /etc/nginx/sites-available/$SERVICE_NAME
server {
    listen 80; server_name $DOMAIN; root /var/www/html;
    location /.well-known/acme-challenge/ { allow all; }
    location /phpmyadmin { index index.php; location ~ \.php\$ { include snippets/fastcgi-php.conf; fastcgi_pass unix:${PHP_FPM_SOCK}; } }
    location / { 
        proxy_pass http://127.0.0.1:${BOT_PORT}; 
        proxy_set_header Host \$host; 
        proxy_set_header X-Real-IP \$remote_addr; 
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for; 
    }
}
EOF
    ln -s -f /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
    systemctl restart nginx
    certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos --email "$ADMIN_EMAIL" --redirect
else
    info "Nginx config exists. Skipping creation."
    certbot renew --quiet
fi

# --- 7. systemd service ---
info "[7/9] Creating service..."
cat << EOF > /etc/systemd/system/$SERVICE_NAME.service
[Unit]
Description=$SERVICE_NAME Telegram Bot Service
After=network.target mysql.service
[Service]
Type=simple
User=root
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/python3 $PROJECT_DIR/bot.py --port ${BOT_PORT}
Restart=on-failure
RestartSec=10
[Install]
WantedBy=multi-user.target
EOF

# --- 8. CLI Tool ---
info "[8/9] Installing CLI tool..."
if [ -f "mersyar" ]; then
    chmod +x "mersyar"
    ln -sf "$PROJECT_DIR/mersyar" /usr/local/bin/mersyar
    success "'mersyar' tool installed successfully."
else
    warning "'mersyar' script not found. Skipping CLI install."
fi

# --- 9. Finalizing ---
info "[9/9] Finalizing..."

# --- START OF INTELLIGENT MIGRATION LOGIC ---
info "-> Applying database migrations..."
cd "$PROJECT_DIR"
source venv/bin/activate

# Try to run the upgrade.
if alembic upgrade head; then
    # If it succeeds, everything is fine (new install or normal update).
    success "-> Database migrated to the latest version."
else
    # If it fails, it's likely due to an inconsistent history during an update.
    warning "-> Initial migration failed. This can happen after a major update."
    info "-> Attempting to automatically resolve migration history..."
    
    # Step A: Get the latest revision ID from the code.
    LATEST_REVISION_ID=$(alembic heads | awk '{print $1}')
    
    if [ -z "$LATEST_REVISION_ID" ]; then
        error "-> Could not determine the latest revision ID from the code. Aborting."
    else
        info "-> Latest revision ID found in code: ${LATEST_REVISION_ID}"
        info "-> Stamping the database with this version to resolve inconsistencies..."
        
        # Step B: Stamp the database with the latest revision from the code.
        if alembic stamp "$LATEST_REVISION_ID"; then
            info "-> Database stamped successfully. Re-running upgrade..."
            
            # Step C: Try upgrading again. This time it should work.
            if alembic upgrade head; then
                success "-> Database migrations applied successfully after stamping."
            else
                error "-> FATAL: Migration failed even after stamping. Manual intervention required."
            fi
        else
            error "-> FATAL: Failed to stamp the database. Manual intervention required."
        fi
    fi
fi

deactivate
# --- END OF INTELLIGENT MIGRATION LOGIC ---

systemctl daemon-reload
systemctl enable $SERVICE_NAME
systemctl restart $SERVICE_NAME

# --- 🔵 Installation Summary ---
if [ -n "$DB_PASSWORD_DISPLAY" ]; then
    success "==============================================="
    success "✅✅✅ Installation Complete! ✅✅✅"
    success "📋 Summary:"
    echo -e "\e[36m🌐 Bot Domain:\e[0m https://$DOMAIN"
    echo -e "\e[36m🔑 phpMyAdmin:\e[0m https://$DOMAIN/phpmyadmin"
    echo -e "\e[36m🗄 Database Name:\e[0m $DB_NAME"
    echo -e "\e[36m👤 Database User:\e[0m $DB_USER"
    echo -e "\e[36m🔒 Database Password:\e[0m $DB_PASSWORD_DISPLAY"
    echo -e "\e[36m🚀 Bot Port:\e[0m $BOT_PORT"
    success "==============================================="
    info "Use 'mersyar' to manage bot."
    info "Check bot status: systemctl status $SERVICE_NAME"
fi
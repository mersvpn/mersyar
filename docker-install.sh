#!/bin/bash
set -e

# --- Helper Functions for Colors ---
info() { echo -e "\e[34m[INFO]\e[0m $1"; }
success() { echo -e "\e[32m[SUCCESS]\e[0m $1"; }
error() { echo -e "\e[31m[ERROR]\e[0m $1"; }
warning() { echo -e "\e[33m[WARN]\e[0m $1"; }

# --- Static Config ---
PROJECT_DIR="/root/mersyar-docker"
CLI_COMMAND_PATH="/usr/local/bin/mersyar"

# ==============================================================================
#                      --- NEW FEATURE --- BACKUP LOGIC (FULLY AUTOMATED)
# ==============================================================================
setup_backup_job() {
    cd "$PROJECT_DIR"
    info "--- Automated Backup Setup ---"
    warning "This will schedule a periodic backup of your database and .env file."

    local DB_CONTAINER_NAME="mersyar-db"
    local DB_NAME_INTERNAL="mersyar_bot_db"

    read -p "Enter backup interval in minutes (e.g., 1440 for daily, 120 for every 2 hours): " INTERVAL
    read -p "Enter the Telegram Bot Token for sending backups: " BACKUP_BOT_TOKEN
    read -p "Enter the destination Telegram Channel/Chat ID: " BACKUP_CHAT_ID

    if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -eq 0 ]]; then
        error "Interval must be a positive number."
        return 1
    fi

    local cron_schedule
    if (( INTERVAL >= 1440 && INTERVAL % 1440 == 0 )); then
        local DAYS=$((INTERVAL / 1440))
        cron_schedule="0 0 */${DAYS} * *"
        info "Scheduling a backup every ${DAYS} day(s) at midnight."
    elif (( INTERVAL >= 60 && INTERVAL % 60 == 0 )); then
        local HOURS=$((INTERVAL / 60))
        cron_schedule="0 */${HOURS} * * *"
        info "Scheduling a backup every ${HOURS} hour(s)."
    elif (( INTERVAL < 60 )); then
        cron_schedule="*/${INTERVAL} * * * *"
        info "Scheduling a backup every ${INTERVAL} minute(s)."
    else
        error "Invalid interval. For intervals of 60 minutes or more, use multiples of 60."
        return 1
    fi

    info "Creating the backup script (backup_script.sh)..."
    
    cat << EOF > "${PROJECT_DIR}/backup_script.sh"
#!/bin/bash
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

BOT_TOKEN="${BACKUP_BOT_TOKEN}"
CHAT_ID="${BACKUP_CHAT_ID}"
PROJECT_DIR="${PROJECT_DIR}"
DB_CONTAINER="${DB_CONTAINER_NAME}"
DB_NAME="${DB_NAME_INTERNAL}"

TIMESTAMP=\$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILENAME="mersyar_backup_\${TIMESTAMP}.tar.gz"
SQL_FILENAME="\${DB_NAME}_\${TIMESTAMP}.sql"

cd "\$PROJECT_DIR" || exit 1

DB_ROOT_PASSWORD=\$(docker exec "\$DB_CONTAINER" printenv MYSQL_ROOT_PASSWORD | tr -d '\r')

if [ -z "\$DB_ROOT_PASSWORD" ]; then
    curl -s "https://api.telegram.org/bot\$BOT_TOKEN/sendMessage" -d "chat_id=\$CHAT_ID" -d "text=❌ Backup Failed: Could not get DB password." >/dev/null
    exit 1
fi

if docker exec -e MYSQL_PWD="\$DB_ROOT_PASSWORD" "\$DB_CONTAINER" mysqldump -u root "\$DB_NAME" > "\$SQL_FILENAME"; then
    echo "Database dump successful."
else
    curl -s "https://api.telegram.org/bot\$BOT_TOKEN/sendMessage" -d "chat_id=\$CHAT_ID" -d "text=❌ Backup Failed: mysqldump error." >/dev/null
    rm -f "\$SQL_FILENAME"
    exit 1
fi

tar -czf "\$BACKUP_FILENAME" "\$SQL_FILENAME" .env

CAPTION="📦 Backup: \${DB_NAME}
📅 Date: \${TIMESTAMP}
✅ Status: Automatic"

HTTP_CODE=\$(curl -s -o /dev/null -w "%{http_code}" \
    -F "chat_id=\$CHAT_ID" \
    -F "document=@\$BACKUP_FILENAME" \
    -F "caption=\$CAPTION" \
    "https://api.telegram.org/bot\$BOT_TOKEN/sendDocument")

rm -f "\$SQL_FILENAME" "\$BACKUP_FILENAME"
EOF

    chmod +x "${PROJECT_DIR}/backup_script.sh"

    info "Scheduling the cron job..."
    EXISTING_CRON=$(crontab -l 2>/dev/null || true)
    CLEAN_CRON=$(echo "$EXISTING_CRON" | grep -v "mersyar_backup" || true)
    NEW_JOB="${cron_schedule} /bin/bash ${PROJECT_DIR}/backup_script.sh >> ${PROJECT_DIR}/backup.log 2>&1 # mersyar_backup"
    
    if [ -z "$CLEAN_CRON" ]; then
        echo "$NEW_JOB" | crontab -
    else
        echo -e "${CLEAN_CRON}\n${NEW_JOB}" | crontab -
    fi

    if crontab -l | grep -q "mersyar_backup"; then
        success "Backup job successfully added to Cron!"
    else
        error "Failed to add job to Cron."
        return 1
    fi
    
    read -p "Do you want to run a test backup now? (y/n): " RUN_TEST
    if [[ "$RUN_TEST" == "y" ]]; then
        info "Running test backup..."
        /bin/bash "${PROJECT_DIR}/backup_script.sh"
    fi
}
# ==============================================================================
#                              MANAGEMENT MENU
# ==============================================================================
manage_bot() {
    
    show_menu() {
       echo -e "\n--- Mersyar Bot Docker Manager ---"
       echo " 1) View Bot Logs (Live)"
       echo " 2) Restart Bot"
       echo " 3) Stop Bot & All Services"
       echo " 4) Start Bot & All Services"
       echo " 5) Update Bot (from GitHub Latest Release)"
       echo " 6) Re-run Installation / Change Settings"
       echo " 7) Configure Automated Backups"
       echo " 8) Exit"
       echo "------------------------------------"
       read -p "Select an option [1-8]: " option
       handle_option "$option"
    }

    handle_option() {
       cd "$PROJECT_DIR"
       case $1 in
           1)
               info "Tailing logs for mersyar. Press Ctrl+C to exit."
               docker compose logs -f bot
               show_menu
               ;;
           2)
               info "Restarting mersyar container..."
               if docker compose restart bot; then success "Bot restarted."; else error "Failed to restart bot."; fi
               show_menu
               ;;
           3)
               info "Stopping all services..."
               if docker compose down; then success "All services stopped."; else error "Failed to stop services."; fi
               show_menu
               ;;
           4)
               info "Starting all services..."
               if docker compose up -d; then success "All services started."; else error "Failed to start services."; fi
               show_menu
               ;;
            5)
                info "Updating bot system..."
                docker compose down
                docker builder prune -f >/dev/null 2>&1
                
                GITHUB_USER="mersvpn"
                GITHUB_REPO="mersyar"
                LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
                if [ -z "$LATEST_TAG" ]; then
                    git pull origin main || echo "Git pull failed..."
                else
                    wget -q "https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/tags/${LATEST_TAG}.tar.gz" -O latest.tar.gz
                    tar -xzf latest.tar.gz --strip-components=1 --exclude='.env' --overwrite
                    rm latest.tar.gz
                fi
                
                if [ -f entrypoint.sh ]; then chmod +x entrypoint.sh; fi
                
                info "Building new image..."
                if ! docker compose build --no-cache bot; then
                    error "Failed to build image. Aborting."
                    docker compose up -d
                    show_menu; return
                fi
                
                info "Starting services..."
                if docker compose up -d; then
                    success "Containers started!"
                    info "Running database migrations..."
                    sleep 5
                    if ! docker compose exec -T bot alembic upgrade head; then
                        warning "Migration failed, attempting auto-repair..."
                        LATEST_ID=$(docker compose exec -T bot alembic heads | awk '{print $1}')
                        docker compose exec -T bot alembic stamp "$LATEST_ID"
                        docker compose exec -T bot alembic upgrade head
                    fi
                    success "Update Complete!"
                else
                    error "Failed to start services."
                fi
                show_menu
                ;;
           6)
               warning "This will re-run the full installation process."
               read -p "Are you sure you want to continue? (y/n): " confirm
               if [[ "$confirm" == "y" ]]; then
                   bash "$CLI_COMMAND_PATH" --force-install
               else
                   show_menu
               fi
               ;;
           7)
               setup_backup_job
               show_menu
               ;;
           8)
               echo "Exiting."
               exit 0
               ;;
           *)
               error "Invalid option."
               show_menu
               ;;
       esac
    }
    show_menu
} 

# ==============================================================================
#                              INSTALLATION LOGIC
# ==============================================================================
install_bot() {
    info "==============================================="
    info "      mersyar Docker Installer"
    info "==============================================="

    info "[1/7] Checking for dependencies..."
    if ! command -v docker &> /dev/null; then
        warning "Docker not found. Installing..."
        curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh && rm get-docker.sh
    fi
    if ! docker compose version &> /dev/null; then
        apt-get update -y > /dev/null && apt-get install -y docker-compose-plugin > /dev/null
    fi

    info "[2/7] Gathering information..."
    read -p "Enter your Domain/Subdomain (e.g., bot.yourdomain.com): " BOT_DOMAIN
    read -p "Enter your email for SSL notifications: " ADMIN_EMAIL
    echo "---"
    read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
    read -p "Enter Telegram Admin User ID: " AUTHORIZED_USER_IDS
    read -p "Enter Support Username (optional): " SUPPORT_USERNAME

    info "[3/7] Creating project structure at $PROJECT_DIR..."
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    if [ -f .env ]; then
        DB_ROOT_PASSWORD=$(grep DB_ROOT_PASSWORD .env | cut -d '=' -f2 | tr -d '"')
        DB_PASSWORD=$(grep DB_PASSWORD .env | cut -d '=' -f2 | tr -d '"')
    else
        DB_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
        DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
    fi
    WEBHOOK_SECRET_TOKEN=$(openssl rand -hex 32)

    info "-> Creating .env file..."
    cat << EOF > .env
# --- Telegram Bot Settings ---
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
AUTHORIZED_USER_IDS="${AUTHORIZED_USER_IDS}"
SUPPORT_USERNAME="${SUPPORT_USERNAME}"
# --- Webhook Settings ---
BOT_DOMAIN="${BOT_DOMAIN}"
WEBHOOK_SECRET_TOKEN="${WEBHOOK_SECRET_TOKEN}"
# FORCE PORT 8081 & LISTEN ON ALL INTERFACES
BOT_PORT=8081
WEBHOOK_PORT=8081
WEBHOOK_LISTEN="0.0.0.0"
# --- Database Settings ---
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
DB_NAME="mersyar_bot_db"
DB_USER="mersyar"
DB_PASSWORD="${DB_PASSWORD}"
DB_HOST="db"
ADMIN_EMAIL="${ADMIN_EMAIL}"
EOF

    info "Downloading source code..."
    GITHUB_USER="mersvpn"
    GITHUB_REPO="mersyar"
    LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -z "$LATEST_TAG" ]; then
        git clone "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git" . || echo "Repo exists."
    else
        wget -q "https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/tags/${LATEST_TAG}.tar.gz" -O latest.tar.gz
        tar -xzf latest.tar.gz --strip-components=1
        rm latest.tar.gz
    fi

    info "-> Creating docker-compose.yml..."
    cat << 'EOF' > docker-compose.yml
services:
  bot:
    build: .
    container_name: mersyar
    restart: unless-stopped
    ports:
      - "127.0.0.1:8081:8081"
    env_file:
      - .env
    networks:
      - mersyar-net
    depends_on:
      db:
        condition: service_healthy
  db:
    image: mysql:8.0
    container_name: mersyar-db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
    volumes:
      - mysql_data:/var/lib/mysql
    networks:
      - mersyar-net
    healthcheck:
      test: ["CMD", "mysqladmin" ,"ping", "-h", "localhost", "-u", "root", "-p${DB_ROOT_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
  phpmyadmin:
    image: phpmyadmin/phpmyadmin
    container_name: mersyar-pma
    restart: unless-stopped
    environment:
      PMA_HOST: db
      PMA_PORT: 3306
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD}
    ports:
      - "127.0.0.1:8082:80"
    networks:
      - mersyar-net
    depends_on:
      db:
        condition: service_healthy
networks:
  mersyar-net:
    driver: bridge
volumes:
  mysql_data:
EOF

    info "[4/7] Building and starting Docker..."
    docker compose up --build -d --force-recreate

    info "Waiting for bot..."
    sleep 10
    
    info "Running migrations..."
    docker compose exec -T bot alembic upgrade head || true

    # ==============================================================================
    #                      --- ROBUST NGINX/SSL SETUP ---
    # ==============================================================================
    info "[5/7] Configuring SSL & Nginx..."
    
    if ! command -v certbot &> /dev/null; then 
        apt-get update -y && apt-get install -y certbot python3-certbot-nginx
    fi
    if ! command -v nginx &> /dev/null; then apt-get install -y nginx; fi

    # 1. Stop Nginx to free port 80 for standalone Certbot
    systemctl stop nginx || true
    
    info "Obtaining Certificate (Standalone Mode)..."
    if certbot certonly --standalone -d "${BOT_DOMAIN}" --non-interactive --agree-tos --email "${ADMIN_EMAIL}"; then
        success "SSL certificate obtained!"
    else
        error "Failed to obtain SSL. Check DNS settings."
        exit 1
    fi
    
    # 2. Create Nginx Config (Hardcoded Port 8081)
    NGINX_CONF="/etc/nginx/sites-available/mersyar"
    cat << EOF > "$NGINX_CONF"
server {
    listen 80;
    server_name ${BOT_DOMAIN};
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name ${BOT_DOMAIN};
    
    ssl_certificate /etc/letsencrypt/live/${BOT_DOMAIN}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/${BOT_DOMAIN}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 90;
        proxy_connect_timeout 90;
    }
}
EOF

    # 3. Enable Config
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default
    
    # 4. Start Nginx
    systemctl start nginx
    systemctl reload nginx

    info "[7/7] Finalizing..."
    cp "$0" "$CLI_COMMAND_PATH"
    chmod +x "$CLI_COMMAND_PATH"
    
    success "Installation Complete! Access via https://${BOT_DOMAIN}"
    info "You can now run 'mersyar' to manage the bot."
}

# ==============================================================================
#                                 MAIN LOGIC
# ==============================================================================
if [[ "$1" == "--force-install" ]]; then
    install_bot
    exit 0
fi

if [[ -f "$CLI_COMMAND_PATH" && -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    manage_bot "$@"
else
    install_bot
fi
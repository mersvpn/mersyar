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

    # Force using the correct container name and DB name
    local DB_CONTAINER_NAME="mersyar-db"
    local DB_NAME_INTERNAL="mersyar_bot_db"

    read -p "Enter backup interval in minutes (e.g., 1440 for daily, 120 for every 2 hours): " INTERVAL
    read -p "Enter the Telegram Bot Token for sending backups: " BACKUP_BOT_TOKEN
    read -p "Enter the destination Telegram Channel/Chat ID: " BACKUP_CHAT_ID

    if ! [[ "$INTERVAL" =~ ^[0-9]+$ ]] || [[ "$INTERVAL" -eq 0 ]]; then
        error "Interval must be a positive number."
        return 1
    fi

    # Calculate Cron Schedule
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
    
    # --- FIXED BACKUP SCRIPT CONTENT WITH AUTO PATH INJECTION ---
    cat << EOF > "${PROJECT_DIR}/backup_script.sh"
#!/bin/bash
# Script Version: 4.0 - Fully Automated

# 0. INJECT SYSTEM PATHS (Crucial for Cron execution)
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

# 1. Configuration
BOT_TOKEN="${BACKUP_BOT_TOKEN}"
CHAT_ID="${BACKUP_CHAT_ID}"
PROJECT_DIR="${PROJECT_DIR}"
DB_CONTAINER="${DB_CONTAINER_NAME}"
DB_NAME="${DB_NAME_INTERNAL}"

# 2. Setup Variables
TIMESTAMP=\$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILENAME="mersyar_backup_\${TIMESTAMP}.tar.gz"
SQL_FILENAME="\${DB_NAME}_\${TIMESTAMP}.sql"

cd "\$PROJECT_DIR" || exit 1

# 3. Get DB Root Password dynamically
DB_ROOT_PASSWORD=\$(docker exec "\$DB_CONTAINER" printenv MYSQL_ROOT_PASSWORD | tr -d '\r')

if [ -z "\$DB_ROOT_PASSWORD" ]; then
    echo "Error: Could not retrieve MYSQL_ROOT_PASSWORD from container."
    curl -s "https://api.telegram.org/bot\$BOT_TOKEN/sendMessage" -d "chat_id=\$CHAT_ID" -d "text=❌ Backup Failed: Could not get DB password." >/dev/null
    exit 1
fi

# 4. Perform Dump
echo "Dumping database..."
if docker exec -e MYSQL_PWD="\$DB_ROOT_PASSWORD" "\$DB_CONTAINER" mysqldump -u root "\$DB_NAME" > "\$SQL_FILENAME"; then
    echo "Database dump successful."
else
    echo "Database dump failed."
    curl -s "https://api.telegram.org/bot\$BOT_TOKEN/sendMessage" -d "chat_id=\$CHAT_ID" -d "text=❌ Backup Failed: mysqldump error." >/dev/null
    rm -f "\$SQL_FILENAME"
    exit 1
fi

# 5. Compress
echo "Compressing..."
tar -czf "\$BACKUP_FILENAME" "\$SQL_FILENAME" .env

# 6. Send to Telegram
echo "Sending to Telegram..."
CAPTION="📦 Backup: \${DB_NAME}
📅 Date: \${TIMESTAMP}
✅ Status: Automatic"

HTTP_CODE=\$(curl -s -o /dev/null -w "%{http_code}" \
    -F "chat_id=\$CHAT_ID" \
    -F "document=@\$BACKUP_FILENAME" \
    -F "caption=\$CAPTION" \
    "https://api.telegram.org/bot\$BOT_TOKEN/sendDocument")

if [ "\$HTTP_CODE" -eq 200 ]; then
    echo "Backup sent successfully."
else
    echo "Failed to send backup. HTTP Code: \$HTTP_CODE"
fi

# 7. Cleanup
rm -f "\$SQL_FILENAME" "\$BACKUP_FILENAME"
EOF

    chmod +x "${PROJECT_DIR}/backup_script.sh"

    # --- Cron Job Setup (Robust Method) ---
    info "Scheduling the cron job..."
    
    # 1. Get current crontab (ignore error if empty)
    EXISTING_CRON=$(crontab -l 2>/dev/null || true)
    
    # 2. Filter out old mersyar jobs
    CLEAN_CRON=$(echo "$EXISTING_CRON" | grep -v "mersyar_backup" || true)
    
    # 3. Define new job
    NEW_JOB="${cron_schedule} /bin/bash ${PROJECT_DIR}/backup_script.sh >> ${PROJECT_DIR}/backup.log 2>&1 # mersyar_backup"
    
    # 4. Install new crontab (Handle empty clean_cron correctly)
    if [ -z "$CLEAN_CRON" ]; then
        echo "$NEW_JOB" | crontab -
    else
        echo -e "${CLEAN_CRON}\n${NEW_JOB}" | crontab -
    fi

    # --- Verification ---
    if crontab -l | grep -q "mersyar_backup"; then
        success "Backup job successfully added to Cron!"
        info "Schedule: $cron_schedule"
        info "Logs will be saved to: ${PROJECT_DIR}/backup.log"
    else
        error "Failed to add job to Cron. Please check permissions."
        return 1
    fi
    
    # Test Run
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
               info "Stopping all services (bot, db, phpmyadmin)..."
               if docker compose down; then success "All services stopped."; else error "Failed to stop services."; fi
               show_menu
               ;;
           4)
               info "Starting all services..."
               if docker compose up -d; then success "All services started in the background."; else error "Failed to start services."; fi
               show_menu
               ;;
            5)
                info "Updating bot system to the latest version..."
                warning "This process will rebuild the bot container."
                
                info "Step 1: Stopping current services..."
                docker compose down
                
                # --- دانلود کد جدید ---
                info "Step 2: Downloading latest source code from GitHub..."
                GITHUB_USER="mersvpn"
                GITHUB_REPO="mersyar"
                
                LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
                
                if [ -z "$LATEST_TAG" ]; then
                    warning "Could not find latest release. Pulling from main branch..."
                    git pull origin main || echo "Git pull failed..."
                else
                    info "Downloading version: $LATEST_TAG"
                    wget -q "https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/tags/${LATEST_TAG}.tar.gz" -O latest.tar.gz
                    tar -xzf latest.tar.gz --strip-components=1 --exclude='.env' --overwrite
                    rm latest.tar.gz
                    success "Source code updated to $LATEST_TAG"
                fi
                
                # --- اصلاحیه مهم: دادن مجوز اجرا به فایل استارت ---
                info "Fixing file permissions..."
                chmod +x entrypoint.sh
                # ------------------------------------------------
                
                info "Step 3: Cleaning up build cache..."
                docker builder prune -f >/dev/null 2>&1
                
                info "Step 4: Building new image..."
                if ! docker compose build --no-cache bot; then
                    error "Failed to build image. Check logs."
                    docker compose up -d
                    show_menu; return
                fi
                
                info "Step 5: Starting services..."
                if docker compose up -d; then
                    success "Containers started!"
                    info "Waiting for bot to initialize..."
                    sleep 5
                    
                    info "Running database migrations..."
                    if ! docker compose exec -T bot alembic upgrade head; then
                         # تلاش برای ترمیم خودکار دیتابیس
                        warning "Migration failed, attempting repair..."
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
                   info "Operation cancelled."
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
               error "Invalid option. Please try again."
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

    # --- 1. Install Dependencies ---
    info "[1/7] Checking for dependencies..."
    if ! command -v docker &> /dev/null; then
        warning "Docker not found. Installing Docker..."
        curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh && rm get-docker.sh
        success "Docker installed successfully."
    else
        success "Docker is already installed."
    fi
    if ! docker compose version &> /dev/null; then
        warning "Docker Compose plugin not found. Installing..."
        apt-get update -y > /dev/null && apt-get install -y docker-compose-plugin > /dev/null
        success "Docker Compose plugin installed successfully."
    else
        success "Docker Compose plugin is already installed."
    fi

    # --- 2. User Input ---
    info "[2/7] Gathering required information..."
    read -p "Enter your Domain/Subdomain (e.g., bot.yourdomain.com): " BOT_DOMAIN
    read -p "Enter your email for SSL notifications: " ADMIN_EMAIL
    echo "---"
    read -p "Enter Telegram Bot Token: " TELEGRAM_BOT_TOKEN
    read -p "Enter Telegram Admin User ID: " AUTHORIZED_USER_IDS
    read -p "Enter Support Username (optional): " SUPPORT_USERNAME

    # --- 3. Create Project Directory and Files ---
    info "[3/7] Creating project structure at $PROJECT_DIR..."
    mkdir -p "$PROJECT_DIR"
    cd "$PROJECT_DIR"

    info "-> Generating secure random strings for secrets..."
    WEBHOOK_SECRET_TOKEN=$(openssl rand -hex 32)
    DB_ROOT_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)
    DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 20)

    info "-> Creating .env file..."
    cat << EOF > .env
# --- Telegram Bot Settings ---
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}"
AUTHORIZED_USER_IDS="${AUTHORIZED_USER_IDS}"
SUPPORT_USERNAME="${SUPPORT_USERNAME}"
# --- Webhook Settings ---
BOT_DOMAIN="${BOT_DOMAIN}"
WEBHOOK_SECRET_TOKEN="${WEBHOOK_SECRET_TOKEN}"
BOT_PORT=8081
# --- Database Settings for Docker Compose ---
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
DB_NAME="mersyar_bot_db"
DB_USER="mersyar"
DB_PASSWORD="${DB_PASSWORD}"
# --- Database Connection Settings for the Bot ---
DB_HOST="db"
# --- Admin Email for Certbot ---
ADMIN_EMAIL="${ADMIN_EMAIL}"
EOF

    # --- DOWNLOAD SOURCE CODE FROM GITHUB ---
    info "Downloading latest source code..."
    GITHUB_USER="mersvpn"
    GITHUB_REPO="mersyar"
    
    LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -z "$LATEST_TAG" ]; then
        warning "Could not find latest release. Cloning master branch..."
        git clone "https://github.com/${GITHUB_USER}/${GITHUB_REPO}.git" . || echo "Repo already exists."
    else
        info "Downloading version: $LATEST_TAG"
        wget -q "https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/tags/${LATEST_TAG}.tar.gz" -O latest.tar.gz
        tar -xzf latest.tar.gz --strip-components=1
        rm latest.tar.gz
    fi
    # --------------------------------------------------


     # --- START OF CORRECTED CODE BLOCK ---
    info "-> Creating docker-compose.yml with healthchecks..."
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
    # --- END OF CORRECTED CODE BLOCK ---

    
    
    # --- 4. Build, Run, and Migrate ---
    info "[4/7] Building and starting Docker containers..."
    docker compose up --build -d --force-recreate

    info "Waiting for the bot container to become ready..."
    for i in {1..10}; do
        if docker compose ps | grep 'mersyar' | grep -q 'running'; then
            info "Bot container is running. Proceeding with migration."
            break
        fi
        info "Waiting... ($i/10)"; sleep 3
    done

    if ! docker compose ps | grep 'mersyar' | grep -q 'running'; then
        error "Bot container did not start correctly. Installation failed."
        exit 1
    fi
    
    info "Running database migrations inside the container..."
    # This intelligent logic handles both new installs and re-installs.
    if ! docker compose exec -T bot alembic upgrade head; then
        warning "Initial migration failed, attempting to stamp and re-run..."
        LATEST_REVISION_ID=$(docker compose exec -T bot alembic heads | awk '{print $1}')
        if [ -z "$LATEST_REVISION_ID" ]; then
            error "Could not determine revision ID. Migration failed."
            exit 1
        fi
        
        if docker compose exec -T bot alembic stamp "$LATEST_REVISION_ID" && docker compose exec -T bot alembic upgrade head; then
            success "Database migration completed successfully after stamping."
        else
            error "Database migration failed even after stamping. Please check logs."
            exit 1
        fi
    else
        success "Database migration completed successfully."
    fi

    # ==============================================================================
    #                      --- START OF REVISED NGINX/SSL LOGIC ---
    # ==============================================================================
    
    # --- 5. Obtain SSL Certificate FIRST ---
    info "[5/7] Obtaining SSL certificate with Certbot..."
    info "-> Ensuring Certbot is installed..."
    if ! command -v certbot &> /dev/null; then
        apt-get update -y > /dev/null && apt-get install -y certbot python3-certbot-nginx > /dev/null
    fi

    if ! systemctl is-active --quiet nginx; then
        warning "Nginx is not running. Starting it temporarily for SSL challenge."
        systemctl start nginx
        NGINX_WAS_STOPPED=true
    fi
    
    info "-> Requesting certificate using webroot method..."
    mkdir -p /var/www/html
    certbot certonly --webroot -w /var/www/html -d "${BOT_DOMAIN}" --non-interactive --agree-tos --email "${ADMIN_EMAIL}"

    if [[ "$NGINX_WAS_STOPPED" == "true" ]]; then
        info "-> Stopping temporary Nginx instance."
        systemctl stop nginx
    fi
    
    SSL_CERT_PATH="/etc/letsencrypt/live/${BOT_DOMAIN}/fullchain.pem"
    if [ ! -f "$SSL_CERT_PATH" ]; then
        error "Failed to obtain SSL certificate. Check logs in /var/log/letsencrypt/."
        error "Make sure domain ${BOT_DOMAIN} points to this server's IP and try again."
        exit 1
    fi
    success "SSL certificate obtained successfully."

    # --- 6. Configure Nginx with the new SSL certificate ---
    info "[6/7] Configuring Nginx reverse proxy with SSL..."
    if ! command -v nginx &> /dev/null; then warning "Nginx not found. Installing..." && apt-get update -y > /dev/null && apt-get install -y nginx > /dev/null; fi
    
    NGINX_CONF="/etc/nginx/sites-available/mersyar"
    SSL_KEY_PATH="/etc/letsencrypt/live/${BOT_DOMAIN}/privkey.pem"

    info "-> Creating Nginx configuration file..."
    cat << EOF > "$NGINX_CONF"
server {
    listen 80;
    server_name ${BOT_DOMAIN};
    location / { return 301 https://\$host\$request_uri; }
}
server {
    listen 443 ssl http2;
    server_name ${BOT_DOMAIN};
    ssl_certificate ${SSL_CERT_PATH};
    ssl_certificate_key ${SSL_KEY_PATH};
    ssl_protocols TLSv1.2 TLSv1.3;
    location / {
        proxy_pass http://127.0.0.1:8081;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
    ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/

    # --- 7. Finalizing ---
    info "[7/7] Finalizing the installation..."
    cp "$0" "$CLI_COMMAND_PATH"
    chmod +x "$CLI_COMMAND_PATH"
    success "CLI command 'mersyar' created/updated."
    
    info "Testing Nginx configuration and reloading..."
    if nginx -t; then
        systemctl reload nginx
        success "Nginx configuration reloaded successfully."
    else
        error "Nginx configuration test failed. Please check the output above."
        error "Your bot is running, but the domain might not be accessible."
        exit 1
    fi
    
    # ==============================================================================
    #                      --- END OF REVISED NGINX/SSL LOGIC ---
    # ==============================================================================

    info "Fetching installed version details..."
    LATEST_TAG=$(wget -qO- "https://api.github.com/repos/mersvpn/mersyar/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -z "$LATEST_TAG" ]; then
        LATEST_TAG="N/A"
    fi

    # --- Installation Summary ---
    success "==============================================="
    success "✅✅✅ mersyar Docker Installation Complete! ✅✅✅"
    info "You can now manage your bot by running the 'mersyar' command."
    echo ""
    echo -e "\e[36m📦 Bot Version Installed:\e[0m ${LATEST_TAG}"
    echo -e "\e[36m🌐 Bot Domain:\e[0m https://${BOT_DOMAIN}"
    echo -e "\e[36m🔑 phpMyAdmin:\e[0m http://127.0.0.1:8082 (Access via SSH tunnel: ssh -L 8082:127.0.0.1:8082 root@<SERVER_IP>)"
    echo -e "\e[36m🔒 Database Root Password:\e[0m ${DB_ROOT_PASSWORD}"
    echo -e "\e[36m🔒 Database User Password:\e[0m ${DB_PASSWORD}"
    success "==============================================="
}

# ==============================================================================
#                                 MAIN LOGIC
# ==============================================================================
# Allow forcing re-installation
if [[ "$1" == "--force-install" ]]; then
    install_bot
    exit 0
fi

# Standard check to show menu or start install
if [[ -f "$CLI_COMMAND_PATH" && -f "$PROJECT_DIR/docker-compose.yml" ]]; then
    manage_bot "$@"
else
    install_bot
fi
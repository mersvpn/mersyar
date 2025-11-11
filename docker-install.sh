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
#                      --- NEW FEATURE --- BACKUP LOGIC
# ==============================================================================
setup_backup_job() {
    cd "$PROJECT_DIR"
    info "--- Automated Backup Setup ---"
    warning "This will schedule a periodic backup of your database and .env file."

   
    local DB_NAME_FOR_BACKUP="mersyar_bot_db"

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
        error "Invalid interval. For intervals of 60 minutes or more, please use a multiple of 60 (e.g., 60, 120, 180, 1440)."
        return 1
    fi

    info "Creating the backup script (backup_script.sh)..."
    # --- [اصلاح ۲] قالب اسکریپت بکاپ به طور کامل بازنویسی و بهینه شد ---
    cat << EOF > "${PROJECT_DIR}/backup_script.sh"
#!/bin/bash
# Script Version: 2.0 - Optimized for single-database backup
set -e

# --- Configuration ---
BOT_TOKEN="\$1"
CHAT_ID="\$2"
PROJECT_DIR="${PROJECT_DIR}"
DB_CONTAINER="mersyar-db"
DB_NAME="${DB_NAME_FOR_BACKUP}" # <-- استفاده از نام دیتابیس مشخص شده

# --- Dynamic variables ---
TIMESTAMP=\$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILENAME="mersyar_backup_\${TIMESTAMP}.tar.gz"
DB_DUMP_FILENAME="\${DB_NAME}_dump_\${TIMESTAMP}.sql"

# --- Main Execution ---
cd "\$PROJECT_DIR" || { echo "Error: Failed to cd to \$PROJECT_DIR" >&2; exit 1; }

echo "Starting backup for database: '\$DB_NAME'..."

DB_ROOT_PASSWORD=\$(docker exec "\$DB_CONTAINER" printenv MYSQL_ROOT_PASSWORD | tr -d '\r')
if [ -z "\$DB_ROOT_PASSWORD" ]; then
    echo "Error: Could not get MYSQL_ROOT_PASSWORD from container." >&2
    exit 1
fi

# --- [اصلاح ۳] دستور mysqldump برای بکاپ گرفتن فقط از دیتابیس ربات ---
echo "Dumping database..."
docker exec -e MYSQL_PWD="\$DB_ROOT_PASSWORD" "\$DB_CONTAINER" mysqldump -u root "\$DB_NAME" > "\$DB_DUMP_FILENAME"

echo "Creating archive: \$BACKUP_FILENAME..."
tar -czf "\$BACKUP_FILENAME" "\$DB_DUMP_FILENAME" .env

echo "Sending backup to Telegram..."
HTTP_CODE=\$(curl -s -o /dev/null -w "%{http_code}" -F "chat_id=\$CHAT_ID" -F "document=@\$BACKUP_FILENAME" -F "caption=Mersyar-Bot Backup (\${DB_NAME}) - \$(date)" "https://api.telegram.org/bot\$BOT_TOKEN/sendDocument")

if [ "\$HTTP_CODE" -eq 200 ]; then
    echo "Backup sent successfully."
else
    echo "Failed to send backup. HTTP Code: \$HTTP_CODE" >&2
fi

echo "Cleaning up temporary files..."
rm "\$DB_DUMP_FILENAME" "\$BACKUP_FILENAME"
echo "Backup process finished."
EOF

    chmod +x "${PROJECT_DIR}/backup_script.sh"
    info "Scheduling the cron job..."
    local cron_job="${cron_schedule} bash ${PROJECT_DIR}/backup_script.sh '$BACKUP_BOT_TOKEN' '$BACKUP_CHAT_ID' >/dev/null 2>&1 # MERSYAR_BACKUP_JOB"
    local temp_cron_file
    temp_cron_file=$(mktemp)
    crontab -l 2>/dev/null | grep -v "# MERSYAR_BACKUP_JOB" > "$temp_cron_file"
    echo "$cron_job" >> "$temp_cron_file"
    crontab "$temp_cron_file"
    local crontab_status=$?
    rm "$temp_cron_file"
    
    if [ $crontab_status -eq 0 ]; then
        success "Backup job successfully scheduled!"
        info "Running an initial test backup now..."
        if bash "${PROJECT_DIR}/backup_script.sh" "$BACKUP_BOT_TOKEN" "$BACKUP_CHAT_ID"; then
            success "Test backup completed. Please check your Telegram chat for the backup file."
        else
            error "The test backup failed. Please review the output above."
            warning "Your backup job is still scheduled, but the credentials or IDs might be incorrect."
        fi
    else
        error "Failed to schedule the cron job. An error occurred with crontab."
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
               info "Tailing logs for mersyar-bot. Press Ctrl+C to exit."
               docker compose logs -f bot
               show_menu
               ;;
           2)
               info "Restarting mersyar-bot container..."
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
                info "Updating bot by rebuilding the image from GitHub..."
                warning "This may take a few minutes."
                
                info "Step 1: Building the new image from the latest release..."
                if docker compose build --no-cache bot; then
                    info "Step 2: Re-creating the container with the new image..."
                    if docker compose up -d; then
                        success "Container updated successfully!"
                        
                        # NEW STEP: Run migrations after update
                        info "Step 3: Applying database migrations..."
                        sleep 5 # Give the bot a moment to start
                        if docker compose exec -T bot bash -c "pip install alembic pymysql sqlalchemy python-dotenv && alembic upgrade head"; then
                            success "Database migrations applied."
                            info "Bot is now fully updated."
                        else
                            error "Database migration failed during update. Please check logs."
                        fi
                        
                    else
                        error "Failed to re-create the container."
                    fi
                else
                    error "Failed to build the new image."
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
    info "      Mersyar-Bot Docker Installer"
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

    info "-> Creating Dockerfile..."
    cat << 'EOF' > Dockerfile
FROM python:3.10-slim-bookworm
RUN apt-get update && apt-get install -y wget tar && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ARG GITHUB_USER="mersvpn"
ARG GITHUB_REPO="mersyar-bot"
WORKDIR /app
# Download and extract the latest release
RUN LATEST_TAG=$(wget -qO- "https://api.github.com/repos/${GITHUB_USER}/${GITHUB_REPO}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/') && \
    DOWNLOAD_URL="https://github.com/${GITHUB_USER}/${GITHUB_REPO}/archive/refs/tags/${LATEST_TAG}.tar.gz" && \
    wget -q "$DOWNLOAD_URL" -O latest_release.tar.gz && \
    tar -xzf latest_release.tar.gz --strip-components=1 && \
    rm latest_release.tar.gz
# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt
# The CMD will be used to run the bot
CMD ["python", "bot.py"]
EOF


     # --- START OF CORRECTED CODE BLOCK ---
    info "-> Creating docker-compose.yml with healthchecks..."
    cat << 'EOF' > docker-compose.yml
services:
  bot:
    build: .
    container_name: mersyar-bot
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
    docker compose up --build -d

    info "Waiting a few seconds for the container to initialize..."
    sleep 10
    
    info "Running database migrations inside the container..."
    if ! docker compose exec -T bot bash -c "pip install alembic pymysql sqlalchemy python-dotenv && alembic upgrade head"; then
        error "Database migration failed. Please check the logs."
        error "To see logs, run: mersyar"
        error "Then select option 1 (View Bot Logs)."
        exit 1
    fi
    success "Database migration completed successfully."

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
    
    NGINX_CONF="/etc/nginx/sites-available/mersyar-bot"
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
    LATEST_TAG=$(wget -qO- "https://api.github.com/repos/mersvpn/mersyar-bot/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
    if [ -z "$LATEST_TAG" ]; then
        LATEST_TAG="N/A"
    fi

    # --- Installation Summary ---
    success "==============================================="
    success "✅✅✅ Mersyar-Bot Docker Installation Complete! ✅✅✅"
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
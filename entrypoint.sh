#!/bin/bash
set -e

# رنگ‌ها برای لاگ زیباتر
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}--- ⏳ Waiting for Database Connection... ---${NC}"

# اسکریپت پایتون برای بررسی دقیق اتصال به دیتابیس
python -c "
import socket, os, time, sys
host = os.environ.get('DB_HOST', 'db')
port = 3306
max_retries = 30
for i in range(max_retries):
    try:
        with socket.create_connection((host, port), timeout=2):
            print('✅ Database is ready!')
            sys.exit(0)
    except (OSError, ConnectionRefusedError):
        print(f'⚠️  Database not ready ({i+1}/{max_retries})...')
        time.sleep(2)
sys.exit(1)
"

echo -e "${GREEN}--- 🔄 Running Database Migrations... ---${NC}"

# اجرای هوشمند مایگریشن
if alembic upgrade head; then
    echo -e "${GREEN}--- ✅ Migration Successful ---${NC}"
else
    echo -e "${YELLOW}--- ⚠️ Migration Failed. Attempting Auto-Repair (Stamp) ---${NC}"
    # دریافت آخرین نسخه سالم و استمپ کردن روی آن
    LATEST_REV=$(alembic heads | awk '{print $1}' | head -n 1)
    if [ -n "$LATEST_REV" ]; then
        echo "🛠 Stamping DB with revision: $LATEST_REV"
        alembic stamp "$LATEST_REV"
        alembic upgrade head
    fi
fi

echo -e "${GREEN}--- 🚀 Starting Bot ---${NC}"
exec "$@"
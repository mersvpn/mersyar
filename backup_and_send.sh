#!/bin/bash
source "/root/mersyar/.env"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
BACKUP_FILE="/tmp/backup-${DB_NAME}-${TIMESTAMP}.sql.gz"
export MYSQL_PWD="$DB_PASSWORD"
if mysqldump --no-tablespaces -h"$DB_HOST" -u"$DB_USER" "$DB_NAME" 2>/dev/null | gzip > "$BACKUP_FILE"; then
    if [ -s "$BACKUP_FILE" ]; then
        CAPTION_TEXT="Backup: ${DB_NAME} @ ${TIMESTAMP}"
        curl -s -X POST "https://api.telegram.org/bot8422561547:AAF8Mfh0dKZPtFGOZOfIpL7ZkQ_ivPwrtzM/sendDocument" \
             -F "chat_id=-1002103623736" \
             -F "document=@${BACKUP_FILE}" \
             -F "caption=${CAPTION_TEXT}" > /dev/null
    fi
fi
unset MYSQL_PWD
rm -f "$BACKUP_FILE"

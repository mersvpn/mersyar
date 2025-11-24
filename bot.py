# FILE: bot.py (WINDOWS FIXED VERSION)

import logging
import logging.handlers
import sys
import os
import argparse
import asyncio # <--- اضافه شد
import platform # <--- اضافه شد

from telegram import Update
from telegram.ext import (
    Application, ApplicationBuilder, ContextTypes, MessageHandler,
    CallbackQueryHandler, filters, TypeHandler, PicklePersistence
)
from telegram.ext import CommandHandler
from config import config
from shared.translator import init_translator
from core.panel_api.marzban import close_marzban_client
from database import engine as db_engine

# ==========================================
# 🔧 WINDOWS FIX (مهم برای اجرای روی ویندوز)
# ==========================================
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
# ==========================================

init_translator()

LOG_FILE = "bot.log"
LOGGER = logging.getLogger(__name__)

def setup_logging():
    if logging.getLogger().hasHandlers(): return
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler = logging.handlers.RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(log_formatter)
    console_handler.setLevel(logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext").setLevel(logging.DEBUG)
    LOGGER.info("Logging configured successfully.")

async def debug_update_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update and hasattr(update, 'to_json'):
            LOGGER.debug(f"Update received: {update.to_json()}")
        else:
            LOGGER.debug(f"Update received (no to_json method): {update}")
    except Exception as e:
        LOGGER.error(f"Error in debug_update_logger: {e}")

async def update_user_activity(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    from database.crud import user as crud_user
    user = getattr(update, 'effective_user', None)
    if user:
        await crud_user.update_last_activity(user.id)

async def post_shutdown(application: Application):
    LOGGER.info("Shutdown signal received. Closing resources...")
    await close_marzban_client()
    LOGGER.info("HTTPX client closed gracefully.")
    await db_engine.close_db()
    LOGGER.info("Database engine (SQLAlchemy) closed gracefully.")

async def heartbeat(context: ContextTypes.DEFAULT_TYPE):
    LOGGER.info("❤️ Heartbeat: Bot is alive and the JobQueue is running.")

async def post_init(application: Application):
    """
    تابع راه‌اندازی اولیه
    """
    # 1. تلاش برای اتصال به دیتابیس
    try:
        await db_engine.init_db()
        LOGGER.info("Database connection initialized successfully.")
    except Exception as e:
        LOGGER.critical(f"🔥 FATAL ERROR: Could not connect to database! Reason: {e}")
        # اگر دیتابیس وصل نشود، ادامه دادن فایده‌ای ندارد
        sys.exit(1)

    LOGGER.info("Registering all application handlers...")

    # 2. ایمپورت کردن ماژول‌ها (درون تابع)
    from modules.general import handler as general_handler
    from modules.marzban import handler as marzban_handler
    from modules.customer import handler as customer_handler
    from modules.bot_settings import handler as bot_settings_handler
    from modules.reminder import handler as reminder_handler
    from modules.guides import handler as guides_handler
    from modules.financials import handler as financials_handler
    from modules.payment import handler as payment_handler
    from modules.broadcaster import handler as broadcaster_handler
    from modules.panel_manager import handler as panel_manager_handler
    from modules.stats import handler as stats_handler
    from modules.search import handler as search_handler
    
    # ماژول‌های تغییر یافته
    from modules import support_panel
    from modules.admin_manager import handler as admin_manager_handler

    # 3. ثبت هندلرها
    general_handler.register_gatekeeper(application)
    application.add_handler(TypeHandler(Update, update_user_activity), group=-1)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, debug_update_logger), group=-1)
    application.add_handler(CallbackQueryHandler(debug_update_logger), group=-1)

    panel_manager_handler.register(application)
    search_handler.register(application)
    admin_manager_handler.register(application)
    marzban_handler.register(application)
    bot_settings_handler.register(application)
    customer_handler.register(application)
    financials_handler.register(application)
    broadcaster_handler.register(application)
    guides_handler.register(application)

    general_handler.register_commands(application)
    payment_handler.register(application)
    reminder_handler.register(application)
    stats_handler.register(application)
    support_panel.handler.register(application)

    from shared.callbacks import main_menu_fallback
    application.add_handler(CommandHandler("cancel", main_menu_fallback), group=1)

    LOGGER.info("All handlers registered successfully.")

def main() -> None:
    setup_logging()
    
    parser = argparse.ArgumentParser(description="Mersyar Telegram Bot")
    parser.add_argument("--port", type=int, help="Port to run the webhook on.")
    args = parser.parse_args()

    LOGGER.info("===================================")
    LOGGER.info("🚀 Starting bot...")

    persistence = PicklePersistence(filepath="bot_persistence.pickle")

    application = (
        ApplicationBuilder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .persistence(persistence)
        .connect_timeout(30)
        .read_timeout(30)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    from modules.reminder.actions.jobs import cleanup_expired_test_accounts
    
    if application.job_queue:
        application.job_queue.run_repeating(heartbeat, interval=3600, first=10, name="heartbeat")
        application.job_queue.run_repeating(cleanup_expired_test_accounts, interval=3600, first=60, name="cleanup_test_accounts")
        LOGGER.info("❤️ Heartbeat and Test Account Cleanup jobs scheduled.")

    # --- Webhook / Polling Setup ---
    BOT_DOMAIN = os.getenv("BOT_DOMAIN")
    WEBHOOK_SECRET_TOKEN = os.getenv("WEBHOOK_SECRET_TOKEN")
    
    if args.port:
        PORT = args.port
    else:
        PORT = int(os.getenv("BOT_PORT", 8081))

    if not all([BOT_DOMAIN, WEBHOOK_SECRET_TOKEN]):
        LOGGER.info("Starting in polling mode.")
        application.run_polling(drop_pending_updates=True)
    else:
        webhook_url = f"https://{BOT_DOMAIN}/{WEBHOOK_SECRET_TOKEN}"
        LOGGER.info(f"Starting in webhook mode on port {PORT}. URL: {webhook_url}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=WEBHOOK_SECRET_TOKEN,
            webhook_url=webhook_url,
            secret_token=WEBHOOK_SECRET_TOKEN,
            allowed_updates=Update.ALL_TYPES
        )

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.critical("A critical error occurred in the main execution block.", exc_info=True)
# FILE: modules/general/handler.py (FINAL CORRECTED VERSION)

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    TypeHandler,
    filters,
    ApplicationHandlerStop,
    CallbackQueryHandler
)
from shared.translator import translator
from modules.bot_settings.data_manager import is_bot_active
from config import config

from .actions import (
    start,
    show_my_id,
    switch_to_admin_view,
    close_message,
    back_to_main_menu_simple
)

MAINTENANCE_MESSAGE = (
    "**🛠 ربات در حال تعمیر و به‌روزرسانی است**\n\n"
    "در حال حاضر امکان پاسخگویی وجود ندارد. لطفاً کمی بعد دوباره تلاش کنید.\n\n"
    "از شکیبایی شما سپاسگزاریم."
)

async def maintenance_gatekeeper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    A powerful gatekeeper that runs before any other handler (group=-1).
    It checks if the bot is in maintenance mode and blocks all non-admin users.
    """
    if await is_bot_active():
        return

    user = update.effective_user
    if user and user.id in config.AUTHORIZED_USER_IDS:
        return

    if update.callback_query:
        await update.callback_query.answer(translator.get("errors.maintenance_mode_active"), show_alert=True)
    elif update.message:
        await update.message.reply_markdown(MAINTENANCE_MESSAGE)

    raise ApplicationHandlerStop

def register_gatekeeper(application: Application):
    """Registers only the maintenance gatekeeper which must run before everything."""
    application.add_handler(TypeHandler(Update, maintenance_gatekeeper), group=-1)

def register_commands(application: Application):
    """Registers general commands and message handlers that should have lower priority."""

    # --- اصلاحیه: اولویت بالا (Group 0) برای دکمه بازگشت ---
    # این هندلر باید قبل از هندلرهای مشتری یا کچ-آل اجرا شود
    back_texts = [
        translator.get("keyboards.settings_and_tools.back_to_main_menu"),
        translator.get("keyboards.general.back_to_main_menu"),
        "🔙 بازگشت به منوی اصلی"  # جهت اطمینان (Hardcode)
    ]
    # حذف مقادیر خالی (None)
    back_buttons = [t for t in back_texts if t]

    if back_buttons:
        application.add_handler(
            MessageHandler(
                filters.Text(back_buttons) & filters.User(user_id=config.AUTHORIZED_USER_IDS),
                back_to_main_menu_simple
            ),
            group=0  # تغییر مهم: اولویت صفر (اجرا قبل از بقیه)
        )
    # ------------------------------------------------------

    # --- CORE COMMANDS ---
    application.add_handler(CommandHandler("start", start), group=1)
    application.add_handler(CommandHandler("myid", show_my_id), group=1)

    # --- CALLBACK QUERY HANDLERS ---
    application.add_handler(CallbackQueryHandler(start, pattern=r'^check_join_status$'), group=1)
    application.add_handler(CallbackQueryHandler(close_message, pattern=r'^close_message$'), group=1)

    # --- ADMIN-SPECIFIC HANDLERS ---
    back_to_admin_text = translator.get("keyboards.general.back_to_admin_panel")
    if back_to_admin_text:
        application.add_handler(MessageHandler(
            filters.Text([back_to_admin_text]) & filters.User(user_id=config.AUTHORIZED_USER_IDS),
            switch_to_admin_view
        ), group=1)
# FILE: modules/reminder/handler.py (نسخه نهایی با روش تمیزتر برای رفع هشدار VS Code)

import logging
from telegram import Update
from telegram.ext import (
    Application, MessageHandler, filters, ContextTypes,
    CommandHandler, CallbackQueryHandler, ConversationHandler
)

# 1. وارد کردن ConversationHandler اصلی (که fallbacks ندارد)
from .actions.daily_note import daily_notes_conv
from .actions import jobs, settings
from shared.keyboards import get_notes_management_keyboard
from modules.marzban.actions import note

LOGGER = logging.getLogger(__name__)

async def show_notes_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays the 'Notes Management' menu."""
    await update.message.reply_text(
        "به بخش «مدیریت یادداشت‌ها» خوش آمدید.",
        reply_markup=get_notes_management_keyboard()
    )

def register(application: Application) -> None:
    """Registers handlers for the reminder and tools module."""
    # 2. وارد کردن تابع fallback به صورت محلی
    from modules.general.actions import end_conversation_and_show_main_menu
    from config import config
    
    if config.AUTHORIZED_USER_IDS:
        application.bot_data['admin_id_for_jobs'] = config.AUTHORIZED_USER_IDS[0]
    else:
        LOGGER.warning("No authorized users found. Reminder job cannot be scheduled.")
        application.bot_data['admin_id_for_jobs'] = None
    
    settings.reminder_settings_conv.entry_points.append(
        MessageHandler(
            filters.Regex('^⚙️ اتوماسیون روزانه$'), 
            settings.start_reminder_settings
        )
    )
    
    # 3. ساخت یک ConversationHandler جدید و کامل با اضافه کردن fallbacks
    complete_daily_notes_conv = ConversationHandler(
        entry_points=daily_notes_conv.entry_points,
        states=daily_notes_conv.states,
        fallbacks=[
            CommandHandler('cancel', end_conversation_and_show_main_menu),
            CallbackQueryHandler(end_conversation_and_show_main_menu, pattern='^cancel_conv$')
        ],
        conversation_timeout=600,
        per_user=True,
        per_chat=True
    )
    
    # 4. ثبت هندلرهای کامل شده
    application.add_handler(settings.reminder_settings_conv, group=1)
    application.add_handler(complete_daily_notes_conv, group=1) # <-- از ConversationHandler جدید استفاده می‌کنیم
    
    application.add_handler(MessageHandler(filters.Regex('^📓 مدیریت یادداشت‌ها$'), show_notes_management_menu), group=1)
    application.add_handler(MessageHandler(filters.Regex('^👤 اشتراک‌های ثبت‌شده$'), note.list_users_with_subscriptions), group=1)

    if application.job_queue:
        application.job_queue.run_once(
            callback=lambda ctx: jobs.schedule_initial_daily_job(application),
            when=5,
            name="initial_job_scheduler"
        )
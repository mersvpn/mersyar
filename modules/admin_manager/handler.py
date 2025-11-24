# FILE: modules/admin_manager/handler.py

from telegram.ext import (
    Application, MessageHandler, filters, 
    CallbackQueryHandler, ConversationHandler, CommandHandler
)
from . import actions
import re
from shared.translator import translator

def register(application: Application) -> None:
    # متن دکمه ورود به مدیریت مدیران (از فایل ترجمه helper_tools)
    manage_admins_text = translator.get("keyboards.helper_tools.manage_admins")
    
    # 1. هندلر دکمه "مدیریت مدیران" (نقطه ورود)
    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(manage_admins_text)}$"), 
            actions.show_admin_management_menu
        )
    )

    # 2. هندلرهای کال‌بک (لیست، جزئیات و حذف)
    application.add_handler(CallbackQueryHandler(actions.show_admin_management_menu, pattern="^admin_manage_list$"))
    application.add_handler(CallbackQueryHandler(actions.show_admin_detail, pattern="^admin_manage_detail_"))
    application.add_handler(CallbackQueryHandler(actions.delete_admin, pattern="^admin_manage_delete_"))
    
    # 3. مکالمه افزودن مدیر جدید
    add_admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(actions.start_add_admin, pattern="^admin_manage_add$")
        ],
        states={
            actions.GET_ADMIN_ID: [
                MessageHandler(filters.TEXT | filters.FORWARDED, actions.process_add_admin_input)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", actions.cancel_add_admin),
            MessageHandler(filters.Regex("^/cancel$"), actions.cancel_add_admin)
        ],
        conversation_timeout=120
    )
    
    application.add_handler(add_admin_conv)
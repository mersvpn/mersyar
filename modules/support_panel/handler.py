# FILE: modules/support_panel/handler.py

from telegram import Update
from telegram.ext import (
    Application, MessageHandler, filters, 
    CallbackQueryHandler, ConversationHandler, CommandHandler, ContextTypes
)
from shared.translator import translator
from . import actions
import re
from modules.marzban.actions import add_user
import logging

LOGGER = logging.getLogger(__name__)

async def support_exit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await actions.show_support_menu(update, context)
    return ConversationHandler.END

def register(application: Application) -> None:
    support_btn_text = translator.get("keyboards.customer_main_menu.support_panel")
    add_user_text = translator.get("keyboards.user_management.add_user")
    my_users_btn_text = translator.get("keyboards.support_panel.my_users") # <--- ترجمه جدید

    # -------------------------------------------------------------------------
    # 🛡️ EXIT GUARD
    # -------------------------------------------------------------------------
    EXIT_BUTTONS = [
        support_btn_text,
        translator.get("keyboards.user_management.back_to_main_menu"),
        my_users_btn_text
    ]
    
    exit_pattern = f"^({'|'.join(map(re.escape, EXIT_BUTTONS))})$"
    exit_handler = MessageHandler(filters.Regex(exit_pattern), support_exit_handler)

    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(support_btn_text)}$"), 
            actions.show_support_menu
        )
    )

    application.add_handler(
        MessageHandler(
            filters.Regex(f"^{re.escape(my_users_btn_text)}$"), 
            actions.show_my_users
        )
    )
    
    application.add_handler(
        CallbackQueryHandler(actions.handle_my_users_pagination, pattern="^myusers_page_")
    )

    support_add_user_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(add_user_text)}$"), add_user.add_user_start)
        ],
        states={
            add_user.SELECT_PANEL: [
                 CallbackQueryHandler(add_user.select_panel_for_creation, pattern='^add_user_panel_'),
                 CallbackQueryHandler(add_user.cancel_add_user, pattern='^cancel_add_user$')
            ],
            add_user.GET_USERNAME: [
                exit_handler,
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_username)
            ],
            add_user.GET_DATALIMIT: [
                exit_handler,
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_datalimit)
            ],
            add_user.GET_EXPIRE: [
                exit_handler,
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_expire)
            ],
            add_user.CONFIRM_CREATION: [
                CallbackQueryHandler(add_user.add_user_create, pattern='^confirm_add_user$'),
                CallbackQueryHandler(add_user.cancel_add_user, pattern='^cancel_add_user$')
            ],
        },
        fallbacks=[
            exit_handler,
            CommandHandler("cancel", actions.show_support_menu),
            MessageHandler(filters.Regex("^/cancel$"), actions.show_support_menu)
        ],
        conversation_timeout=600
    )
    
    application.add_handler(support_add_user_conv)
    
    LOGGER.info("Support Panel handlers registered.")
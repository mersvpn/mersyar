# FILE: modules/marzban/handler.py
# --- START OF FILE ---

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application, ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from shared.callbacks import cancel_conversation_and_stop_propagation, cancel_to_helper_tools
from shared.keyboards import get_admin_main_menu_keyboard 
from shared.translator import translator
from modules.general.actions import switch_to_customer_view
from modules.payment.actions import renewal as payment_actions
from config import config
import re

# Define Conversation States
SELECT_PANEL, USER_MENU = range(2)

# --- تابع جدید برای خروج هوشمند ---
async def universal_exit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    این تابع وقتی اجرا می‌شود که کاربر وسط مکالمه دکمه‌ای از منوی اصلی را بزند.
    مکالمه را می‌بندد و منوی اصلی را مجدداً ارسال می‌کند تا کاربر بداند آزاد شده است.
    """
    user_id = update.effective_user.id
    
    # ارسال پیام لغو و نمایش مجدد منوی اصلی
    await update.message.reply_text(
        text=translator.get("keyboards.general.cancel"),
        reply_markup=get_admin_main_menu_keyboard()
    )
    
    # پایان دادن به مکالمه فعلی
    return ConversationHandler.END

def register(application: Application) -> None:
    """Registers all handlers for the Marzban (admin) module."""
    from .actions import (
        add_user, display, modify_user,
        note, template, linking,
    )

    admin_filter = filters.User(user_id=config.AUTHORIZED_USER_IDS)

    # -------------------------------------------------------------------------
    # 🛡️ EXIT GUARD: تعریف لیست دکمه‌هایی که باید مکالمه را قطع کنند
    # -------------------------------------------------------------------------
    EXIT_BUTTONS_TEXT = [
        translator.get("keyboards.user_management.back_to_main_menu"),
        translator.get("keyboards.admin_main_menu.manage_users"),
        translator.get("keyboards.admin_main_menu.bot_settings"),
        translator.get("keyboards.admin_main_menu.financials"),
        translator.get("keyboards.admin_main_menu.support_panel"),
        translator.get("keyboards.admin_main_menu.customer_panel_view"),
        translator.get("keyboards.admin_main_menu.search_user"),
        translator.get("keyboards.customer_main_menu.support_panel")
    ]

    exit_pattern = f"^({'|'.join(map(re.escape, EXIT_BUTTONS_TEXT))})$"
    
    # استفاده از تابع جدید universal_exit_handler بجای stop_propagation
    exit_handler = MessageHandler(filters.Regex(exit_pattern), universal_exit_handler)
    # -------------------------------------------------------------------------

    # --- Get translated texts for filters ---
    USER_MANAGEMENT_TEXT = translator.get("keyboards.admin_main_menu.manage_users")
    BACK_TO_MAIN_MENU_TEXT = translator.get("keyboards.user_management.back_to_main_menu")
    
    # ✨ Universal Fallback
    universal_admin_fallback = [
        exit_handler, 
        MessageHandler(filters.Regex(f'^{BACK_TO_MAIN_MENU_TEXT}$'), universal_exit_handler),
        CommandHandler('cancel', universal_exit_handler)
    ]

    # --- Nested Conversation: Add User ---
    add_user_conv_nested = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.add_user")}$'), add_user.add_user_start)],
        states={
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
        fallbacks=[CommandHandler('cancel', display.show_user_management_menu)],
        conversation_timeout=600,
        map_to_parent={ ConversationHandler.END: USER_MENU }
    )
   
    # --- Main Conversation: User Management ---
    user_management_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{USER_MANAGEMENT_TEXT}$') & admin_filter, display.prompt_for_panel_selection)],
        states={
            SELECT_PANEL: [
                exit_handler, 
                MessageHandler(filters.TEXT & ~filters.COMMAND, display.select_panel_and_show_menu)
            ],
            USER_MENU: [
                add_user_conv_nested,
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.show_users")}$'), display.list_all_users_paginated),
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.expiring_users")}$'), display.list_warning_users_paginated),
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.back_to_panel_selection")}$'), display.prompt_for_panel_selection),
            ],
        },
        fallbacks=universal_admin_fallback,
        allow_reentry=True,
    )

    # --- Conversation: Add User For Customer ---
    add_user_for_customer_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_user.add_user_for_customer_start, pattern=r'^create_user_for_')],
        states={
            SELECT_PANEL: [CallbackQueryHandler(add_user.select_panel_for_creation, pattern=r'^add_user_panel_')],
            add_user.GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_username)],
            add_user.GET_DATALIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_datalimit)],
            add_user.GET_EXPIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_expire)],
            add_user.CONFIRM_CREATION: [
                CallbackQueryHandler(add_user.add_user_create, pattern='^confirm_add_user$'),
                CallbackQueryHandler(add_user.cancel_add_user, pattern='^cancel_add_user$') 
            ],
        },
        fallbacks=universal_admin_fallback,
        conversation_timeout=600
    )

    # --- Conversation: Edit Note / Price ---
    note_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(note.prompt_for_note_details, pattern=r'^note_')],
        states={
            note.GET_DURATION: [
                exit_handler, 
                MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_duration_and_ask_for_data_limit), 
                CallbackQueryHandler(note.delete_note_from_prompt, pattern=r'^delete_note_')
            ],
            note.GET_DATA_LIMIT: [
                exit_handler, 
                MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_data_limit_and_ask_for_price)
            ],
            note.GET_PRICE: [
                exit_handler, 
                MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_price_and_save_note)
            ],
        }, 
        fallbacks=universal_admin_fallback,
        conversation_timeout=600,
    )
    
    # --- Conversation: Add Days ---
    add_days_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(modify_user.prompt_for_add_days, pattern=r'^add_days_')],
        states={
            modify_user.ADD_DAYS_PROMPT: [
                exit_handler,
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_user.do_add_days)
            ]
        },
        fallbacks=universal_admin_fallback,
        conversation_timeout=600,
    )
    
    # --- Conversation: Add Data ---
    add_data_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(modify_user.prompt_for_add_data, pattern=r'^add_data_')],
        states={
            modify_user.ADD_DATA_PROMPT: [
                exit_handler,
                MessageHandler(filters.TEXT & ~filters.COMMAND, modify_user.do_add_data)
            ]
        },
        fallbacks=universal_admin_fallback,
        conversation_timeout=600,
    )
    
    # --- Helper Tools ---
    helper_tools_fallback = [CommandHandler('cancel', cancel_to_helper_tools)]
    
    linking_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{translator.get("keyboards.helper_tools.create_connect_link")}$') & admin_filter, linking.start_linking_process)],
        states={linking.PROMPT_USERNAME_FOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, linking.generate_linking_url)]},
        fallbacks=helper_tools_fallback,
        conversation_timeout=300
    )

    # --- Register All Handlers ---
    application.add_handler(user_management_conv)
    application.add_handler(note_conv) 
    application.add_handler(linking_conv)
    application.add_handler(add_days_conv)
    application.add_handler(add_data_conv)
    application.add_handler(add_user_for_customer_conv)

    application.add_handler(MessageHandler(filters.Regex(f'^{translator.get("keyboards.admin_main_menu.customer_panel_view")}$') & admin_filter, switch_to_customer_view))
    
    # --- Register Standalone Handlers ---
    standalone_handlers = [
        CallbackQueryHandler(display.show_status_legend, pattern=r'^show_status_legend$'),
        CallbackQueryHandler(display.update_user_page, pattern=r'^show_users_page_'),
        CallbackQueryHandler(display.show_user_details, pattern=r'^user_details_'),
        CallbackQueryHandler(display.send_subscription_qr_code_and_link, pattern=r'^sub_link_'),
        CallbackQueryHandler(modify_user.renew_user_smart, pattern=r'^renew_'),
        CallbackQueryHandler(modify_user.reset_user_traffic, pattern=r'^reset_traffic_'),
        CallbackQueryHandler(modify_user.confirm_delete_user, pattern=r'^delete_'),
        CallbackQueryHandler(modify_user.do_delete_user, pattern=r'^do_delete_user_'),
        CallbackQueryHandler(note.list_users_with_subscriptions, pattern=r'^list_subs_page_'),
        CallbackQueryHandler(payment_actions.send_manual_invoice, pattern=r'^send_invoice_'),
        CommandHandler("start", display.handle_deep_link_details, filters=filters.Regex(r'details_'))
    ]
    for handler in standalone_handlers:
        application.add_handler(handler)

# --- END OF FILE ---
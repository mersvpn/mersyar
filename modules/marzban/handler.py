# FILE: modules/marzban/handler.py (نسخه نهایی و یکپارچه شده)
# --- START OF FILE ---

from telegram.ext import (
    Application, ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
# ✨ FIX: Import only the necessary and correct callbacks
from shared.callbacks import cancel_conversation_and_stop_propagation, cancel_to_helper_tools
from shared.translator import translator
from modules.general.actions import switch_to_customer_view
from modules.payment.actions import renewal as payment_actions
from config import config

# Define Conversation States for clarity
SELECT_PANEL, USER_MENU = range(2)

def register(application: Application) -> None:
    """Registers all handlers for the Marzban (admin) module."""
    from .actions import (
        add_user, display, modify_user,
        note, template, linking,
    )

    admin_filter = filters.User(user_id=config.AUTHORIZED_USER_IDS)
    
    # --- Get translated texts for filters once ---
    USER_MANAGEMENT_TEXT = translator.get("keyboards.admin_main_menu.manage_users")
    SEARCH_USER_TEXT = translator.get("keyboards.admin_main_menu.search_user") # Moved from user_management
    BACK_TO_MAIN_MENU_TEXT = translator.get("keyboards.user_management.back_to_main_menu")
    
    # ✨ --- THE GOLDEN FALLBACK PATTERN --- ✨
    # This fallback will be used by MOST conversations in this module.
    # It correctly handles the "Back to Main Menu" button and the /cancel command,
    # and stops further handlers from running.
    universal_admin_fallback = [
        MessageHandler(filters.Regex(f'^{BACK_TO_MAIN_MENU_TEXT}$'), cancel_conversation_and_stop_propagation),
        CommandHandler('cancel', cancel_conversation_and_stop_propagation)
    ]

    # This conversation is nested inside user_management_conv to handle adding users from that menu
    add_user_conv_nested = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.add_user")}$'), add_user.add_user_start)],
        states={
            add_user.GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_username)],
            add_user.GET_DATALIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_datalimit)],
            add_user.GET_EXPIRE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_user.add_user_get_expire)],
            add_user.CONFIRM_CREATION: [
                CallbackQueryHandler(add_user.add_user_create, pattern='^confirm_add_user$'),
                CallbackQueryHandler(add_user.cancel_add_user, pattern='^cancel_add_user$')
            ],
        },
        fallbacks=[CommandHandler('cancel', display.show_user_management_menu)], # Special case: cancel returns to parent menu
        conversation_timeout=600,
        map_to_parent={ ConversationHandler.END: USER_MENU }
    )
   
    # Main User Management Conversation: The entry point for "مدیریت کاربران"
    user_management_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{USER_MANAGEMENT_TEXT}$') & admin_filter, display.prompt_for_panel_selection)],
        states={
            SELECT_PANEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, display.select_panel_and_show_menu)
            ],
            USER_MENU: [
                add_user_conv_nested, # The add user conversation is nested here
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.show_users")}$'), display.list_all_users_paginated),
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.expiring_users")}$'), display.list_warning_users_paginated),
                MessageHandler(filters.Regex(f'^{translator.get("keyboards.user_management.back_to_panel_selection")}$'), display.prompt_for_panel_selection),
            ],
        },
        fallbacks=universal_admin_fallback, # ✨ FIX: Uses the correct, universal fallback
        allow_reentry=True,
    )


    # Standalone conversation for adding a user for a specific customer (e.g., from an invoice)
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
        fallbacks=universal_admin_fallback, # ✨ FIX: Uses the correct, universal fallback
        conversation_timeout=600
    )

    # Conversations triggered by inline keyboards (e.g., inside user details)
    note_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(note.prompt_for_note_details, pattern=r'^note_')],
        states={
            note.GET_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_duration_and_ask_for_data_limit), CallbackQueryHandler(note.delete_note_from_prompt, pattern=r'^delete_note_')],
            note.GET_DATA_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_data_limit_and_ask_for_price)],
            note.GET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, note.get_price_and_save_note)],
        }, 
        fallbacks=universal_admin_fallback, # ✨ FIX: Uses the correct, universal fallback
        conversation_timeout=600,
    )
    
    add_days_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(modify_user.prompt_for_add_days, pattern=r'^add_days_')],
        states={modify_user.ADD_DAYS_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, modify_user.do_add_days)]},
        fallbacks=universal_admin_fallback, # ✨ FIX: Uses the correct, universal fallback
        conversation_timeout=600,
    )
    
    add_data_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(modify_user.prompt_for_add_data, pattern=r'^add_data_')],
        states={modify_user.ADD_DATA_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, modify_user.do_add_data)]},
        fallbacks=universal_admin_fallback, # ✨ FIX: Uses the correct, universal fallback
        conversation_timeout=600,
    )
    
    # Conversations from "Helper Tools" menu have a different fallback
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
    
    # --- Register Standalone Handlers (that are not part of any conversation) ---
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
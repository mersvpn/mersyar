# FILE: modules/panel_manager/handler.py (FINAL VERSION WITH CORRECT TRANSLATION HANDLING)

from telegram.ext import (
    Application, ConversationHandler, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters
)
# ✨ FIX: Import the translator object directly
from shared.translator import translator
from shared.auth import admin_only_conv, admin_only
from modules.bot_settings.actions import show_settings_and_tools_menu
from shared.callbacks import cancel_and_remove_message

from . import actions as panel_actions
from modules.marzban.actions import template
from shared.callbacks import cancel_to_panel_management # We will create this callback soon
# Define states for the main conversation
MANAGE_PANEL_MENU = 100

def register(application: Application) -> None:
    """Registers all handlers for the Panel Manager module."""

    # ✨ FIX: Get translated strings directly using the translator object
    # This ensures we have a standard string when building the Regex filter.
    PANEL_MANAGEMENT_TEXT = translator.get("keyboards.settings_and_tools.panel_management")
    ADD_PANEL_TEXT = translator.get("keyboards.panel_management.add_panel")
    BACK_TO_SETTINGS_TEXT = translator.get("keyboards.panel_management.back_to_settings")


    add_panel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{ADD_PANEL_TEXT}$'), admin_only_conv(panel_actions.start_add_panel_conv))],
        states={
            panel_actions.SELECT_PANEL_TYPE: [CallbackQueryHandler(panel_actions.select_panel_type, pattern=r'^add_panel_type_')],
            panel_actions.GET_PANEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_actions.get_panel_name)],
            panel_actions.GET_API_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_actions.get_api_url)],
            panel_actions.GET_USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_actions.get_username)],
            panel_actions.GET_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, panel_actions.get_password_and_save)],
        },
        fallbacks=[
            CallbackQueryHandler(panel_actions.cancel_add_panel, pattern=r'^cancel_add_panel$'),
            CommandHandler('cancel', panel_actions.cancel_add_panel)
        ],
        map_to_parent={ ConversationHandler.END: MANAGE_PANEL_MENU },
        conversation_timeout=600
    )

    template_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_only_conv(template.set_template_user_start), pattern=r'^set_template_')],
        states={template.SET_TEMPLATE_USER_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, template.set_template_user_process)]},
        fallbacks=[CommandHandler('cancel', cancel_to_panel_management)],
        conversation_timeout=300
        
    )

    manage_panel_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{PANEL_MANAGEMENT_TEXT}$'), admin_only_conv(panel_actions.show_panel_management_menu))],
        states={
            MANAGE_PANEL_MENU: [
                template_conv,
                add_panel_conv,
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND &
                    ~filters.Regex(f'^{ADD_PANEL_TEXT}$') &
                    ~filters.Regex(f'^{BACK_TO_SETTINGS_TEXT}'),
                    panel_actions.select_panel_from_reply
                ),
                
                CallbackQueryHandler(admin_only(panel_actions.check_panel_connection), pattern=r'^panel_status_'),
                CallbackQueryHandler(admin_only(panel_actions.confirm_delete_panel), pattern=r'^confirm_delete_panel_'),
                CallbackQueryHandler(admin_only(panel_actions.do_delete_panel), pattern=r'^do_delete_panel_'),
                CallbackQueryHandler(admin_only(panel_actions.migrate_and_delete_panel), pattern=r'^migrate_del_'),
                CallbackQueryHandler(cancel_and_remove_message, pattern=r'^cancel_generic$'),
                CallbackQueryHandler(admin_only(panel_actions.toggle_test_panel_status), pattern=r'^toggle_test_panel_'),
            ],
        },
        fallbacks=[
            MessageHandler(
                filters.Regex(f'^{translator.get("keyboards.panel_management.back_to_settings")}$'), 
                show_settings_and_tools_menu # این تابع باید مکالمه را پایان دهد
            ),
            CommandHandler('cancel', show_settings_and_tools_menu)
        ],
        allow_reentry=True
    )

    application.add_handler(manage_panel_conv)
# FILE: modules/bot_settings/handler.py (FINAL, FULLY CORRECTED VERSION)

from telegram.ext import (
    Application, ConversationHandler, MessageHandler,
    filters, CallbackQueryHandler, CommandHandler
)
import logging
from shared.auth import admin_only_conv, admin_only
from shared.keyboards import get_settings_and_tools_keyboard, get_helper_tools_keyboard
from .actions import (
    start_bot_settings, toggle_maintenance_mode, toggle_log_channel,show_settings_and_tools_menu,
    toggle_auto_confirm,
    prompt_for_channel_id, process_channel_id, MENU_STATE, SET_CHANNEL_ID,
    toggle_forced_join_status, prompt_for_forced_join_channel, process_forced_join_channel,
    GET_FORCED_JOIN_CHANNEL,
    show_helper_tools_menu, back_to_settings_menu,
    start_test_account_settings, toggle_test_account_activation,
    prompt_for_hours, prompt_for_gb, prompt_for_limit,
    toggle_sub_creation,
    process_and_save_value, back_to_management_menu,
    
    ADMIN_TEST_ACCOUNT_MENU, GET_HOURS, GET_GB, GET_LIMIT
)
from shared.translator import _



def register(application: Application) -> None:
    logging.critical("!!!!!! [TRACE] BOT_SETTINGS HANDLER is being registered. !!!!!!")
    # (✨ FIX) Define a consistent group for admin main menu handlers to ensure correct priority.
    ADMIN_MAIN_MENU_GROUP = 0

    # This conversation handler is for the main bot settings (maintenance, wallet, etc.)
    bot_settings_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{_("settings_and_tools.bot_settings")}$'), admin_only_conv(start_bot_settings))],
        states={
            MENU_STATE: [
                CallbackQueryHandler(toggle_maintenance_mode, pattern=r'^toggle_maintenance_'),
                CallbackQueryHandler(toggle_log_channel, pattern=r'^toggle_log_channel_'),
                CallbackQueryHandler(toggle_forced_join_status, pattern=r'^toggle_forced_join_'),
                CallbackQueryHandler(toggle_auto_confirm, pattern=r'^toggle_auto_confirm_'),
                CallbackQueryHandler(toggle_sub_creation, pattern=r'^toggle_sub_creation_'),
            ]
        },
        fallbacks=[
            CallbackQueryHandler(back_to_settings_menu, pattern=r'^bot_status_back$'),
            CommandHandler('cancel', back_to_settings_menu)
        ],
        conversation_timeout=300
    )

    # This conversation is just for setting the log channel ID
    channel_id_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{_("settings_and_tools.set_log_channel")}$'), admin_only_conv(prompt_for_channel_id))],
        states={
            SET_CHANNEL_ID: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND & ~filters.Regex(f'^{_("helper_tools.back_to_settings")}$'),
                    process_channel_id
                )
            ]
        },
        fallbacks=[
            MessageHandler(filters.Regex(f'^{_("helper_tools.back_to_settings")}$'), back_to_settings_menu)
        ],
        conversation_timeout=300
    )

    # This is the conversation handler for setting the forced join channel
    forced_join_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{_("helper_tools.set_forced_join_channel")}$'), admin_only_conv(prompt_for_forced_join_channel))],
        states={
            GET_FORCED_JOIN_CHANNEL: [
                MessageHandler(filters.Regex(f'^{_("helper_tools.back_to_helper_tools")}$'), back_to_management_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_forced_join_channel)
            ]
        },
        fallbacks=[
            CommandHandler('cancel', back_to_management_menu)
        ],
        conversation_timeout=300
    )

    # This is the main conversation handler for the Test Account inline menu
    test_account_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{_("helper_tools.test_account_settings")}$'), admin_only_conv(start_test_account_settings))],
        states={
            ADMIN_TEST_ACCOUNT_MENU: [
                CallbackQueryHandler(toggle_test_account_activation, pattern=r'^admin_test_acc_(enable|disable)$'),
                CallbackQueryHandler(prompt_for_hours, pattern=r'^admin_test_acc_set_hours$'),
                CallbackQueryHandler(prompt_for_gb, pattern=r'^admin_test_acc_set_gb$'),
                CallbackQueryHandler(prompt_for_limit, pattern=r'^admin_test_acc_set_limit$'),
                CallbackQueryHandler(back_to_management_menu, pattern=r'^admin_test_acc_back$'),
            ],
            GET_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_and_save_value)],
            GET_GB: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_and_save_value)],
            GET_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_and_save_value)],
        },
        fallbacks=[
            CallbackQueryHandler(back_to_management_menu, pattern=r'^admin_test_acc_back$'),
            MessageHandler(filters.Regex(f'^{_("helper_tools.back_to_management_menu")}$'), back_to_management_menu),
            CommandHandler('cancel', back_to_management_menu)
        ],
        conversation_timeout=300 # (✨ FIX) Added timeout for consistency
    )
    
    # Register all handlers
    # Using the same group ensures they are processed in the order they are added.
    # This prevents general handlers from capturing input before specific ones.
    application.add_handler(MessageHandler(filters.Regex(f'^{_("admin_main_menu.settings_and_tools")}$'), admin_only(show_settings_and_tools_menu)), group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(bot_settings_conv, group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(channel_id_conv, group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(test_account_conv, group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(forced_join_conv, group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(MessageHandler(filters.Regex(f'^{_("settings_and_tools.helper_tools")}$'), admin_only(show_helper_tools_menu)), group=ADMIN_MAIN_MENU_GROUP)
    application.add_handler(MessageHandler(filters.Regex(f'^{_("helper_tools.back_to_settings")}$'), admin_only(back_to_settings_menu)), group=ADMIN_MAIN_MENU_GROUP)
# FILE: modules/financials/handler.py (نسخه نهایی و کاملاً اصلاح شده)

import logging
from telegram.ext import (
    Application, CallbackQueryHandler, MessageHandler, 
    filters, ConversationHandler, CommandHandler
)
from shared.translator import _
from .actions.settings import (
    card_settings_conv,
    plan_name_settings_conv,
    show_financial_menu,
    show_payment_methods_menu,
    show_plan_management_menu,
    back_to_main_settings_menu
)
from .actions import (
    unlimited_plans_admin, 
    volumetric_plans_admin, 
    wallet_admin, 
    balance_management,
    gift
)
from shared.callbacks import show_coming_soon
from shared.auth import get_admin_fallbacks

LOGGER = logging.getLogger(__name__)

def register(application: Application):
    """
    Registers handlers for the ADMIN financial settings panel.
    """
    from shared.callbacks import main_menu_fallback # <-- FIX 1: Import correct function
    
    LOGGER.info("Registering financials settings module handlers...")
    
    # We use main_menu_fallback as the universal cancel command handler
    cancel_fallback = [CommandHandler('cancel', main_menu_fallback)]

    # --- Attaching fallbacks to imported ConversationHandlers ---
    # These handlers were defined in other files with fallbacks=[]
    card_settings_conv.fallbacks.extend(cancel_fallback)
    plan_name_settings_conv.fallbacks.extend(cancel_fallback)
    unlimited_plans_admin.add_unlimited_plan_conv.fallbacks.extend(cancel_fallback)
    volumetric_plans_admin.edit_base_price_conv.fallbacks.extend(cancel_fallback)
    volumetric_plans_admin.add_tier_conv.fallbacks.extend(cancel_fallback)
    volumetric_plans_admin.edit_tier_conv.fallbacks.extend(cancel_fallback)
    wallet_admin.edit_amounts_conv.fallbacks.extend(cancel_fallback)
    # Note: We are ignoring get_admin_fallbacks() for simplicity and consistency

    # --- Conversation Handler for Balance Management ---
    balance_management_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(balance_management.start_balance_management, pattern='^admin_manage_balance$')
        ],
        states={
            balance_management.GET_USER_ID: [
                MessageHandler(filters.Regex(f'^{_("keyboards.financials.balance_management_back_button")}$'), balance_management.end_management_and_show_financial_menu),
                MessageHandler(filters.TEXT & ~filters.COMMAND, balance_management.process_user_id),
            ],
            balance_management.SHOW_USER_BALANCE: [
                CallbackQueryHandler(balance_management.prompt_for_amount, pattern=r'^balance_')
            ],
            balance_management.GET_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, balance_management.process_amount),
                CallbackQueryHandler(balance_management.show_user_balance_menu, pattern=r'^back_to_user_menu_from_amount$')
            ],
        },
        fallbacks=cancel_fallback,
    )

    # --- Conversation Handlers for Gift Management ---
    welcome_gift_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(gift.prompt_for_welcome_gift, pattern='^admin_gift_set_welcome$')],
        states={
            gift.GET_WELCOME_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift.save_welcome_gift)]
        },
        fallbacks=[CommandHandler('cancel', main_menu_fallback)],
        conversation_timeout=300,
        map_to_parent={
            ConversationHandler.END: gift.MENU
        }
    )

    universal_gift_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(gift.prompt_for_universal_gift, pattern='^admin_gift_send_universal$')],
        states={
            gift.GET_UNIVERSAL_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift.prompt_for_gift_confirmation)],
            gift.CONFIRM_UNIVERSAL_GIFT: [MessageHandler(filters.TEXT & ~filters.COMMAND, gift.process_universal_gift)]
        },
        fallbacks=[CommandHandler('cancel', main_menu_fallback)],
        conversation_timeout=300,
        map_to_parent={
            ConversationHandler.END: gift.MENU
        }
    )

    gift_management_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(gift.show_gift_management_menu, pattern='^admin_gift_management$')],
        states={
            gift.MENU: [
                welcome_gift_conv,
                universal_gift_conv,
                CallbackQueryHandler(show_financial_menu, pattern='^back_to_financial_settings$')
            ]
        },
        fallbacks=[CommandHandler('cancel', main_menu_fallback)],
        conversation_timeout=600,
        allow_reentry=True
    )

    # --- Register ALL Conversation Handlers ---
    application.add_handler(card_settings_conv)
    application.add_handler(plan_name_settings_conv)
    application.add_handler(unlimited_plans_admin.add_unlimited_plan_conv)
    application.add_handler(volumetric_plans_admin.edit_base_price_conv)
    application.add_handler(volumetric_plans_admin.add_tier_conv)
    application.add_handler(volumetric_plans_admin.edit_tier_conv)
    application.add_handler(wallet_admin.edit_amounts_conv)
    application.add_handler(balance_management_conv)
    application.add_handler(gift_management_conv)

    # --- Register Standalone Handlers ---
    financial_settings_btn = f'^{_("keyboards.settings_and_tools.financial_settings")}$'
    
    standalone_handlers = [
        MessageHandler(filters.Regex(financial_settings_btn), show_financial_menu),
        CallbackQueryHandler(show_payment_methods_menu, pattern=r'^show_payment_methods$'),
        CallbackQueryHandler(show_plan_management_menu, pattern=r'^show_plan_management$'),
        CallbackQueryHandler(wallet_admin.show_wallet_settings_menu, pattern=r'^admin_wallet_settings$'),
        CallbackQueryHandler(show_financial_menu, pattern=r'^back_to_financial_settings$'),
        CallbackQueryHandler(back_to_main_settings_menu, pattern=r'^back_to_main_settings$'),
        CallbackQueryHandler(show_plan_management_menu, pattern=r'^back_to_plan_management$'),
        CallbackQueryHandler(unlimited_plans_admin.manage_unlimited_plans_menu, pattern=r'^admin_manage_unlimited$'),
        CallbackQueryHandler(unlimited_plans_admin.confirm_delete_plan, pattern=r'^unlimplan_delete_'),
        CallbackQueryHandler(unlimited_plans_admin.execute_delete_plan, pattern=r'^unlimplan_do_delete_'),
        CallbackQueryHandler(unlimited_plans_admin.toggle_plan_status, pattern=r'^unlimplan_toggle_'),
        CallbackQueryHandler(volumetric_plans_admin.manage_volumetric_plans_menu, pattern=r'^admin_manage_volumetric$'),
        CallbackQueryHandler(volumetric_plans_admin.confirm_delete_tier, pattern=r'^vol_delete_tier_'),
        CallbackQueryHandler(volumetric_plans_admin.execute_delete_tier, pattern=r'^vol_do_delete_tier_'),
        CallbackQueryHandler(show_coming_soon, pattern=r'^coming_soon$'),
    ]
    application.add_handlers(standalone_handlers)
    LOGGER.info("Financials settings module handlers registered successfully.")
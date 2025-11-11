# FILE: modules/customer/handler.py (FINAL, FULLY CORRECTED VERSION)

import logging
import re
from telegram import Update
from telegram.ext import (
    Application, ConversationHandler, MessageHandler,
    CallbackQueryHandler, filters, CommandHandler, ContextTypes
)
from telegram.ext.filters import BaseFilter

from shared.translator import _
from .actions import (
    purchase, renewal, service, panel, guide, wallet,
    receipt as receipt_actions,
    custom_purchase as custom_purchase_actions,
    unlimited_purchase as unlimited_purchase_actions,
    charge as charge_actions,
    test_account as test_account_actions
)



from config import config
from shared.callback_types import SendReceipt

LOGGER = logging.getLogger(__name__)

application: Application = None

class NotInBuilderMode(BaseFilter):
    def filter(self, update: Update) -> bool:
        global application
        if not application:
            LOGGER.warning("Application context not available for NotInBuilderMode filter.")
            return True
        context = ContextTypes.DEFAULT_TYPE.from_update(update, application)
        if context:
            return not context.user_data.get('in_builder_mode', False)
        return True

not_in_builder_mode_filter = NotInBuilderMode()

def _gatekeeper(handler_func, filter_instance):
    async def wrapped_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if filter_instance.filter(update):
            return await handler_func(update, context)
        else:
            LOGGER.info(f"[GATEKEEPER] Blocked handler '{handler_func.__name__}' because user is in builder mode.")
            pass
    return wrapped_handler

MAIN_MENU_REGEX = r'^(🛍️خرید اشتـــراک|📊ســــــــرویس‌های من|📱 راهــــــــــنمای اتصال|🔙 بازگشت به منوی اصلی)$'

IGNORE_MAIN_MENU_FILTER = filters.TEXT & ~filters.COMMAND & ~filters.Regex(MAIN_MENU_REGEX)

DISPLAY_PANEL = 0
charge_actions.DISPLAY_PANEL = DISPLAY_PANEL

def register(app: Application):
    from modules.general.actions import end_conv_and_reroute, start
    from shared.callbacks import main_menu_fallback
    
    global application
    application = app
    LOGGER.info("Registering UNIFIED customer module handlers...")
    
    unified_fallback = [
    MessageHandler(filters.Regex(MAIN_MENU_REGEX), end_conv_and_reroute),
    CommandHandler('cancel', main_menu_fallback) # <-- CHANGE THIS LINE
]

    my_service_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.my_services"))}$'), service.handle_my_service)],
        states={
            service.CHOOSE_SERVICE: [
                CallbackQueryHandler(service.choose_service, pattern=r'^select_service_'),
                CallbackQueryHandler(service.handle_service_page_change, pattern=r'^page_(fwd|back)_')
            ],
            service.DISPLAY_SERVICE: [

                CallbackQueryHandler(service.choose_service, pattern=r'^select_service_'),
                CallbackQueryHandler(renewal.handle_renewal_request, pattern=r'^customer_renew_request_'),
                CallbackQueryHandler(service.confirm_reset_subscription, pattern=r'^customer_reset_sub_'),
                CallbackQueryHandler(service.request_delete_service, pattern=r'^request_delete_'),
                CallbackQueryHandler(service.start_data_purchase, pattern=r'^purchase_data_'),
                CallbackQueryHandler(service.toggle_auto_renew, pattern=r'^toggle_autorenew_')
            ],
            service.CONFIRM_RESET_SUB: [
                CallbackQueryHandler(service.execute_reset_subscription, pattern=r'^do_reset_sub_'),
                CallbackQueryHandler(service.choose_service, pattern=r'^select_service_')
            ],
            service.CONFIRM_DELETE: [
                CallbackQueryHandler(service.confirm_delete_request, pattern=r'^confirm_delete_'),
                CallbackQueryHandler(service.choose_service, pattern=r'^select_service_')
            ],
            service.PROMPT_FOR_DATA_AMOUNT: [
                MessageHandler(IGNORE_MAIN_MENU_FILTER, service.calculate_price_and_confirm)
            ],
            service.CONFIRM_DATA_PURCHASE: [
                CallbackQueryHandler(service.generate_data_purchase_invoice, pattern=r'^confirm_data_purchase_final$'),
                CallbackQueryHandler(service.choose_service, pattern=r'^select_service_')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(service.back_to_main_menu_customer, pattern=r'^customer_back_to_main_menu$'),
            *unified_fallback
        ],
        conversation_timeout=600,
        per_message=False
    )
    
    manual_purchase_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_shop.assisted_purchase"))}$'), purchase.start_purchase_conversation)],
        states={
            purchase.GET_REQUEST_MESSAGE: [
                MessageHandler(IGNORE_MAIN_MENU_FILTER, purchase.handle_request_message)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(main_menu_fallback, pattern='^cancel_conv$'), # <-- CHANGE THIS LINE
            *unified_fallback
        ],
        conversation_timeout=600,
        per_message=False
    )
    
    receipt_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_shop.send_receipt"))}$'), receipt_actions.start_receipt_from_menu),
            CallbackQueryHandler(receipt_actions.start_receipt_from_invoice, pattern=f'^{SendReceipt.PREFIX}:')
        ],
        states={
            receipt_actions.CHOOSE_INVOICE: [CallbackQueryHandler(receipt_actions.select_invoice_for_receipt, pattern='^select_invoice_')],
            receipt_actions.GET_RECEIPT_PHOTO: [
                MessageHandler(filters.PHOTO & ~filters.COMMAND, receipt_actions.handle_receipt_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receipt_actions.warn_for_photo)
            ]
        },
        fallbacks=[
            CallbackQueryHandler(receipt_actions.cancel_receipt_upload, pattern='^cancel_receipt_upload$'),
            *unified_fallback
        ],
        conversation_timeout=600,
        per_message=False
    )

    custom_purchase_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_shop.custom_volume_plan"))}$'), custom_purchase_actions.start_custom_purchase),
            CallbackQueryHandler(_gatekeeper(custom_purchase_actions.start_custom_purchase, not_in_builder_mode_filter), pattern=r'^shop_custom_volume$')
        ],
        states={
            # ✨ NEW STATE ADDED HERE
            custom_purchase_actions.SELECT_PANEL: [
                CallbackQueryHandler(custom_purchase_actions.select_panel_and_ask_username, pattern=r'^cp_select_panel_')
            ],
            custom_purchase_actions.ASK_USERNAME: [MessageHandler(IGNORE_MAIN_MENU_FILTER, custom_purchase_actions.get_username_and_ask_volume)],
            custom_purchase_actions.ASK_VOLUME: [MessageHandler(IGNORE_MAIN_MENU_FILTER, custom_purchase_actions.get_volume_and_ask_for_duration)],
            custom_purchase_actions.ASK_DURATION: [MessageHandler(IGNORE_MAIN_MENU_FILTER, custom_purchase_actions.get_duration_and_confirm)],
            custom_purchase_actions.CONFIRM_PLAN: [CallbackQueryHandler(custom_purchase_actions.generate_invoice, pattern='^confirm_custom_plan$')],
        },
        fallbacks=[
            CallbackQueryHandler(custom_purchase_actions.cancel_custom_purchase, pattern=f'^{custom_purchase_actions.CANCEL_CALLBACK_DATA}$'),
            *unified_fallback
        ],
        conversation_timeout=600,
        per_message=False
    )

    # ADD THIS ENTIRE BLOCK BACK

    unlimited_purchase_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f'^{re.escape(_("keyboards.customer_shop.unlimited_volume_plan"))}$'), 
                unlimited_purchase_actions.start_unlimited_purchase
            ),
            CallbackQueryHandler(
                _gatekeeper(unlimited_purchase_actions.start_unlimited_purchase, not_in_builder_mode_filter), 
                pattern=r'^shop_unlimited_volume$'
            )
        ],
        states={
            # ✨ NEW STATE ADDED
            unlimited_purchase_actions.SELECT_PANEL: [
                CallbackQueryHandler(unlimited_purchase_actions.select_panel_and_ask_username, pattern=r'^unlim_select_panel_')
            ],
            unlimited_purchase_actions.ASK_USERNAME: [MessageHandler(IGNORE_MAIN_MENU_FILTER, unlimited_purchase_actions.get_username_and_ask_plan)],
            unlimited_purchase_actions.CHOOSE_PLAN: [CallbackQueryHandler(unlimited_purchase_actions.select_plan_and_confirm, pattern=r'^unlim_select_')],
            unlimited_purchase_actions.CONFIRM_UNLIMITED_PLAN: [CallbackQueryHandler(unlimited_purchase_actions.generate_unlimited_invoice, pattern=r'^unlim_confirm_final$')],
        },
        fallbacks=[
            CallbackQueryHandler(unlimited_purchase_actions.cancel_unlimited_purchase, pattern=f'^{unlimited_purchase_actions.CANCEL_CALLBACK_DATA}$'),
            MessageHandler(filters.Regex(MAIN_MENU_REGEX), end_conv_and_reroute),
        ],
        conversation_timeout=600,
    )

    # The next line should be: wallet_conv = ConversationHandler(...)
    
    wallet_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.wallet_charge"))}$'), wallet.show_wallet_panel)],
        states={
            DISPLAY_PANEL: [
                CallbackQueryHandler(charge_actions.start_charge_process, pattern=f'^{wallet.CALLBACK_CHARGE_WALLET}$')
            ],
            charge_actions.CHOOSE_AMOUNT: [
                CallbackQueryHandler(charge_actions.handle_predefined_amount, pattern=f'^{charge_actions.CALLBACK_PREFIX_AMOUNT}'),
                CallbackQueryHandler(charge_actions.prompt_for_custom_amount, pattern=f'^{charge_actions.CALLBACK_CUSTOM_AMOUNT}$')
            ],
            charge_actions.GET_CUSTOM_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, charge_actions.handle_custom_amount)
            ],
            charge_actions.CONFIRM_CHARGE: [
                CallbackQueryHandler(charge_actions.generate_charge_invoice, pattern=f'^{charge_actions.CALLBACK_CONFIRM_FINAL}$')
            ]
        },
        fallbacks=[
            CallbackQueryHandler(charge_actions.back_to_wallet_panel, pattern=f'^{charge_actions.CALLBACK_CANCEL_CHARGE}$'),
            CallbackQueryHandler(wallet.close_wallet_panel, pattern=f'^{wallet.CALLBACK_WALLET_CLOSE}$'),
            *unified_fallback
        ],
        conversation_timeout=600,
        per_message=False
    )

    test_account_conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.test_account"))}$'), 
                test_account_actions.handle_test_account_request
            )
        ],
        states={
            test_account_actions.ASK_USERNAME: [
                MessageHandler(
                    filters.TEXT & 
                    ~filters.COMMAND & 
                    ~filters.Regex(MAIN_MENU_REGEX) & 
                    ~filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.test_account"))}$'), 
                    test_account_actions.get_username_and_create_account
                )
            ]
        },
        fallbacks=unified_fallback,
        conversation_timeout=300,
        per_message=False
    )
    
    app.add_handler(my_service_conv, group=1)
    app.add_handler(manual_purchase_conv, group=1)
    app.add_handler(receipt_conv, group=1)
    app.add_handler(custom_purchase_conv, group=1)
    app.add_handler(unlimited_purchase_conv, group=1)
    app.add_handler(wallet_conv, group=1)
    app.add_handler(test_account_conv, group=1)

    app.add_handler(CallbackQueryHandler(guide.show_guides_as_new_message, pattern=r'^show_connection_guides$'), group=1)
    app.add_handler(MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.shop"))}$'), panel.show_customer_panel), group=1)
    app.add_handler(MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.connection_guide"))}$'), guide.show_guides_to_customer), group=1)
    app.add_handler(MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.general.back_to_main_menu"))}$'), start), group=1)
    app.add_handler(CallbackQueryHandler(renewal.handle_renewal_request, pattern=r'^customer_renew_request_'), group=1)
    
    app.add_handler(CallbackQueryHandler(_gatekeeper(panel.show_customer_panel, not_in_builder_mode_filter), pattern=r'^customer_shop$'), group=1)
    app.add_handler(CallbackQueryHandler(_gatekeeper(service.handle_my_service, not_in_builder_mode_filter), pattern=r'^customer_my_services$'), group=1)
    app.add_handler(CallbackQueryHandler(_gatekeeper(guide.show_guides_to_customer, not_in_builder_mode_filter), pattern=r'^customer_guides$'), group=1)
    app.add_handler(CallbackQueryHandler(_gatekeeper(test_account_actions.handle_test_account_request, not_in_builder_mode_filter), pattern=r'^customer_test_account$'), group=1)

    if config.SUPPORT_USERNAME:
        app.add_handler(MessageHandler(filters.Regex(f'^{re.escape(_("keyboards.customer_main_menu.support"))}$'), purchase.handle_support_button), group=1)
        app.add_handler(CallbackQueryHandler(guide.send_guide_content_to_customer, pattern=r'^customer_show_guide_'), group=1)
        app.add_handler(CallbackQueryHandler(guide.show_guides_to_customer, pattern=r'^customer_back_to_guides$'), group=1)
        app.add_handler(CallbackQueryHandler(guide.close_guide_menu, pattern=r'^close_guide_menu$'), group=1)
# FILE: modules/payment/handler.py (CORRECTED VERSION)

from telegram.ext import Application, CallbackQueryHandler
from modules.general.actions import send_main_menu
from shared.translator import _

# Import actions from the refactored files
from .actions.approval import approve_payment, reject_payment, confirm_manual_payment
from .actions.wallet import pay_with_wallet
from .actions.renewal import send_manual_invoice
from .actions.manual import manual_invoice_conv

async def handle_payment_back_button(update, context):
    """Handles the 'Back to Menu' button on invoices."""
    query = update.callback_query
    await query.answer()
    
    context.user_data['is_rerouted_from_conv'] = True
    
    await send_main_menu(update, context)


def register(application: Application):
    """Registers all handlers for the payment module."""
    
    application.add_handler(manual_invoice_conv)

    handlers = [
        # Approval/Rejection Handlers
        CallbackQueryHandler(approve_payment, pattern=r'^admin_approve_'),
        CallbackQueryHandler(reject_payment, pattern=r'^admin_reject_'),
        CallbackQueryHandler(confirm_manual_payment, pattern=r'^confirm_manual_receipt_'),
        CallbackQueryHandler(approve_payment, pattern=r'^approve_data_top_up_'),

        # Wallet Payment Handler
        CallbackQueryHandler(pay_with_wallet, pattern=r'^wallet_pay_'),

        # Manual invoice trigger from admin panel
        CallbackQueryHandler(send_manual_invoice, pattern=r'^fin_send_invoice_'),
        
        # Generic back button on invoices
        CallbackQueryHandler(handle_payment_back_button, pattern=r'^payment_back_to_menu$'),
    ]
    
    application.add_handlers(handlers)
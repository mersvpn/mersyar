# --- START OF FILE modules/payment/actions/creation.py ---
import logging
import html
from typing import Dict, Any, Optional
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from database.crud import pending_invoice as crud_invoice
from database.crud import financial_setting as crud_financial
from shared.translator import _
from shared.callback_types import SendReceipt
from shared.financial_utils import calculate_payment_details

LOGGER = logging.getLogger(__name__)


async def create_and_send_invoice(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    plan_details: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Creates an invoice in the database, calculates payment details,
    and sends a beautifully formatted invoice message to the user.
    Returns the created invoice object on success, None on failure.
    """
    price = plan_details.get('price')
    if price is None:
        LOGGER.error(f"Invoice creation failed: price not set in plan_details")
        return None

    payment_info = await calculate_payment_details(user_id, price)
    payable_amount = payment_info["payable_amount"]
    paid_from_wallet = payment_info["paid_from_wallet"]
    has_sufficient_funds = payment_info["has_sufficient_funds"]

    invoice_obj = await crud_invoice.create_pending_invoice({
        'user_id': user_id,
        'plan_details': plan_details,
        'price': price,
        'from_wallet_amount': paid_from_wallet
    })

    if not invoice_obj:
        LOGGER.error(f"Failed to create pending invoice in DB for user {user_id}.")
        try:
            await context.bot.send_message(chat_id=user_id, text=_("financials_payment.error_processing_plan"))
        except Exception: pass
        return None

    financial_settings = await crud_financial.load_financial_settings()
    if not financial_settings or not financial_settings.card_holder or not financial_settings.card_number:
        LOGGER.warning("Financial settings (card holder/number) are not configured.")
        try:
            await context.bot.send_message(chat_id=user_id, text=_("financials_payment.invoice_generation_unavailable"))
        except Exception: pass
        return None

    # --- START: Building the new, beautiful invoice text ---
    
    invoice_text = f"🧾 <b>{_('financials_payment.invoice_title_custom_plan')}</b>\n"
    invoice_text += "➖➖➖➖➖➖➖➖➖➖\n"
    invoice_text += f"📄 {_('financials_payment.invoice_number_label')} <code>{invoice_obj.invoice_id}</code>\n\n"
    
    invoice_text += f"🔻 <b>{_('financials_payment.invoice_service_details_label')}</b>\n"
    
    if plan_details.get("panel_name"):
        invoice_text += f"🖥️ {_('financials_payment.invoice_panel_name_label')} <b>{html.escape(plan_details['panel_name'])}</b>\n"
    if plan_details.get("username"):
        invoice_text += f"👤 {_('financials_payment.invoice_username_label')} <code>{html.escape(plan_details['username'])}</code>\n"

    invoice_type = plan_details.get("invoice_type", "LEGACY")
    
    if invoice_type == "NEW_USER_UNLIMITED":
        invoice_text += f"✨ {_('financials_payment.invoice_plan_type_label')} <b>{html.escape(plan_details.get('plan_name', 'N/A'))}</b>\n"
    elif invoice_type in ["NEW_USER_CUSTOM", "RENEWAL", "DATA_TOP_UP"]:
        invoice_text += f"📦 {_('financials_payment.invoice_volume_label')} <b>{plan_details.get('volume', 'N/A')} GB</b>\n"
        duration = plan_details.get('duration', 'N/A')
        duration_text = f"{duration} روز" if invoice_type != "DATA_TOP_UP" else _("customer.customer_service.data_top_up_label")
        invoice_text += f"⏳ {_('financials_payment.invoice_duration_label')} <b>{duration_text}</b>\n"
    
    invoice_text += f"\n💳 <b>{_('financials_payment.invoice_payment_summary_label')}</b>\n"
    invoice_text += f"💰 {_('financials_payment.invoice_price_label')} <code>{price:,.0f}</code> تومان\n"
    
    if paid_from_wallet > 0:
        invoice_text += f"💸 {_('financials_payment.invoice_wallet_deduction_label')} <code>{paid_from_wallet:,.0f}</code> تومان\n"
    
    invoice_text += "➖➖➖➖➖➖➖➖➖➖\n"
    invoice_text += f"✅ <b>{_('financials_payment.invoice_payable_amount_label')}</b> <code>{payable_amount:,.0f}</code> <b>تومان</b>\n\n"
    
    if payable_amount > 0:
        invoice_text += f"👇 <b>{_('financials_payment.invoice_payment_details_label')}</b>\n"
        invoice_text += f"▪️ {_('financials_payment.invoice_card_number_label')} <code>{financial_settings.card_number}</code>\n"
        invoice_text += f"▪️ {_('financials_payment.invoice_card_holder_label')} <b>{financial_settings.card_holder}</b>\n\n"
        invoice_text += f"{_('financials_payment.invoice_footer_prompt')}"
        
    # --- END: Building the new invoice text ---

    keyboard_rows = []
    
    if has_sufficient_funds:
        wallet_button_text = _("financials_payment.button_pay_with_wallet_full", price=f"{int(price):,}")
        keyboard_rows.append([
            InlineKeyboardButton(wallet_button_text, callback_data=f"wallet_pay_{invoice_obj.invoice_id}")
        ])
    elif payable_amount > 0:
        send_receipt_callback = SendReceipt(invoice_id=invoice_obj.invoice_id).to_string()
        keyboard_rows.append(
            [InlineKeyboardButton(_("financials_payment.button_send_receipt"), callback_data=send_receipt_callback)]
        )

    keyboard_rows.append([InlineKeyboardButton(_("financials_payment.button_back_to_menu"), callback_data="payment_back_to_menu")])
    keyboard = InlineKeyboardMarkup(keyboard_rows)
    
    try:
        # Use ParseMode.HTML for the new format
        await context.bot.send_message(chat_id=user_id, text=invoice_text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
        LOGGER.info(f"Invoice #{invoice_obj.invoice_id} sent to user {user_id}. Payable: {payable_amount}, From Wallet: {paid_from_wallet}")
        return invoice_obj
    except Exception as e:
        LOGGER.error(f"Failed to send invoice #{invoice_obj.invoice_id} to user {user_id}: {e}", exc_info=True)
        try:
            await context.bot.send_message(chat_id=user_id, text=_("financials_payment.error_sending_invoice"))
        except Exception: pass
        return None
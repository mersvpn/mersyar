# --- START OF FILE modules/payment/actions/renewal.py ---
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import TelegramError

from database.crud import (
    financial_setting as crud_financial,
    user_note as crud_user_note,
    marzban_link as crud_marzban_link,
    pending_invoice as crud_invoice
)
from shared.translator import _
from shared.callback_types import SendReceipt, StartManualInvoice
from shared.financial_utils import calculate_payment_details

LOGGER = logging.getLogger(__name__)


async def send_renewal_invoice_to_user(context: ContextTypes.DEFAULT_TYPE, user_telegram_id: int, username: str, renewal_days: int, price: int, data_limit_gb: int):
    try:
        financials = await crud_financial.load_financial_settings()
        if not financials or not financials.card_holder or not financials.card_number:
            LOGGER.error(f"Cannot send renewal invoice to {username}: Financial settings not configured.")
            return

        # 1. اول محاسبه را انجام می‌دهیم
        payment_info = await calculate_payment_details(user_telegram_id, price)
        payable_amount = payment_info["payable_amount"]
        paid_from_wallet = payment_info["paid_from_wallet"]
        has_sufficient_funds = payment_info["has_sufficient_funds"]

        # 2. جزئیات پلن را آماده می‌کنیم
        plan_details = {
            'invoice_type': 'RENEWAL',
            'username': username,
            'duration': renewal_days,
            'volume': data_limit_gb,
            'price': price
        }
        
        # 3. فاکتور را می‌سازیم و مقدار کسر از کیف پول را هم ذخیره می‌کنیم
        invoice_obj = await crud_invoice.create_pending_invoice({
            'user_id': user_telegram_id,
            'plan_details': plan_details,
            'price': price,
            'from_wallet_amount': paid_from_wallet  # <-- این مقدار بسیار مهم است
        })

        if not invoice_obj:
            LOGGER.error(f"Failed to create renewal invoice for {username}.")
            return

        invoice_id = invoice_obj.invoice_id
        payment_info = await calculate_payment_details(user_telegram_id, price)
        payable_amount = payment_info["payable_amount"]
        paid_from_wallet = payment_info["paid_from_wallet"]
        has_sufficient_funds = payment_info["has_sufficient_funds"]

        invoice_text = _("financials_payment.invoice_title_renewal")
        invoice_text += _("financials_payment.invoice_number", id=invoice_id)
        invoice_text += _("financials_payment.invoice_service", username=f"`{username}`")
        invoice_text += _("financials_payment.invoice_renewal_period", days=renewal_days)
        invoice_text += "-------------------------------------\n"
        invoice_text += _("financials_payment.invoice_price", price=f"`{price:,.0f}`")

        if paid_from_wallet > 0:
            invoice_text += _("financials_payment.invoice_wallet_deduction", amount=f"`{paid_from_wallet:,.0f}`")

        invoice_text += "-------------------------------------\n"
        invoice_text += _("financials_payment.invoice_payable_amount", amount=f"`{payable_amount:,.0f}`")
        
        if payable_amount > 0:
            invoice_text += _("financials_payment.invoice_payment_details", card_number=f"`{financials.card_number}`", card_holder=f"`{financials.card_holder}`")
            invoice_text += _("financials_payment.invoice_footer_prompt")
        
        keyboard_rows = []
        if has_sufficient_funds:
            wallet_button_text = _("financials_payment.button_pay_with_wallet_full", price=f"{int(price):,}")
            keyboard_rows.append([
                InlineKeyboardButton(wallet_button_text, callback_data=f"wallet_pay_{invoice_id}")
            ])
        elif payable_amount > 0:
            send_receipt_callback = SendReceipt(invoice_id=invoice_id).to_string()
            keyboard_rows.append(
                [InlineKeyboardButton(_("financials_payment.button_send_receipt"), callback_data=send_receipt_callback)]
            )
        
        keyboard_rows.append([InlineKeyboardButton(_("financials_payment.button_back_to_menu"), callback_data="payment_back_to_menu")])
        keyboard = InlineKeyboardMarkup(keyboard_rows)

        await context.bot.send_message(chat_id=user_telegram_id, text=invoice_text, parse_mode=ParseMode.MARKDOWN, reply_markup=keyboard)
        LOGGER.info(f"Renewal invoice #{invoice_id} sent to user {username} ({user_telegram_id}). Payable: {payable_amount}, From Wallet: {paid_from_wallet}")

    except TelegramError as e:
        if "bot was blocked" in str(e).lower():
            LOGGER.warning(f"Could not send renewal invoice to {user_telegram_id}: User blocked the bot.")
        else:
            LOGGER.error(f"Telegram error sending renewal invoice to {user_telegram_id}: {e}", exc_info=True)
    except Exception as e:
        LOGGER.error(f"Unexpected error in send_renewal_invoice_to_user for {username}: {e}", exc_info=True)


async def send_manual_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    username = query.data.split('_', 2)[-1]
    admin_chat_id = update.effective_chat.id

    try:
        customer_id = await crud_marzban_link.get_telegram_id_by_marzban_username(username)
        if not customer_id:
            await context.bot.send_message(admin_chat_id, _("financials_payment.error_customer_telegram_not_found", username=f"`{username}`"), parse_mode=ParseMode.MARKDOWN)
            return
            
        note_data = await crud_user_note.get_user_note(username)
        price = note_data.subscription_price if note_data else None
        duration = note_data.subscription_duration if note_data else None
        
        if price is None or duration is None:
            callback_obj = StartManualInvoice(customer_id=customer_id, username=username)
            admin_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(
                _("financials_payment.button_create_send_invoice"), 
                callback_data=callback_obj.to_string()
            )]])
            await context.bot.send_message(
                admin_chat_id, 
                _("financials_payment.note_not_set_prompt_manual_invoice", username=f"`{username}`"), 
                reply_markup=admin_keyboard, 
                parse_mode=ParseMode.MARKDOWN
            )
            return

        data_limit_gb = note_data.subscription_data_limit_gb if note_data and note_data.subscription_data_limit_gb is not None else 0
        await send_renewal_invoice_to_user(
            context,
            user_telegram_id=customer_id,
            username=username,
            renewal_days=duration,
            price=price,
            data_limit_gb=data_limit_gb
        )
        await context.bot.send_message(admin_chat_id, _("financials_payment.invoice_sent_to_user_success_no_id"))

    except Exception as e:
        LOGGER.error(f"Failed to send manual invoice for user {username}: {e}", exc_info=True)
        await context.bot.send_message(admin_chat_id, _("financials_payment.unknown_error"), parse_mode=ParseMode.MARKDOWN)

# --- END OF FILE modules/payment/actions/renewal.py ---
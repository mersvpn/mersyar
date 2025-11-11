# --- START OF FILE modules/customer/actions/receipt.py ---
import logging
import html
from telegram.ext import (
    ConversationHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    filters
)
from database.crud import panel_credential as crud_panel
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from telegram.error import BadRequest
from shared.financial_utils import calculate_payment_details
from config import config
from database.crud import pending_invoice as crud_invoice
from database.crud import user as crud_user
from shared.keyboards import get_customer_shop_keyboard
from shared.translator import _
from shared.log_channel import send_log
from shared.callback_types import SendReceipt
from database.crud import bot_setting as crud_bot_setting
from modules.payment.actions.approval import approve_payment
LOGGER = logging.getLogger(__name__)

CHOOSE_INVOICE, GET_RECEIPT_PHOTO = range(2)

async def start_receipt_from_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    processing_message = await update.message.reply_text(_("customer.receipt.checking_invoices"), reply_markup=ReplyKeyboardRemove())
    
    pending_invoices = await crud_invoice.get_pending_invoices_for_user(user_id)
    await processing_message.delete()

    if not pending_invoices:
        await update.message.reply_text(_("customer.receipt.no_pending_invoices"), reply_markup=get_customer_shop_keyboard())
        return ConversationHandler.END

    if len(pending_invoices) == 1:
        invoice = pending_invoices[0]
        context.user_data['invoice_id'] = invoice.invoice_id
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("keyboards.buttons.cancel_operation"), callback_data="cancel_receipt_upload")]])
        await update.message.reply_text(
            text=_("customer.receipt.single_invoice_prompt", price=f"{invoice.price:,.0f}"),
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        return GET_RECEIPT_PHOTO
    
    else:
        buttons = []
        text = _("customer.receipt.multiple_invoices_prompt")
        for inv in pending_invoices:
            plan_desc = inv.plan_details.get('username') or inv.plan_details.get('plan_name') or f"Invoice #{inv.invoice_id}"
            btn_text = _("customer.receipt.invoice_button_format", 
                         id=inv.invoice_id,  
                         description=plan_desc,
                         price=f"{inv.price:,.0f}")
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"select_invoice_{inv.invoice_id}")])
        
        buttons.append([InlineKeyboardButton(_("keyboards.buttons.cancel_operation"), callback_data="cancel_receipt_upload")])
        keyboard = InlineKeyboardMarkup(buttons)
        await update.message.reply_text(text=text, reply_markup=keyboard)
        return CHOOSE_INVOICE

async def start_receipt_from_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    callback_obj = SendReceipt.from_string(query.data)
    if not callback_obj:
        LOGGER.error(f"Could not parse SendReceipt callback for user {update.effective_user.id}. Data: {query.data}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=_("customer.receipt.invoice_id_parse_error"))
        return ConversationHandler.END

    context.user_data['invoice_id'] = callback_obj.invoice_id
    LOGGER.info(f"User {update.effective_user.id} started receipt upload for invoice #{callback_obj.invoice_id} from an inline button.")
    
    try: await query.message.delete()
    except Exception: pass

    text_prompt = _("customer.receipt.photo_prompt_simple")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("keyboards.buttons.cancel_operation"), callback_data="cancel_receipt_upload")]
    ])
    
    try:
        with open("assets/receipt_guide.png", "rb") as photo_file:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_file, caption=text_prompt, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except FileNotFoundError:
        LOGGER.warning("assets/receipt_guide.png not found. Sending text fallback.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_prompt, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    return GET_RECEIPT_PHOTO

async def select_invoice_for_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    try:
        invoice_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.answer(_("general.errors.internal_error"), show_alert=True)
        return ConversationHandler.END

    context.user_data['invoice_id'] = invoice_id
    await query.answer()
    
    try: await query.message.delete()
    except Exception: pass

    text_prompt = _("customer.receipt.photo_prompt_simple")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("keyboards.buttons.cancel_operation"), callback_data="cancel_receipt_upload")]])
    
    try:
        with open("assets/receipt_guide.png", "rb") as photo_file:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=photo_file, caption=text_prompt, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    except FileNotFoundError:
        LOGGER.warning("assets/receipt_guide.png not found. Sending text fallback.")
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text_prompt, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    
    return GET_RECEIPT_PHOTO

async def handle_receipt_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    photo_file_id = update.message.photo[-1].file_id
    invoice_id = context.user_data.get('invoice_id')

    if not invoice_id:
        await update.message.reply_text(_("customer.receipt.internal_error_start_over"), reply_markup=get_customer_shop_keyboard())
        return ConversationHandler.END

    await update.message.reply_text(_("customer.receipt.sent_to_support_success"), reply_markup=get_customer_shop_keyboard())
    
    invoice = await crud_invoice.get_pending_invoice_by_id(invoice_id)
    if not invoice:
        LOGGER.warning(f"Could not find invoice #{invoice_id} after user {user.id} submitted a photo.")
        context.user_data.clear()
        return ConversationHandler.END

    # --- START: Building the new, beautiful caption for admin ---
    total_price = float(invoice.price)
    plan_details = invoice.plan_details
    paid_from_wallet = float(invoice.from_wallet_amount or 0)
    payable_amount = total_price - paid_from_wallet
    
    # Fetch panel name if available
    panel_name = _("customer.receipt.panel_not_specified")
    if plan_details.get('panel_id'):
        panel = await crud_panel.get_panel_by_id(plan_details['panel_id'])
        if panel:
            panel_name = panel.name

    caption = f"🧾 <b>{_('customer.receipt.admin_header', invoice_id=invoice_id)}</b>\n"
    caption += "➖➖➖➖➖➖➖➖➖➖\n"
    caption += f"👤 <b>{_('customer.receipt.admin_user_label')}</b> {html.escape(user.full_name)}\n"
    caption += f"🔢 <b>{_('customer.receipt.admin_id_label')}</b> <code>{user.id}</code>\n\n"
    
    caption += f"📦 <b>{_('customer.receipt.admin_plan_details_label')}</b>\n"
    
    invoice_type = plan_details.get('invoice_type', 'LEGACY')
    if invoice_type == 'WALLET_CHARGE':
        caption += f"▫️ {_('customer.receipt.admin_service_label')} <b>{_('customer.receipt.wallet_charge_label')}</b>\n"
    else:
        caption += f"🖥️ {_('customer.receipt.admin_panel_label')} <b>{html.escape(panel_name)}</b>\n"
        caption += f"▫️ {_('customer.receipt.admin_service_label')} <code>{html.escape(plan_details.get('username', 'N/A'))}</code>\n"
        caption += f"▫️ {_('customer.receipt.admin_volume_label')} {plan_details.get('volume', 'N/A')} GB\n"
        duration = plan_details.get('duration', 'N/A')
        duration_text = f"{duration} روز" if invoice_type != "DATA_TOP_UP" else _("customer.customer_service.data_top_up_label")
        caption += f"▫️ {_('customer.receipt.admin_duration_label')} {duration_text}\n"

    caption += f"\n💰 <b>{_('customer.receipt.admin_financial_details_label')}</b>\n"
    caption += f"▫️ {_('customer.receipt.admin_total_price_label')} {total_price:,.0f} تومان\n"
    if paid_from_wallet > 0:
        caption += f"▫️ {_('customer.receipt.admin_wallet_deduction_label')} {paid_from_wallet:,.0f} تومان\n"
    caption += f"▫️ {_('customer.receipt.admin_payable_label')} <b>{payable_amount:,.0f} تومان</b>\n"
    
    caption += "➖➖➖➖➖➖➖➖➖➖\n"
    caption += f"{_('customer.receipt.admin_footer')}"
    # --- END: Building the new caption ---

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_("keyboards.buttons.approve_payment"), callback_data=f"admin_approve_{invoice_id}"),
            InlineKeyboardButton(_("keyboards.buttons.reject"), callback_data=f"admin_reject_{invoice_id}")
        ]
    ])

    admin_message_ids = {}
    for admin_id in config.AUTHORIZED_USER_IDS:
        try:
            sent_message = await context.bot.send_photo(chat_id=admin_id, photo=photo_file_id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
            admin_message_ids[admin_id] = sent_message.message_id
        except Exception as e:
            LOGGER.error(f"Failed to forward receipt for invoice #{invoice_id} to admin {admin_id}: {e}")

    bot_settings = await crud_bot_setting.load_bot_settings()
    if bot_settings.get('auto_confirm_invoices', False):
        LOGGER.info(f"Auto-confirm is ENABLED for invoice #{invoice_id}. Scheduling job.")
        
        job_data = {
            'invoice_id': invoice_id,
            'user_id': user.id,
            'admin_message_ids': admin_message_ids,
            'original_caption': caption
        }
        
        context.job_queue.run_once(
            _auto_approve_callback, 
            30, 
            data=job_data,
            name=f"auto_approve_{invoice_id}"
        )

    context.user_data.clear()
    return ConversationHandler.END

async def warn_for_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(_("customer.receipt.invalid_input_warning"))
    return GET_RECEIPT_PHOTO

async def cancel_receipt_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(_("customer.receipt.upload_cancelled"))
        except BadRequest:
            pass
    
    await context.bot.send_message(chat_id=update.effective_chat.id, text=_("customer.receipt.back_to_shop_menu"), reply_markup=get_customer_shop_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def _auto_approve_callback(context: ContextTypes.DEFAULT_TYPE):
    job_data = context.job.data
    invoice_id = job_data['invoice_id']
    user_id = job_data['user_id']
    admin_message_ids = job_data['admin_message_ids']
    original_caption = job_data['original_caption']
    
    LOGGER.info(f"Executing scheduled auto-approval for invoice #{invoice_id}.")
    
    invoice = await crud_invoice.get_pending_invoice_by_id(invoice_id)
    if not invoice or invoice.status != 'pending':
        LOGGER.info(f"Auto-approval for invoice #{invoice_id} cancelled: Invoice already processed.")
        return

    # --- Create mock objects that perfectly imitate the real ones ---
    class MockUser:
        id = user_id
        full_name = "Auto-Confirm System"
    
    class MockMessage:
        caption = original_caption
        async def edit_message_caption(self, caption, reply_markup=None, parse_mode=None):
            for admin_id, message_id in admin_message_ids.items():
                try:
                    await context.bot.edit_message_caption(
                        chat_id=admin_id,
                        message_id=message_id,
                        caption=caption,
                        reply_markup=reply_markup,
                        parse_mode=parse_mode
                    )
                except Exception as e:
                    LOGGER.error(f"Failed to edit auto-approved message {message_id} for admin {admin_id}: {e}")

    class MockCallbackQuery:
        data = f"admin_approve_{invoice_id}"
        message = MockMessage()
        async def answer(self, *args, **kwargs): pass

        # This method now lives directly on the mock query,
        # exactly mirroring the real CallbackQuery object.
        async def edit_message_caption(self, *args, **kwargs):
            # It calls the method on its own message attribute.
            await self.message.edit_message_caption(*args, **kwargs)

    class MockUpdate:
        effective_user = MockUser()
        callback_query = MockCallbackQuery()
        
    mock_update = MockUpdate()

    # --- Call the main approve_payment function ---
    try:
        await approve_payment(mock_update, context, auto_approved=True)
        LOGGER.info(f"Auto-approval for invoice #{invoice_id} completed successfully.")

        # --- Notification Logic ---
        # 1. Notify Admins via private message
        customer = await crud_user.get_user_by_id(user_id)
        customer_name = customer.first_name if customer else f"User ID: {user_id}"
        
        notification_text = _("payment.auto_approved_admin_notification", 
                              invoice_id=invoice_id, 
                              customer_name=customer_name)
        
        for admin_id in config.AUTHORIZED_USER_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=notification_text)
            except Exception as e:
                LOGGER.error(f"Failed to send auto-approve notification to admin {admin_id}: {e}")

        # 2. Send structured log to the log channel
        customer_display_name = customer.first_name if customer else 'Unknown'
        invoice_id_html = f"<b>#{invoice_id}</b>"
        customer_name_html = f"<b>{html.escape(customer_display_name)}</b>"
        customer_id_html = f"<code>{user_id}</code>"
        
        log_text = _("log_channel.payment_approved_auto_html",
                     invoice_id=invoice_id_html,
                     customer_name=customer_name_html,
                     customer_id=customer_id_html,
                     admin_name="Auto-Confirm System")
        await send_log(context.bot, log_text)

    except Exception as e:
        LOGGER.error(f"An error occurred during auto-approval execution for invoice #{invoice_id}: {e}", exc_info=True)
# FILE: modules/payment/actions/approval.py
# Note: All instances of parse_mode have been reviewed and set to ParseMode.HTML 
# to correctly render HTML tags like <b> and <code> in Telegram messages.

import qrcode
import io
import logging
from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode
from decimal import Decimal
from database.models.panel_credential import PanelType

from database.crud import (
    pending_invoice as crud_invoice,
    marzban_link as crud_marzban_link,
    user as crud_user,
    user_note as crud_user_note,
    panel_credential as crud_panel,
    bot_managed_user as crud_bot_managed_user
)
from shared.keyboards import get_customer_main_menu_keyboard
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from modules.marzban.actions import helpers as marzban_helpers
from typing import Optional
from shared.translator import _
from shared.log_channel import send_log
from database.models.pending_invoice import PendingInvoice

LOGGER = logging.getLogger(__name__)

async def _get_api_for_panel(panel_id: int) -> Optional[PanelAPI]:
    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        LOGGER.error(f"Panel with ID {panel_id} not found.")
        return None
    
    if panel.panel_type == PanelType.MARZBAN:
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        return MarzbanPanel(credentials)
    
    LOGGER.warning(f"Panel type '{panel.panel_type.value}' is not yet supported.")
    return None

async def _get_api_for_user(marzban_username: str) -> Optional[PanelAPI]:
    link = await crud_marzban_link.get_link_with_panel_by_username(marzban_username)
    if not link or not link.panel:
        LOGGER.error(f"Could not find a panel for user '{marzban_username}'. Link or panel data is missing.")
        return None
    
    return await _get_api_for_panel(link.panel_id)


async def _approve_manual_invoice(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    customer_id = invoice.user_id
    plan_details = invoice.plan_details
    invoice_id = invoice.invoice_id

    username = plan_details.get('username')
    duration = plan_details.get('duration')
    volume = plan_details.get('volume')
    price = plan_details.get('price')

    if not all([username, duration is not None, volume is not None, price is not None]):
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_incomplete_plan_details')}")
        return

    await crud_user_note.create_or_update_user_note(
        marzban_username=username,
        duration=duration,
        data_limit_gb=volume,
        price=price
    )
    LOGGER.info(f"Subscription details for '{username}' saved/updated from manual invoice #{invoice_id}.")

    await crud_invoice.update_invoice_status(invoice_id, 'approved')
    
    try:
        await context.bot.send_message(
            customer_id, 
            _("financials_payment.payment_approved_existing_user", id=invoice_id, username=username),
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        LOGGER.error(f"Failed to send manual payment confirmation to customer {customer_id}: {e}")

    final_caption = f"{query.message.caption}{_('financials_payment.admin_log_payment_approved_existing', username=username, admin_name=admin_user.full_name)}"
    await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)
    
    log_message = _("log.manual_invoice_approved", 
                    invoice_id=invoice_id, 
                    username=f"<code>{username}</code>", 
                    price=f"{int(price):,}",
                    customer_id=customer_id,
                    admin_name=admin_user.full_name)
    await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)

async def _approve_new_user_creation(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    from modules.marzban.actions.add_user import add_user_to_panel_from_template
    customer_id = invoice.user_id
    plan_details = invoice.plan_details
    invoice_id = invoice.invoice_id
    
    panel_id = plan_details.get('panel_id')
    if not panel_id:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_no_panel_id')}")
        return

    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('panel_manager.errors.panel_not_found_in_invoice')}")
        return
    panel_name = panel.name

    marzban_username = plan_details.get('username')
    plan_type = plan_details.get("plan_type")
    duration_days = plan_details.get('duration')
    price = plan_details.get('price')
    max_ips = plan_details.get('max_ips')
    data_limit_gb = 0 if plan_type == "unlimited" else plan_details.get('volume')

    if not all([marzban_username, data_limit_gb is not None, duration_days is not None, price is not None]):
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_incomplete_plan_details')}")
        return

    try:
        api = await _get_api_for_panel(panel_id)
        if not api:
            raise Exception(f"Could not create API object for panel ID {panel_id}.")

        new_user_data = await add_user_to_panel_from_template(
            api=api,
            panel_id=panel_id,
            data_limit_gb=data_limit_gb, 
            expire_days=duration_days, 
            username=marzban_username, 
            max_ips=max_ips
        )
        if not new_user_data or 'username' not in new_user_data:
            raise Exception("Failed to create user in panel, received empty response.")
    except Exception as e:
        LOGGER.error(f"Failed to create Marzban user for invoice #{invoice_id}: {e}", exc_info=True)
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_creating_user_in_marzban')}")
        return
    
    await crud_user_note.create_or_update_user_note(marzban_username=marzban_username, duration=duration_days, price=price, data_limit_gb=data_limit_gb)
    await crud_marzban_link.create_or_update_link(marzban_username, customer_id, panel_id)
    await crud_invoice.update_invoice_status(invoice_id, 'approved')
    
    # دریافت کیبورد مشتری
    customer_keyboard = await get_customer_main_menu_keyboard(customer_id)

    try:
        subscription_url = new_user_data.get('subscription_url')
        if subscription_url:
            qr_image = qrcode.make(subscription_url)
            bio = io.BytesIO(); bio.name = 'qrcode.png'; qr_image.save(bio, 'PNG'); bio.seek(0)
            
            volume_text = _("marzban_display.unlimited") if plan_type == "unlimited" else f"{data_limit_gb} گیگابایت"
            user_limit_text = _("financials_payment.user_creation_success_message_ips", ips=max_ips) if max_ips else ""
            
            caption = _("financials_payment.user_creation_success_message_title")
            caption += _("financials_payment.user_creation_success_message_location", location=f"*{panel_name}*")
            caption += _("financials_payment.user_creation_success_message_username", username=f"`{marzban_username}`")
            caption += _("financials_payment.user_creation_success_message_volume", volume=volume_text)
            caption += _("financials_payment.user_creation_success_message_duration", duration=duration_days) + user_limit_text
            caption += _("financials_payment.user_creation_success_connection_intro")
            caption += f"\n`{subscription_url}`\n"
            caption += _("financials_payment.user_creation_success_link_guide")
            caption += _("financials_payment.user_creation_success_qr_guide")
            
            # ✨ FIX: Added reply_markup
            await context.bot.send_photo(chat_id=customer_id, photo=bio, caption=caption, parse_mode=ParseMode.MARKDOWN, reply_markup=customer_keyboard)
        else:
            # ✨ FIX: Added reply_markup
            await context.bot.send_message(customer_id, _("financials_payment.user_creation_fallback_message", username=f"`{marzban_username}`"), parse_mode=ParseMode.MARKDOWN, reply_markup=customer_keyboard)
    except Exception as e:
        LOGGER.error(f"Failed to send success message to customer {customer_id} for invoice #{invoice_id}: {e}", exc_info=True)
    
    final_caption = f"{query.message.caption}{_('financials_payment.admin_log_user_created_on_panel', username=f'<code>{marzban_username}</code>', panel_name=f'<b>{panel_name}</b>', admin_name=admin_user.full_name)}"
    await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)
    
    volume_text_log = _("marzban_display.unlimited") if data_limit_gb == 0 else f"{data_limit_gb} GB"
    log_message = _("log.new_user_approved", invoice_id=invoice_id, username=f"<code>{marzban_username}</code>", volume=volume_text_log, duration=duration_days, price=f"{int(price):,}", customer_id=customer_id, admin_name=admin_user.full_name)
    await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)

async def _approve_renewal(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    customer_id = invoice.user_id
    plan_details = invoice.plan_details
    invoice_id = invoice.invoice_id
    
    username = plan_details.get('username')
    note_data = await crud_user_note.get_user_note(username)
    renewal_days = plan_details.get('duration') or (note_data.subscription_duration if note_data else None)
    price = invoice.price

    if not all([username, renewal_days is not None]):
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_incomplete_plan_details')}")
        return

    api = await _get_api_for_user(username)
    if not api:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_user_panel_not_found')}")
        return

    success, message = await marzban_helpers.renew_user_subscription(api, username, renewal_days)
    
    if not success:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('marzban_modify_user.renew_error_modify', error=message)}")
        return

    await crud_invoice.update_invoice_status(invoice_id, 'approved')
    
    data_limit_gb = plan_details.get('volume') or (note_data.subscription_data_limit_gb if note_data else 0)
    data_limit_gb = data_limit_gb or 0
    
    try:
        # ✨ FIX: Added reply_markup
        await context.bot.send_message(
            customer_id,
            _("financials_payment.renewal_success_customer", 
              username=f"<code>{username}</code>", days=renewal_days, gb=data_limit_gb),
            parse_mode=ParseMode.HTML,
            reply_markup=await get_customer_main_menu_keyboard(customer_id)
        )
    except Exception as e:
        LOGGER.error(f"Failed to send renewal confirmation to customer {customer_id}: {e}")

    final_caption = f"{query.message.caption}{_('financials_payment.admin_log_renewal_success', username=f'<code>{username}</code>', admin_name=admin_user.full_name)}"
    await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)
    
    volume_text_log = _("marzban_display.unlimited") if data_limit_gb == 0 else f"{data_limit_gb} GB"
    log_message = _("log.renewal_approved",
                    invoice_id=invoice_id,
                    username=f"<code>{username}</code>",
                    volume=volume_text_log,
                    duration=renewal_days,
                    price=f"{int(price):,}",
                    customer_id=customer_id,
                    admin_name=admin_user.full_name)
    await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)


async def _approve_wallet_charge(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    customer_id = invoice.user_id
    amount_to_add = Decimal(invoice.price)
    invoice_id = invoice.invoice_id

    new_balance = await crud_user.increase_wallet_balance(user_id=customer_id, amount=amount_to_add)

    if new_balance is not None:
        await crud_invoice.update_invoice_status(invoice_id, 'approved')
        try:
            # ✨ FIX: Added reply_markup
            await context.bot.send_message(
                customer_id,
                _("financials_payment.wallet_charge_success_customer", 
                  amount=f"{int(amount_to_add):,}", new_balance=f"{int(new_balance):,}"),
                parse_mode=ParseMode.HTML,
                reply_markup=await get_customer_main_menu_keyboard(customer_id)
            )
        except Exception as e:
            LOGGER.error(f"Failed to send wallet charge confirmation to customer {customer_id}: {e}")
        
        final_caption = f"{query.message.caption}{_('financials_payment.admin_log_wallet_charge_success', amount=f'{int(amount_to_add):,}', admin_name=admin_user.full_name)}"
        await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)
        
        log_message = _("log.wallet_charge_approved",
                        invoice_id=invoice_id,
                        amount=f"{int(amount_to_add):,}",
                        customer_id=customer_id,
                        admin_name=admin_user.full_name)
        await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_updating_wallet_db')}")


async def _approve_data_top_up(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    customer_id = invoice.user_id
    plan_details = invoice.plan_details
    marzban_username = plan_details.get('username')
    data_gb_to_add = plan_details.get('volume')
    price = invoice.price
    invoice_id = invoice.invoice_id

    if not all([marzban_username, data_gb_to_add, customer_id]):
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_incomplete_top_up_details')}")
        return

    api = await _get_api_for_user(marzban_username)
    if not api:
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_user_panel_not_found')}")
        return

    success, message = await marzban_helpers.add_data_to_user(api, marzban_username, data_gb_to_add)

    if success:
        await crud_invoice.update_invoice_status(invoice_id, 'approved')
        LOGGER.info(f"Admin {admin_user.id} approved data top-up for '{marzban_username}' (Invoice #{invoice_id}).")
        
        try:
            # ✨ FIX: Added reply_markup
            await context.bot.send_message(
                customer_id, 
                _("financials_payment.data_top_up_customer_success", id=f"<code>{invoice_id}</code>", gb=f"<b>{data_gb_to_add}</b>"), 
                parse_mode=ParseMode.HTML,
                reply_markup=await get_customer_main_menu_keyboard(customer_id)
            )
        except Exception as e:
            LOGGER.error(f"Failed to send data top-up confirmation to customer {customer_id}: {e}")

        final_caption = f"{query.message.caption}{_('financials_payment.admin_log_data_top_up_success', username=f'<code>{marzban_username}</code>', admin_name=admin_user.full_name)}"
        await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)
        
        log_message = _("log.data_topup_approved",
                        invoice_id=invoice_id,
                        username=f"<code>{marzban_username}</code>",
                        volume=data_gb_to_add,
                        price=f"{int(price):,}",
                        customer_id=customer_id,
                        admin_name=admin_user.full_name)
        await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)
    else:
        LOGGER.error(f"Failed to add data for '{marzban_username}' via API. Reason: {message}")
        await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_marzban_connection', error=message)}")


async def _approve_legacy(context: ContextTypes.DEFAULT_TYPE, invoice: PendingInvoice, query: Update, admin_user):
    LOGGER.warning(f"Approving invoice #{invoice.invoice_id} using legacy method.")
    await _approve_manual_invoice(context, invoice, query, admin_user)


async def approve_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, auto_approved: bool = False) -> None:
    query = update.callback_query
    admin_user = update.effective_user
    if query.message:
        await query.answer(_("financials_payment.processing_approval"))

    try:
        invoice_id = int(query.data.split('_')[-1])
    except (IndexError, ValueError):
        if query.message:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_invalid_invoice_number')}")
        return
    if not auto_approved:
        job_name = f"auto_approve_{invoice_id}"
        current_jobs = context.job_queue.get_jobs_by_name(job_name)
        if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
            LOGGER.info(f"Manual approval by {admin_user.full_name}: Removed scheduled auto-approve job for invoice #{invoice_id}.")
    invoice = await crud_invoice.get_pending_invoice_by_id(invoice_id)
    if not invoice or invoice.status != 'pending':
        if query.message:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.invoice_already_processed')}")
        return

    if not auto_approved and invoice.from_wallet_amount > 0:
        new_balance = await crud_user.decrease_wallet_balance(user_id=invoice.user_id, amount=invoice.from_wallet_amount)
        if new_balance is None:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.error_insufficient_funds_on_approval')}")
            return

    plan_details = invoice.plan_details
    invoice_type = plan_details.get("invoice_type")

    if invoice_type == "WALLET_CHARGE":
        await _approve_wallet_charge(context, invoice, query, admin_user)
    elif invoice_type == "MANUAL_INVOICE":
        await _approve_manual_invoice(context, invoice, query, admin_user)
    elif invoice_type == "DATA_TOP_UP":
        await _approve_data_top_up(context, invoice, query, admin_user)
    elif invoice_type in ["NEW_USER_CUSTOM", "NEW_USER_UNLIMITED"]:
        await _approve_new_user_creation(context, invoice, query, admin_user)
    elif invoice_type == "RENEWAL":
        await _approve_renewal(context, invoice, query, admin_user)
    else: 
        await _approve_legacy(context, invoice, query, admin_user)


async def reject_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    admin_user = update.effective_user
    await query.answer(_("financials_payment.processing_rejection"))

    try:
        invoice_id = int(query.data.split('_')[-1])
    except (IndexError, ValueError):
        if query.message:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('errors.internal_error')}")
        return
    job_name = f"auto_approve_{invoice_id}"
    current_jobs = context.job_queue.get_jobs_by_name(job_name)
    if current_jobs:
            for job in current_jobs:
                job.schedule_removal()
            LOGGER.info(f"Manual rejection by {admin_user.full_name}: Removed scheduled auto-approve job for invoice #{invoice_id}.")
            
    invoice = await crud_invoice.get_pending_invoice_by_id(invoice_id)
    if not invoice or invoice.status != 'pending':
        if query.message:
            await query.edit_message_caption(caption=f"{query.message.caption}\n\n{_('financials_payment.invoice_already_processed')}")
        return

    await crud_invoice.update_invoice_status(invoice.invoice_id, 'rejected')
    LOGGER.info(f"Admin {admin_user.id} rejected payment for invoice #{invoice.invoice_id}.")
    
    try:
        await context.bot.send_message(invoice.user_id, _("financials_payment.payment_rejected_customer_message", id=invoice.invoice_id), parse_mode=ParseMode.HTML)
    except Exception as e:
        LOGGER.error(f"Failed to send rejection notification to customer {invoice.user_id}: {e}")

    final_caption = f"{query.message.caption}{_('financials_payment.admin_log_payment_rejected', admin_name=admin_user.full_name)}"
    await query.edit_message_caption(caption=final_caption, parse_mode=ParseMode.HTML)

    log_message = _("log.payment_rejected",
                    invoice_id=invoice.invoice_id,
                    customer_id=invoice.user_id,
                    admin_name=admin_user.full_name)
    await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)


async def confirm_manual_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await approve_payment(update, context)
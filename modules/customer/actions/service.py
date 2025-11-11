# --- START OF FILE modules/customer/actions/service.py ---
import datetime
import jdatetime
import logging
import asyncio
from collections import defaultdict
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from config import config
from shared.translator import _
from shared.keyboards import get_customer_main_menu_keyboard, get_admin_main_menu_keyboard, get_back_to_main_menu_keyboard
# ✨ NEW IMPORTS FOR MULTI-PANEL ARCHITECTURE
from typing import Optional, List, Dict, Any
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
from modules.marzban.actions import helpers as marzban_helpers # We will use helpers here
# ---
from modules.marzban.actions.constants import GB_IN_BYTES
from modules.marzban.actions.data_manager import normalize_username
from database.crud import marzban_link as crud_marzban_link
from database.crud import user_note as crud_user_note
from database.crud import volumetric_tier as crud_volumetric
from database.crud import financial_setting as crud_financial
from modules.payment.actions.creation import create_and_send_invoice

LOGGER = logging.getLogger(__name__)

CHOOSE_SERVICE, DISPLAY_SERVICE, CONFIRM_RESET_SUB, CONFIRM_DELETE = range(4)
PROMPT_FOR_DATA_AMOUNT, CONFIRM_DATA_PURCHASE = range(4, 6)
ITEMS_PER_PAGE = 8


async def _get_api_for_panel(panel) -> Optional[PanelAPI]:
    """Factory to create an API object from a panel DB object."""
    if panel.panel_type.value == "marzban":
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        return MarzbanPanel(credentials)
    return None
async def _get_api_for_user(marzban_username: str) -> Optional[PanelAPI]:
    """Finds which panel a user belongs to and returns an API object for it."""
    link = await crud_marzban_link.get_link_with_panel_by_username(marzban_username)
    if not link or not link.panel:
        LOGGER.error(f"Could not find a panel for user '{marzban_username}'.")
        return None
    
    panel = link.panel
    if panel.panel_type.value == "marzban":
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        return MarzbanPanel(credentials)
    return None

async def _build_paginated_service_keyboard(services: list, page: int = 0) -> InlineKeyboardMarkup:
    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    keyboard = []
    for user in services[start_index:end_index]:
        status_icon = "🟢" if user.get('status') == 'active' else "🔴"
        button_text = f"{status_icon} {user['username']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"select_service_{user['username']}")])
    nav_buttons = []
    total_pages = (len(services) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(_("keyboards.buttons.pagination_prev"), callback_data=f"page_back_{page-1}"))
    if total_pages > 1:
        page_indicator = _("keyboards.buttons.pagination_page", current=page + 1, total=total_pages)
        nav_buttons.append(InlineKeyboardButton(page_indicator, callback_data="noop"))
    if end_index < len(services):
        nav_buttons.append(InlineKeyboardButton(_("keyboards.buttons.pagination_next"), callback_data=f"page_fwd_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton(_("keyboards.buttons.cancel_and_return"), callback_data="customer_back_to_main_menu")])
    return InlineKeyboardMarkup(keyboard)

async def handle_service_page_change(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    direction, page_str = query.data.split('_')[1:]
    page = int(page_str)
    services = context.user_data.get('services_list', [])
    if not services:
        await query.edit_message_text(_("customer.customer_service.service_list_error"))
        return ConversationHandler.END
    reply_markup = await _build_paginated_service_keyboard(services, page)
    await query.edit_message_text(_("customer.customer_service.multiple_services_prompt"), reply_markup=reply_markup)
    return CHOOSE_SERVICE


async def handle_my_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    query = update.callback_query
    
    if query:
        await query.answer()
        try: await query.message.delete()
        except Exception: pass
        loading_message = await context.bot.send_message(user_id, _("customer.customer_service.loading"))
    else:
        loading_message = await update.message.reply_text(_("customer.customer_service.loading"))

    try:
        links = await crud_marzban_link.get_links_by_telegram_id_with_panel(user_id)
        if not links:
            await loading_message.edit_text(_("customer.customer_service.no_service_linked"))
            return ConversationHandler.END

        # Group user links by panel to minimize API calls
        links_by_panel = defaultdict(list)
        for link in links:
            if link.panel:
                links_by_panel[link.panel].append(link.marzban_username)

        valid_accounts = []
        all_user_links = {link.marzban_username for link in links}

        async def fetch_panel_data(panel, usernames):
            api = await _get_api_for_panel(panel)
            if not api: return []
            
            # Fetch all users from the panel once
            all_panel_users_data = await api.get_all_users()
            if not all_panel_users_data: return []

            # Create a dictionary for quick lookups
            users_dict = {user['username']: user for user in all_panel_users_data}

            # Filter out the data for the specific user's services
            found_users = []
            for username in usernames:
                if username in users_dict:
                    user_data = users_dict[username]
                    user_data['panel_name'] = panel.name
                    user_data['panel_id'] = panel.id
                    found_users.append(user_data)
            return found_users

        tasks = [fetch_panel_data(panel, usernames) for panel, usernames in links_by_panel.items()]
        results = await asyncio.gather(*tasks)
        
        for user_list in results:
            valid_accounts.extend(user_list)
        
        found_usernames = {acc['username'] for acc in valid_accounts}
        dead_links_usernames = all_user_links - found_usernames

        if dead_links_usernames:
            LOGGER.info(f"Cleaning up {len(dead_links_usernames)} dead links for user {user_id}: {dead_links_usernames}")
            for username in dead_links_usernames:
                await crud_marzban_link.delete_marzban_link(username)
        
        if not valid_accounts:
            await loading_message.edit_text(_("customer.customer_service.no_valid_service_found"))
            return ConversationHandler.END

        # Filter out test accounts
        note_tasks = [crud_user_note.get_user_note(acc['username']) for acc in valid_accounts]
        notes = await asyncio.gather(*note_tasks)
        final_accounts = [acc for i, acc in enumerate(valid_accounts) if not (notes[i] and notes[i].is_test_account)]
        
        if not final_accounts:
            await loading_message.edit_text(_("customer.customer_service.no_valid_service_found"))
            return ConversationHandler.END
        
        if len(final_accounts) == 1:
            return await display_service_details(user_id, loading_message, context, final_accounts[0]['username'])
        else:
            sorted_services = sorted(final_accounts, key=lambda u: u['username'].lower())
            context.user_data['services_list'] = sorted_services
            reply_markup = await _build_paginated_service_keyboard(sorted_services, page=0)
            await loading_message.edit_text(_("customer.customer_service.multiple_services_prompt"), reply_markup=reply_markup)
            return CHOOSE_SERVICE

    except Exception as e:
        LOGGER.error(f"Error in handle_my_service for user {user_id}: {e}", exc_info=True)
        await loading_message.edit_text(_("customer.customer_service.panel_connection_error"))
        return ConversationHandler.END



async def display_service_details(user_id: int, message_to_edit, context: ContextTypes.DEFAULT_TYPE, marzban_username: str) -> int:
    await message_to_edit.edit_text(text=_("customer.customer_service.getting_service_info", username=marzban_username))
    api = await _get_api_for_user(marzban_username)
    user_info = await api.get_user_data(marzban_username) if api else None

    if not user_info or "error" in user_info:
        await message_to_edit.edit_text(_("customer.customer_service.service_not_found_in_panel"))
        return ConversationHandler.END

    is_active = user_info.get('status') == 'active'
    message = ""

    if is_active:
        usage_gb = (user_info.get('used_traffic') or 0) / GB_IN_BYTES
        limit_gb = (user_info.get('data_limit') or 0) / GB_IN_BYTES
        usage_str = f"{usage_gb:.2f} GB"
        if limit_gb > 0:
            usage_str += f" / {limit_gb:.0f} GB"
        else:
            usage_str += _("customer.customer_service.unlimited_usage_suffix")

        expire_str = _("customer.customer_service.unlimited_label")
        duration_str = _("customer.customer_service.duration_unknown")

        note_data = await crud_user_note.get_user_note(normalize_username(marzban_username))
        if note_data and note_data.subscription_duration:
            duration_str = _("customer.customer_service.duration_days", days=note_data.subscription_duration)

        if user_info.get('expire'):
            expire_date = datetime.datetime.fromtimestamp(user_info['expire'])
            time_left = expire_date - datetime.datetime.now()
            if time_left.total_seconds() > 0:
                jalali_date = jdatetime.datetime.fromgregorian(datetime=expire_date)
                days_left_str = _("customer.customer_service.days_remaining", days=time_left.days)
                expire_str = f"{jalali_date.strftime('%Y/%m/%d')} ({days_left_str})"
            else:
                is_active = False
                expire_str = _("customer.customer_service.expired_status")
        
        sub_url = user_info.get('subscription_url', _("customer.customer_service.not_found"))
        
        message = _("customer.customer_service.active_details_message",
                    username=marzban_username,
                    usage=usage_str,
                    duration=duration_str,
                    expiry=expire_str,
                    sub_url=sub_url)
    
    if not is_active:
        message = _("customer.customer_service.inactive_details_message", username=marzban_username)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(_("keyboards.buttons.renew_this_service"), callback_data=f"customer_renew_request_{marzban_username}")],
            [InlineKeyboardButton(_("keyboards.buttons.back_to_main_menu"), callback_data="customer_back_to_main_menu")]
        ])
    else:
        auto_renew_is_on = await crud_marzban_link.is_auto_renew_enabled(user_id, marzban_username)
        
        if auto_renew_is_on:
            auto_renew_text = _("keyboards.buttons.auto_renew_active")
            auto_renew_callback = f"toggle_autorenew_off:{marzban_username}"
        else:
            auto_renew_text = _("keyboards.buttons.auto_renew_inactive")
            auto_renew_callback = f"toggle_autorenew_on:{marzban_username}"

        keyboard_rows = [
            [
                InlineKeyboardButton(_("keyboards.buttons.request_renewal"), callback_data=f"customer_renew_request_{marzban_username}"),
                InlineKeyboardButton(_("keyboards.buttons.purchase_data"), callback_data=f"purchase_data_{marzban_username}")
            ],
            [
                InlineKeyboardButton(auto_renew_text, callback_data=auto_renew_callback)
            ],
            [
                InlineKeyboardButton(_("keyboards.buttons.reset_subscription"), callback_data=f"customer_reset_sub_{marzban_username}"),
                InlineKeyboardButton(_("keyboards.buttons.request_delete"), callback_data=f"request_delete_{marzban_username}")
            ],
            [InlineKeyboardButton(_("keyboards.buttons.back_to_main_menu"), callback_data="customer_back_to_main_menu")]
        ]
        keyboard = InlineKeyboardMarkup(keyboard_rows)

    await message_to_edit.edit_text(message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return DISPLAY_SERVICE


# (✨ FINAL REPLACEMENT for choose_service)
async def choose_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    marzban_username = query.data.split('select_service_')[-1]
    user_id = query.from_user.id
    
    # This directly returns the next state from the called function.
    return await display_service_details(user_id, query.message, context, marzban_username)


async def back_to_main_menu_customer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    task = context.user_data.pop('service_loader_task', None)
    if task and not task.done():
        task.cancel()
    
    user_id = update.effective_user.id
    message_text = _("general.operation_cancelled")
    
    if user_id in config.AUTHORIZED_USER_IDS:
        final_keyboard = get_admin_main_menu_keyboard()
    else:
        final_keyboard = await get_customer_main_menu_keyboard(user_id=user_id)
        
    try:
        await query.message.delete()
    except Exception:
        pass
        
    await context.bot.send_message(
        chat_id=user_id,
        text=message_text,
        reply_markup=final_keyboard
    )
    
    context.user_data.clear()
    return ConversationHandler.END


async def confirm_reset_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    username = query.data.split('_')[-1]
    context.user_data['service_username'] = username
    text = _("customer.customer_service.reset_sub_warning")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("keyboards.buttons.reset_sub_confirm"), callback_data=f"do_reset_sub_{username}")],
        [InlineKeyboardButton(_("keyboards.buttons.reset_sub_cancel"), callback_data=f"select_service_{username}")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_RESET_SUB


async def execute_reset_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    username = query.data.split('_')[-1]
    if not username:
        await query.edit_message_text(_("general.errors.username_not_found"))
        return ConversationHandler.END
    await query.edit_message_text(_("customer.customer_service.resetting_sub_link", username=f"`{username}`"))
    api = await _get_api_for_user(username)
    success, result = (await api.revoke_subscription(username)) if api else (False, "Panel not found")
    if success:
        new_sub_url = result.get('subscription_url', _("customer.customer_service.not_found"))
        text = _("customer.customer_service.reset_sub_successful", sub_url=new_sub_url)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("keyboards.buttons.back_to_details"), callback_data=f"select_service_{username}")]])
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        text = _("customer.customer_service.reset_sub_failed", error=result)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("keyboards.buttons.back_to_details"), callback_data=f"select_service_{username}")]])
        await query.edit_message_text(text, reply_markup=keyboard)
    return DISPLAY_SERVICE


async def request_delete_service(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    username = query.data.split('_')[-1]
    text = _("customer.customer_service.delete_request_warning", username=f"`{username}`")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("keyboards.buttons.delete_confirm"), callback_data=f"confirm_delete_{username}")],
        [InlineKeyboardButton(_("keyboards.buttons.delete_cancel"), callback_data=f"select_service_{username}")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_DELETE


async def confirm_delete_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    username = query.data.split('_')[-1]
    user = update.effective_user
    await query.edit_message_text(_("customer.customer_service.delete_request_sent"))
    if config.AUTHORIZED_USER_IDS:
        user_info_str = f"{user.full_name}"
        if user.username: user_info_str += f" (@{user.username})"
        user_info_str += f"\nUser ID: `{user.id}`"
        message_to_admin = _("customer.customer_service.delete_request_admin_notification", user_info=user_info_str, username=f"`{username}`")
        admin_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_("keyboards.buttons.confirm_delete_admin"), callback_data=f"delete_{username}")]])
        for admin_id in config.AUTHORIZED_USER_IDS:
            try:
                await context.bot.send_message(chat_id=admin_id, text=message_to_admin, reply_markup=admin_keyboard, parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                LOGGER.error(f"Failed to send delete request to admin {admin_id} for {username}: {e}", exc_info=True)
    return ConversationHandler.END


async def start_data_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    marzban_username = query.data.split('purchase_data_')[-1]
    context.user_data['purchase_data_username'] = marzban_username
    tiers = await crud_volumetric.get_all_pricing_tiers()
    if not tiers:
        await query.edit_message_text(_("customer.customer_service.purchase_data_not_configured"))
        return ConversationHandler.END
    text = _("customer.customer_service.purchase_data_prompt", username=f"`{marzban_username}`")
    await query.message.delete()
    await context.bot.send_message(chat_id=query.message.chat_id, text=text, reply_markup=get_back_to_main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN)
    return PROMPT_FOR_DATA_AMOUNT


async def calculate_price_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        volume_gb = int(update.message.text.strip())
        if volume_gb <= 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("customer.customer_service.invalid_number_input"))
        return PROMPT_FOR_DATA_AMOUNT
    tiers = await crud_volumetric.get_all_pricing_tiers()
    price_per_gb = 0
    if tiers:
        for tier in tiers:
            if volume_gb <= tier.volume_limit_gb:
                price_per_gb = tier.price_per_gb
                break
        if price_per_gb == 0: price_per_gb = tiers[-1].price_per_gb
    if price_per_gb == 0:
        await update.message.reply_text(_("customer.customer_service.pricing_system_error"))
        return ConversationHandler.END
    total_price = volume_gb * price_per_gb
    username = context.user_data.get('purchase_data_username')
    context.user_data['purchase_data_details'] = {
        "volume": volume_gb, 
        "price": total_price, 
        "plan_type": "data_top_up", 
        "username": username,
        "invoice_type": "DATA_TOP_UP"
    }
    text = _("customer.customer_service.data_purchase_invoice_preview", username=f"`{username}`", volume=volume_gb, price=total_price)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("keyboards.buttons.confirm_and_get_invoice"), callback_data="confirm_data_purchase_final")],
        [InlineKeyboardButton(_("keyboards.buttons.cancel"), callback_data=f"select_service_{username}")]])
    await update.message.reply_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_DATA_PURCHASE


async def generate_data_purchase_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(_("customer.customer_service.generating_invoice"))
    user_id = query.from_user.id
    purchase_details = context.user_data.get('purchase_data_details')
    if not purchase_details:
        await query.edit_message_text(_("customer.customer_service.purchase_info_not_found"))
        return ConversationHandler.END
    
    await query.message.delete()
    
    invoice_display_details = {
        "type": "data_top_up",
        "volume": f"+{purchase_details['volume']} GB",
        "duration": _("customer.customer_service.data_top_up_label"),
        "price": purchase_details['price'],
        **purchase_details
    }
    
    invoice = await create_and_send_invoice(context, user_id, invoice_display_details)
    
    if not invoice:
        await context.bot.send_message(chat_id=user_id, text=_("customer.customer_service.system_error_retry"))

    context.user_data.clear()
    return ConversationHandler.END


async def toggle_auto_renew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    
    try:
        prefix, marzban_username = query.data.split(':', 1)
        action = prefix.split('_')[-1]
        new_status = (action == "on")
    except (ValueError, IndexError):
        LOGGER.error(f"Invalid callback data for toggle_auto_renew: {query.data}")
        await query.answer(_("general.errors.internal_error"), show_alert=True)
        return DISPLAY_SERVICE

    user_id = update.effective_user.id
    
    await crud_marzban_link.set_auto_renew_status(user_id, marzban_username, new_status)

    if new_status:
        alert_text = _("customer.customer_service.auto_renew_activated_alert")
    else:
        alert_text = _("customer.customer_service.auto_renew_deactivated_alert")
    
    await query.answer(alert_text, show_alert=True)
    
    message_to_edit = query.message
    return await display_service_details(user_id, message_to_edit, context, marzban_username)

# --- END OF FILE modules/customer/actions/service.py ---
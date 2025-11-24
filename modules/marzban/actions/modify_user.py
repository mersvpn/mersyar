# FILE: modules/marzban/actions/modify_user.py (FINAL ROBUST VERSION)
import html
import datetime
import logging
import asyncio 
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from shared.log_channel import send_log
from shared.keyboards import get_back_to_main_menu_keyboard

from database.crud import marzban_link as crud_marzban_link
from database.crud import user_note as crud_user_note
from .display import show_user_details_panel
from .constants import GB_IN_BYTES, DEFAULT_RENEW_DAYS
from .data_manager import normalize_username
# ✨ NEW IMPORTS FOR MULTI-PANEL ARCHITECTURE
from typing import Optional
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
from modules.marzban.actions import helpers as marzban_helpers
# ✨ Import PanelType Enum
from database.models.panel_credential import PanelType

LOGGER = logging.getLogger(__name__)

async def _get_api_for_panel(panel_id: int) -> Optional[PanelAPI]:
    """Helper factory to create an API object from a panel DB object."""
    try:
        panel = await crud_panel.get_panel_by_id(panel_id)
        if not panel:
            LOGGER.error(f"[API FACTORY] Panel with ID {panel_id} not found in DB.")
            return None
        
        # ✨ ROBUST FIX: Use Enum directly for comparison
        if panel.panel_type == PanelType.MARZBAN:
            credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
            return MarzbanPanel(credentials)
        
        LOGGER.warning(f"[API FACTORY] Panel type '{panel.panel_type}' is not supported/implemented for panel ID {panel_id}.")
        return None
    except Exception as e:
        LOGGER.error(f"[API FACTORY] Error creating API for panel {panel_id}: {e}")
        return None

# Define conversation states (Global constants)
ADD_DAYS_PROMPT, ADD_DATA_PROMPT = range(2)

async def _get_api_for_user(marzban_username: str, context: ContextTypes.DEFAULT_TYPE) -> Optional[PanelAPI]:
    """
    Finds the correct panel for a user and returns an API object for it.
    It is now resilient to DB inconsistencies and searches everywhere if needed.
    """
    normalized_username = normalize_username(marzban_username)
    
    # Priority 1: Check the database link first.
    LOGGER.info(f"[API FINDER] Trying to find panel for '{normalized_username}' via DB link...")
    link = await crud_marzban_link.get_link_with_panel_by_username(normalized_username)
    
    if link and link.panel:
        # Try to connect using the linked panel
        api = await _get_api_for_panel(link.panel.id)
        if api:
            LOGGER.info(f"[API FINDER] Found panel '{link.panel.name}' (ID: {link.panel.id}) via DB link.")
            return api
        else:
            LOGGER.warning(f"[API FINDER] Link exists for '{normalized_username}' but panel ID {link.panel.id} API could not be created. Falling back to scan.")

    # Priority 2: If no link or link failed, search ALL panels.
    LOGGER.warning(f"[API FINDER] Scanning ALL panels for user '{normalized_username}'...")
    all_panels = await crud_panel.get_all_panels()
    
    for panel in all_panels:
        try:
            api = await _get_api_for_panel(panel.id)
            if not api: continue

            # Check if user exists in this panel
            user_data = await api.get_user_data(normalized_username)
            if user_data and 'username' in user_data:
                LOGGER.info(f"[API FINDER] Found user '{normalized_username}' in panel '{panel.name}'. Updating link.")
                
                # Self-Healing: Update the link in DB so next time it's faster
                # We can't update link here easily without telegram_id, but returning API is enough for the action to work.
                return api
        except Exception as e:
            LOGGER.warning(f"[API FINDER] Failed to check panel {panel.name} for user {normalized_username}: {e}")
            continue
    
    LOGGER.error(f"[API FINDER] CRITICAL: Could not find user '{normalized_username}' in ANY configured panel.")
    return None

async def _start_modification_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_text: str, prefix: str) -> None:
    from shared.keyboards import get_back_to_main_menu_keyboard 
    
    query = update.callback_query
    username = query.data.removeprefix(prefix)
    
    context.user_data['modify_user_info'] = {
        'username': username, 'chat_id': query.message.chat_id,
        'message_id': query.message.message_id,
        'list_type': context.user_data.get('current_list_type', 'all'),
        'page_number': context.user_data.get('current_page', 1)
    }
    await query.answer()
    
    await query.message.delete()

    await context.bot.send_message(
        chat_id=query.message.chat_id, 
        text=prompt_text,
        reply_markup=get_back_to_main_menu_keyboard(), 
        parse_mode=ParseMode.MARKDOWN
    )

async def prompt_for_add_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    username = update.callback_query.data.removeprefix('add_days_')
    text = _("marzban_modify_user.prompt_add_days", username=f"`{username}`")
    await _start_modification_conversation(update, context, text, 'add_days_')
    return ADD_DAYS_PROMPT

async def prompt_for_add_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    username = update.callback_query.data.removeprefix('add_data_')
    text = _("marzban_modify_user.prompt_add_data", username=f"`{username}`")
    await _start_modification_conversation(update, context, text, 'add_data_')
    return ADD_DATA_PROMPT

async def do_add_days(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    modify_info = context.user_data.get('modify_user_info')
    if not modify_info:
        await update.message.reply_text(_("marzban_modify_user.conversation_expired"))
        return ConversationHandler.END

    try:
        days_to_add = int(update.message.text)
        if days_to_add <= 0:
            await update.message.reply_text(_("marzban_modify_user.invalid_positive_number"))
            return ADD_DAYS_PROMPT
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban_modify_user.invalid_number_input"))
        return ADD_DAYS_PROMPT

    await update.message.delete()
    
    username = modify_info['username']
    api = await _get_api_for_user(username, context)
    
    if not api:
        await context.bot.send_message(chat_id=modify_info['chat_id'], text=_("marzban_display.user_not_found"))
        return ConversationHandler.END

    user_data = await api.get_user_data(username)
    if not user_data:
        await context.bot.send_message(chat_id=modify_info['chat_id'], text=_("marzban_display.user_not_found"))
        return ConversationHandler.END

    current_expire_ts = user_data.get('expire') or 0
    start_date = datetime.datetime.fromtimestamp(max(current_expire_ts, datetime.datetime.now().timestamp()))
    new_expire_date = start_date + datetime.timedelta(days=days_to_add)
    

    payload = {
        "expire": int(new_expire_date.timestamp()),
        "status": "active"
    }
    success, message = await api.modify_user(username, payload)
    
    success_msg = _("marzban_modify_user.success_add_days", days=days_to_add) if success else _("marzban_modify_user.error_add_days", error=message)
    await show_user_details_panel(context=context, **modify_info, success_message=success_msg)
    
    if success:
        normalized_username = normalize_username(username)
        customer_id = await crud_marzban_link.get_telegram_id_by_marzban_username(normalized_username)
        if customer_id:
            try:
                notification_text = _("marzban_modify_user.customer_add_days_notification", days=days_to_add)
                await context.bot.send_message(chat_id=customer_id, text=notification_text)
            except Exception as e:
                LOGGER.warning(f"Failed to send 'add days' notification: {e}")
    
    context.user_data.pop('modify_user_info', None)
    return ConversationHandler.END

async def do_add_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    modify_info = context.user_data.get('modify_user_info')
    if not modify_info:
        await update.message.reply_text(_("marzban_modify_user.conversation_expired"))
        return ConversationHandler.END

    try:
        gb_to_add = int(update.message.text)
        if gb_to_add <= 0:
            await update.message.reply_text(_("marzban_modify_user.invalid_positive_number"))
            return ADD_DATA_PROMPT
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban_modify_user.invalid_number_input"))
        return ADD_DATA_PROMPT

    await update.message.delete()
    
    username = modify_info['username']
    api = await _get_api_for_user(username, context)
    
    if not api:
        await context.bot.send_message(chat_id=modify_info['chat_id'], text=_("marzban_display.user_not_found"))
        return ConversationHandler.END

    user_data = await api.get_user_data(username)
    if not user_data:
        await context.bot.send_message(chat_id=modify_info['chat_id'], text=_("marzban_display.user_not_found"))
        return ConversationHandler.END

    new_data_limit = user_data.get('data_limit', 0) + (gb_to_add * GB_IN_BYTES)
    
    payload = {"data_limit": new_data_limit, "status": "active"}
    success, message = await api.modify_user(username, payload)
    success_msg = _("marzban_modify_user.success_add_data", gb=gb_to_add) if success else _("marzban_modify_user.error_add_data", error=message)
    await show_user_details_panel(context=context, **modify_info, success_message=success_msg)

    if success:
        normalized_username = normalize_username(username)
        customer_id = await crud_marzban_link.get_telegram_id_by_marzban_username(normalized_username)
        if customer_id:
            try:
                notification_text = _("marzban_modify_user.customer_add_data_notification", gb=gb_to_add)
                await context.bot.send_message(chat_id=customer_id, text=notification_text)
            except Exception as e:
                LOGGER.warning(f"Failed to send 'add data' notification: {e}")

    context.user_data.pop('modify_user_info', None)
    return ConversationHandler.END

async def reset_user_traffic(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    username = query.data.removeprefix('reset_traffic_')
    await query.answer(_("marzban_modify_user.resetting_traffic", username=username))
    
    api = await _get_api_for_user(username, context)
    
    if not api:
         # If we can't find the user, we can't reset traffic. Show an alert.
         await query.answer(_("marzban_display.user_not_found"), show_alert=True)
         return

    success, message = await api.reset_user_traffic(username)
    success_msg = _("marzban_modify_user.traffic_reset_success") if success else _("marzban_modify_user.traffic_reset_error", error=message)

    # Refresh the view
    await show_user_details_panel(
        context=context, chat_id=query.message.chat_id, message_id=query.message.message_id,
        username=username, list_type=context.user_data.get('current_list_type', 'all'),
        page_number=context.user_data.get('current_page', 1), success_message=success_msg
    )

async def confirm_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    username = query.data.removeprefix('delete_')
    list_type = context.user_data.get('current_list_type', 'all')
    page_number = context.user_data.get('current_page', 1)
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("marzban_modify_user.button_confirm_delete"), callback_data=f"do_delete_user_{username}")],
        [InlineKeyboardButton(_("marzban_modify_user.button_cancel_delete"), callback_data=f"user_details_{username}_{list_type}_{page_number}")]
    ])
    await query.edit_message_text(_("marzban_modify_user.delete_confirm_prompt", username=f"<code>{html.escape(username)}</code>"), reply_markup=keyboard, parse_mode=ParseMode.HTML)

async def do_delete_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
 
    query = update.callback_query
    admin_user = update.effective_user
    
    # Aggressively clean the username to avoid "user_user1" errors
    raw_username_data = query.data.removeprefix('do_delete_')
    username = raw_username_data.replace('user_', '', 1) if raw_username_data.startswith('user_') else raw_username_data
    
    normalized_username_str = normalize_username(username)
    await query.answer()
    
    is_customer_request = "درخواست حذف سرویس" in (query.message.text or "")
    
    await query.edit_message_text(_("marzban_modify_user.deleting_user", username=f"<code>{html.escape(username)}</code>"), parse_mode=ParseMode.HTML)
    
    customer_id = await crud_marzban_link.get_telegram_id_by_marzban_username(normalized_username_str)

    api = await _get_api_for_user(username, context)
    if not api:
        await query.edit_message_text(_("marzban_display.user_not_found"))
        return

    success, message = await api.delete_user(username)
    
    if success:
        await crud_marzban_link.delete_marzban_link(normalized_username_str)
        await crud_user_note.delete_user_note(normalized_username_str)
        
        admin_mention = html.escape(admin_user.full_name)
        safe_username = html.escape(username)
        
        log_title = _("marzban_modify_user.log_delete_by_customer") if is_customer_request else _("marzban_modify_user.log_delete_by_admin")
        log_message = f"{log_title}\n\n▫️ <b>نام کاربری:</b> <code>{safe_username}</code>\n"
        log_message += _("marzban_modify_user.log_deleted_by", admin_mention=f"<b>{admin_mention}</b>")
        await send_log(context.bot, log_message, parse_mode=ParseMode.HTML)
        
        await query.edit_message_text(_("marzban_modify_user.delete_successful", username=f"<code>{safe_username}</code>"), parse_mode=ParseMode.HTML)

        if customer_id:
             try:
                await context.bot.send_message(chat_id=customer_id, text=_("marzban_modify_user.notify_customer_delete_success", username=f"<code>{safe_username}</code>"), parse_mode=ParseMode.HTML)
             except Exception as e:
                LOGGER.warning(f"Config deleted, but failed to notify customer {customer_id}: {e}")
    else:
        await query.edit_message_text(f"❌ {html.escape(str(message))}")

async def renew_user_smart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    from .display import show_user_details_panel

    query = update.callback_query
    username = query.data.removeprefix('renew_')
    normalized_username_str = normalize_username(username)
    admin_user = update.effective_user
    
    await query.answer(_("marzban_modify_user.renewing_user", username=username))
    await query.edit_message_text(
        _("marzban_modify_user.renew_in_progress", username=f"`{username}`"), 
        parse_mode=ParseMode.MARKDOWN
    )

    api = await _get_api_for_user(username, context)
    if not api:
         await query.edit_message_text(_("marzban_display.user_not_found"))
         return

    user_data = await api.get_user_data(username)
    if not user_data:
        await query.edit_message_text(_("marzban_display.user_not_found"))
        return

    note_data = await crud_user_note.get_user_note(normalized_username_str)
    
    renewal_duration_days = note_data.subscription_duration if note_data and note_data.subscription_duration else DEFAULT_RENEW_DAYS
    data_limit_gb = note_data.subscription_data_limit_gb if note_data and note_data.subscription_data_limit_gb is not None else (user_data.get('data_limit') or 0) / GB_IN_BYTES
    
    # --- قدم ۱: ریست ترافیک (بدون تغییر) ---
    success_reset, message_reset = await api.reset_user_traffic(username)
    if not success_reset:
        await query.edit_message_text(_("marzban_modify_user.renew_error_reset_traffic", error=f"`{message_reset}`"), parse_mode=ParseMode.MARKDOWN)
        return
        
    start_date = datetime.datetime.fromtimestamp(max(user_data.get('expire') or 0, datetime.datetime.now().timestamp()))
    new_expire_date = start_date + datetime.timedelta(days=renewal_duration_days)
    payload_to_modify = {
        "expire": int(new_expire_date.timestamp()), 
        "data_limit": int(data_limit_gb * GB_IN_BYTES), 
        "status": "active"
    }

    success_modify = False
    message_modify = ""
    
    for attempt in range(3): 
        success_modify, message_modify = await api.modify_user(username, payload_to_modify)
        if success_modify:
            break 
        
        LOGGER.warning(f"Renew attempt {attempt+1}/3 failed for {username}. Retrying in 1.5s...")
        await asyncio.sleep(1.5) 
    
    if not success_modify:
        await query.edit_message_text(_("marzban_modify_user.renew_error_modify", error=f"`{message_modify}`"), parse_mode=ParseMode.MARKDOWN)
        return
        
    admin_mention = escape_markdown(admin_user.full_name, version=2)
    safe_username = escape_markdown(username, version=2)
    log_message = _("marzban_modify_user.log_renew_title")
    log_message += _("marzban_modify_user.log_renew_username", username=safe_username)
    log_message += _("marzban_modify_user.log_renew_data", gb=int(data_limit_gb))
    log_message += _("marzban_modify_user.log_renew_duration", days=renewal_duration_days)
    log_message += _("marzban_modify_user.log_deleted_by", admin_mention=admin_mention)
    await send_log(context.bot, log_message, parse_mode=ParseMode.MARKDOWN_V2)

    customer_id = await crud_marzban_link.get_telegram_id_by_marzban_username(normalized_username_str)
    customer_notified = False
    if customer_id:
        try:
            customer_message = _(
                "marzban_modify_user.customer_renew_notification",
                username=f"`{username}`",
                days=renewal_duration_days,
                gb=int(data_limit_gb)
            )
            await context.bot.send_message(customer_id, customer_message, parse_mode=ParseMode.MARKDOWN)
            customer_notified = True
        except Exception as e:
            LOGGER.error(f"User {username} renewed, but failed to notify customer {customer_id}: {e}")

    if customer_notified:
        success_message = _("marzban_modify_user.renew_successful_admin_and_customer", username=f"`{username}`")
    else:
        success_message = _("marzban_modify_user.renew_successful_admin_only", username=f"`{username}`")
    
    await show_user_details_panel(
        context=context, 
        chat_id=query.message.chat_id, 
        message_id=query.message.message_id,
        username=username, 
        list_type=context.user_data.get('current_list_type', 'all'),
        page_number=context.user_data.get('current_page', 1), 
        success_message=success_message
    )
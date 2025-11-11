# FILE: modules/marzban/actions/display.py (FINAL VERSION - MODIFIED FOR CALLBACK_TYPES)

import qrcode
import io
import time
import math
import datetime
import jdatetime
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes,ConversationHandler

from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from shared.keyboards import get_panel_selection_keyboard
from config import config
from shared.keyboards import get_user_management_keyboard
# --- MODIFIED: Import new callback type ---
from shared.callback_types import StartManualInvoice
from .constants import USERS_PER_PAGE, GB_IN_BYTES
# ✨ NEW IMPORTS FOR MULTI-PANEL ARCHITECTURE
from typing import List, Dict, Any, Optional
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
from modules.marzban.actions import helpers as marzban_helpers
from shared.translator import _
# ---
from modules.general.actions import start as show_main_menu_action
from shared.auth import admin_only
from shared import panel_utils

LOGGER = logging.getLogger(__name__)


def _pad_string(input_str: str, max_len: int) -> str:
    return input_str + ' ' * (max_len - len(input_str))

def get_user_display_info(user: dict) -> tuple[str, str, bool, str, str]:
    from shared.translator import translator
    username = user.get('username', 'N/A')
    sanitized_username = username.replace('`', '')
    
    status = user.get('status', 'disabled')
    used_traffic = user.get('used_traffic') or 0
    data_limit = user.get('data_limit') or 0
    expire_timestamp = user.get('expire')
    online_at = user.get('online_at')

    prefix = translator.get("marzban.marzban_display.status_active")
    is_online = False
    days_left_str = translator.get("marzban.marzban_display.infinite")
    data_left_str = translator.get("marzban.marzban_display.infinite")

    if online_at:
        try:
            online_at_dt = datetime.datetime.fromisoformat(online_at.replace("Z", "+00:00"))
            if (datetime.datetime.now(datetime.timezone.utc) - online_at_dt).total_seconds() < 180:
                is_online = True
                prefix = translator.get("marzban.marzban_display.status_online")
        except (ValueError, TypeError): pass

    if status != 'active' or (expire_timestamp and datetime.datetime.fromtimestamp(expire_timestamp) < datetime.datetime.now()):
        prefix = translator.get("marzban.marzban_display.status_inactive")
        days_left_str = translator.get("marzban.marzban_display.expired")
    else:
        is_warning = False
        if expire_timestamp:
            time_left = datetime.datetime.fromtimestamp(expire_timestamp) - datetime.datetime.now()
            days_left_val = time_left.days + (1 if time_left.seconds > 0 else 0)
            days_left_str = translator.get("marzban.marzban_display.days_left", days=days_left_val)
            if 0 < days_left_val <= 3:
                is_warning = True
        
        if data_limit > 0:
            data_left_gb = (data_limit - used_traffic) / GB_IN_BYTES
            data_left_str = translator.get("marzban.marzban_display.data_left_gb", gb=data_left_gb)
            if data_left_gb < 1:
                is_warning = True
        
        if is_warning and not is_online:
            prefix = translator.get("marzban.marzban_display.status_warning")
            
    return prefix, sanitized_username, is_online, days_left_str, data_left_str

# ----------------- START OF MODIFIED CODE -----------------

# ----------------- START OF FINAL CODE -----------------
def _get_status_emoji(user: dict) -> str:
    """Determines the correct status emoji for a user based on their state."""
    # This check for 'unused' status has the highest priority after online status
    used_traffic = user.get('used_traffic') or 0
    if used_traffic == 0:
        return "🟣" # Unused user
        
    online_at = user.get('online_at')
    if online_at:
        try:
            online_at_dt = datetime.datetime.strptime(online_at, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            if (datetime.datetime.now(datetime.timezone.utc) - online_at_dt).total_seconds() < 180:
                return "🟢" # Online user
        except (ValueError, TypeError):
            pass

    status = user.get('status', 'disabled')
    expire_timestamp = user.get('expire')

    if status != 'active' or (expire_timestamp and datetime.datetime.fromtimestamp(expire_timestamp) < datetime.datetime.now()):
        return "🔴" # Expired/Disabled user

    is_warning = False
    if expire_timestamp:
        days_left_val = (datetime.datetime.fromtimestamp(expire_timestamp) - datetime.datetime.now()).days
        if 0 <= days_left_val <= 3:
            is_warning = True
    
        data_limit = user.get('data_limit') or 0
    if data_limit > 0:
        data_left_gb = (data_limit - used_traffic) / GB_IN_BYTES
        if data_left_gb < 1:
            is_warning = True
            
    if is_warning:
        return "🟡" # Warning user
        
    return "⚪️" # Offline but active user

def build_users_keyboard(users: list, current_page: int, total_pages: int, list_type: str) -> InlineKeyboardMarkup:
    """
    Builds a 3-column, translated keyboard for a list of users.
    Places the "Guide" button in the center of the navigation row.
    """
    from shared.translator import _  # Import the translator shortcut

    keyboard_rows = []
    
    # --- Create main rows with 3 user buttons per row ---
    for i in range(0, len(users), 3):
        row = []
        for user in users[i : i + 3]:
            username = user.get('username', 'N/A')
            panel_name = user.get('panel_name')
            panel_emoji = "🖥️" if panel_name else ""
            button_text = f"{_get_status_emoji(user)} {username}{panel_emoji}"
            panel_id = user.get('panel_id', 0)
            callback_data = f"user_details_{username}_{list_type}_{current_page}_{panel_id}"
            row.append(InlineKeyboardButton(button_text, callback_data=callback_data))
        keyboard_rows.append(row)

    # --- Build the navigation row with translated buttons ---
    nav_row = []
    
    # "Previous" button
    if current_page > 1:
        nav_row.append(InlineKeyboardButton(
            _("marzban.marzban_display.keyboard_nav_previous"),
            callback_data=f"show_users_page_{list_type}_{current_page - 1}"
        ))
    else:
        # Add a placeholder to keep the layout consistent
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))

    # "Guide" button in the middle
    nav_row.append(InlineKeyboardButton(
        _("marzban.marzban_display.keyboard_nav_guide"),
        callback_data="show_status_legend"
    ))
        
    # "Next" button
    if current_page < total_pages:
        nav_row.append(InlineKeyboardButton(
            _("marzban.marzban_display.keyboard_nav_next"),
            callback_data=f"show_users_page_{list_type}_{current_page + 1}"
        ))
    else:
        # Add a placeholder
        nav_row.append(InlineKeyboardButton(" ", callback_data="noop"))
        
    keyboard_rows.append(nav_row)

    # --- Add page number and close button in the final row ---
    page_text = _("marzban.marzban_display.keyboard_nav_page", current_page=current_page, total_pages=total_pages)
    close_text = _("marzban.marzban_display.keyboard_nav_close")

    final_row = [
        InlineKeyboardButton(page_text, callback_data="noop"),
        InlineKeyboardButton(close_text, callback_data="close_message")
    ]
    keyboard_rows.append(final_row)
    
    return InlineKeyboardMarkup(keyboard_rows)

async def show_status_legend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows a popup alert with the meaning of status emojis."""
    query = update.callback_query
    
    legend_text = (
        "راهنمای وضعیت کاربران:\n\n"
        "🟢 آنلاین (در ۳ دقیقه اخیر)\n"
        "🟣 استفاده نشده (حجم مصرفی: صفر)\n"
        "⚪️ آفلاین (فعال)\n"
        "🟡 هشدار (نزدیک به انقضا)\n"
        "🔴 منقضی / غیرفعال"
    )
    
    await query.answer(text=legend_text, show_alert=True)

# --- ADD THESE 2 NEW FUNCTIONS to modules/marzban/actions/display.py ---

async def prompt_for_panel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Entry point for user management. Displays a keyboard for panel selection.
    """
    from shared.translator import translator
    from ..handler import SELECT_PANEL # Import state from handler

    # Store a map of all panel names to their IDs for the next step
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        await update.message.reply_text(translator.get("marzban.marzban_display.no_panels_configured"))
        return ConversationHandler.END

    context.user_data['panel_name_to_id_map'] = {panel.name: panel.id for panel in all_panels}
    
    await update.message.reply_text(
        translator.get("marzban.marzban_display.select_panel_prompt"),
        reply_markup=await get_panel_selection_keyboard()
    )
    return SELECT_PANEL

async def select_panel_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles the user's panel choice, saves it, and shows the user management menu.
    """
    from ..handler import USER_MENU # Import state from handler
    panel_name = update.message.text
    panel_map = context.user_data.get('panel_name_to_id_map', {})
    
    panel_id = panel_map.get(panel_name)
    if not panel_id:
        # If the user types something random, just show the panel selection again
        await prompt_for_panel_selection(update, context)
        return ConversationHandler.END # End this and let the user re-enter

    # ✨ Store the selected panel ID and name for other functions to use
    context.user_data['selected_panel_id'] = panel_id
    context.user_data['selected_panel_name'] = panel_name
    
    # Now, show the actual user management menu
    await show_user_management_menu(update, context)
    return USER_MENU

@admin_only
async def show_user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator  
    await update.message.reply_text(translator.get("marzban.marzban_display.user_management_section"), reply_markup=get_user_management_keyboard())

# FILE: modules/marzban/actions/display.py
# REPLACE THE ENTIRE _list_users_base FUNCTION WITH THIS OPTIMIZED VERSION

async def _list_users_base(update: Update, context: ContextTypes.DEFAULT_TYPE, list_type: str, page: int = 1):
    from shared.translator import translator
    import time

    is_callback = update.callback_query is not None
    message = update.callback_query.message if is_callback else await update.message.reply_text(translator.get("marzban.marzban_display.loading"))
    
    # Clear search results cache if we are not in a search context
    if list_type != 'search':
        context.user_data.pop('last_search_results', None)
    
    if is_callback:
        await update.callback_query.answer()
    else:
        await message.edit_text(translator.get("marzban.marzban_display.fetching_users"))
    
    target_users = []
    
    try:
        panel_id = context.user_data.get('selected_panel_id')
        if not panel_id:
            await message.edit_text(translator.get("marzban.marzban_display.no_panel_selected_error"))
            return

        # --- ✨ START OF CACHING LOGIC ---
        CACHE_EXPIRY_SECONDS = 60  # Cache lists for 60 seconds
        now = time.time()
        
        # Define cache keys based on list type and panel ID to avoid conflicts
        users_cache_key = f'cached_users_{panel_id}_{list_type}'
        cache_time_key = f'cache_time_{panel_id}_{list_type}'
        
        cached_users = context.user_data.get(users_cache_key)
        cache_time = context.user_data.get(cache_time_key, 0)

        # Check if cache is valid
        if cached_users is not None and (now - cache_time) < CACHE_EXPIRY_SECONDS:
            LOGGER.info(f"Using cached user list for panel {panel_id}, type '{list_type}'.")
            target_users = cached_users
        else:
            LOGGER.info(f"Cache expired or not found for panel {panel_id}, type '{list_type}'. Fetching from API.")
            
            # --- START: API Fetching Block (only runs when cache is invalid) ---
            if list_type == 'search':
                # Search results are handled differently and have their own cache
                target_users = context.user_data.get('last_search_results', [])
            else:
                panel = await crud_panel.get_panel_by_id(panel_id)
                if not panel:
                     await message.edit_text(translator.get("panel_manager.delete.not_found")); return
                
                api = await panel_utils._get_api_for_panel(panel)
                if not api:
                    await message.edit_text(translator.get("marzban.marzban_display.panel_connection_error")); return
                
                all_users = await api.get_all_users()
                if all_users is None:
                    await message.edit_text(translator.get("marzban.marzban_display.panel_connection_error")); return
                
                # Process and sort the fetched list
                if list_type == 'warning':
                    warning_users = []
                    warning_status = translator.get("marzban.marzban_display.status_warning")
                    inactive_status = translator.get("marzban.marzban_display.status_inactive")
                    for u in all_users:
                        prefix, _, is_online, _, _ = get_user_display_info(u)
                        if not is_online and prefix in [warning_status, inactive_status]:
                            warning_users.append(u)
                    target_users = sorted(warning_users, key=lambda u: u.get('username','').lower())
                else: # list_type == 'all'
                    target_users = sorted(all_users, key=lambda u: u.get('username','').lower())

                # Store the newly fetched and processed list in the cache
                context.user_data[users_cache_key] = target_users
                context.user_data[cache_time_key] = now
            # --- END: API Fetching Block ---
        # --- ✨ END OF CACHING LOGIC ---

        # Determine titles and not-found texts
        if list_type == 'search':
            title_text = translator.get("marzban.marzban_display.search_results_title")
            not_found_text = translator.get("marzban.marzban_display.no_search_results")
        else: # 'all' or 'warning'
            title_text = translator.get("marzban.marzban_display.warning_list_title") if list_type == 'warning' else translator.get("marzban.marzban_display.all_users_list_title")
            not_found_text = translator.get("marzban.marzban_display.no_warning_users") if list_type == 'warning' else translator.get("marzban.marzban_display.no_users_in_panel")

        if not target_users:
            await message.edit_text(not_found_text); return
            
        # --- Pagination and Display (No changes needed here) ---
        total_pages = math.ceil(len(target_users) / USERS_PER_PAGE)
        page = max(1, min(page, total_pages))
        start_index = (page - 1) * USERS_PER_PAGE
        page_users = target_users[start_index : start_index + USERS_PER_PAGE]
        
        keyboard = build_users_keyboard(page_users, page, total_pages, list_type)
        
        panel_name = context.user_data.get('selected_panel_name', '')
        title_with_panel = f"{title_text} ({panel_name})"

        safe_title = escape_markdown(translator.get("marzban.marzban_display.page_title", title=title_with_panel, page=page), version=2)
        await message.edit_text(safe_title, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        LOGGER.error(f"Error in _list_users_base: {e}", exc_info=True)
        await message.edit_text(translator.get("marzban.marzban_display.list_display_error"))

@admin_only
async def list_all_users_paginated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _list_users_base(update, context, list_type='all')

@admin_only
async def list_warning_users_paginated(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _list_users_base(update, context, list_type='warning')

async def update_user_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _list_users_base(update, context, list_type=update.callback_query.data.split('_')[-2], page=int(update.callback_query.data.split('_')[-1]))

async def show_user_details_panel(context: ContextTypes.DEFAULT_TYPE, chat_id: int, username: str, list_type: str, page_number: int, success_message: str = None, message_id: int = None) -> None:
    from shared.translator import translator
    
    panel_id = context.user_data.get('selected_panel_id')
    if not panel_id:
        await context.bot.send_message(chat_id=chat_id, text=translator.get("marzban.marzban_display.no_panel_selected_error"))
        return

    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await context.bot.send_message(chat_id=chat_id, text=translator.get("panel_manager.delete.not_found"))
        return

    api = await panel_utils._get_api_for_panel(panel)
    if not api:
        await context.bot.send_message(chat_id=chat_id, text=translator.get("marzban.marzban_display.panel_connection_error"))
        return

    user_info = await api.get_user_data(username)
    if not user_info:
        if message_id:
            try:
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=translator.get("marzban.marzban_display.user_not_found"))
            except Exception:
                await context.bot.send_message(chat_id=chat_id, text=translator.get("marzban.marzban_display.user_not_found"))
        return

    online_status = translator.get("marzban.marzban_display.offline")
    if user_info.get('online_at'):
        try:
            online_at_dt = datetime.datetime.strptime(user_info['online_at'], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            if (datetime.datetime.now(datetime.timezone.utc) - online_at_dt).total_seconds() < 180:
                online_status = translator.get("marzban.marzban_display.online")
        except (ValueError, TypeError):
            pass
        
    used_gb = (user_info.get('used_traffic') or 0) / GB_IN_BYTES
    limit_gb = (user_info.get('data_limit') or 0) / GB_IN_BYTES
    usage_str = f"{used_gb:.2f} GB / " + (f"{limit_gb:.0f} GB" if limit_gb > 0 else translator.get("marzban.marzban_display.unlimited"))
    
    expire_str = translator.get("marzban.marzban_display.unlimited")
    if user_info.get('expire'):
        expire_dt = datetime.datetime.fromtimestamp(user_info['expire'])
        if expire_dt > datetime.datetime.now():
            jalali_date = jdatetime.datetime.fromgregorian(datetime=expire_dt)
            days_left = (expire_dt - datetime.datetime.now()).days
            expire_str = f"{jalali_date.strftime('%Y/%m/%d')} (" + translator.get("marzban.marzban_display.days_remaining", days=days_left) + ")"
        else:
            expire_str = translator.get("marzban.marzban_display.expired")
            
    message_text = ""
    if success_message:
        message_text += f"{success_message}\n{'-'*20}\n"
    
    message_text += translator.get("marzban.marzban_display.user_details_title", username=username)
    message_text += f"{translator.get('marzban.marzban_display.user_status_label')} {online_status}\n"
    message_text += f"{translator.get('marzban.marzban_display.user_usage_label')} {usage_str}\n"
    message_text += f"{translator.get('marzban.marzban_display.user_expiry_label')} `{expire_str}`"
    
    back_button_callback = f"list_subs_page_{page_number}" if list_type == 'subs' else f"show_users_page_{list_type}_{page_number}"
    back_button_text = translator.get("marzban.marzban_display.back_to_subs_list") if list_type == 'subs' else translator.get("marzban.marzban_display.back_to_users_list")
    
    send_invoice_callback = StartManualInvoice(customer_id=0, username=username).to_string()

    # ✅ --- START OF FIX ---
    # The username is passed directly without any extra prefixes.
    keyboard_rows = [
        [InlineKeyboardButton(translator.get("marzban.marzban_display.button_smart_renew"), callback_data=f"renew_{username}"), InlineKeyboardButton(translator.get("marzban.marzban_display.button_send_invoice"), callback_data=send_invoice_callback)],
        [InlineKeyboardButton(translator.get("marzban.marzban_display.button_add_data"), callback_data=f"add_data_{username}"), InlineKeyboardButton(translator.get("marzban.marzban_display.button_add_days"), callback_data=f"add_days_{username}")],
        [InlineKeyboardButton(translator.get("marzban.marzban_display.button_reset_traffic"), callback_data=f"reset_traffic_{username}"), InlineKeyboardButton(translator.get("marzban.marzban_display.button_subscription_info"), callback_data=f"note_{username}")],
        [InlineKeyboardButton(translator.get("marzban.marzban_display.button_subscription_link"), callback_data=f"sub_link_{username}"), InlineKeyboardButton(translator.get("marzban.marzban_display.button_delete_user"), callback_data=f"delete_{username}")],
        [InlineKeyboardButton(back_button_text, callback_data=back_button_callback)]
    ]
    # ✅ --- END OF FIX ---
    
    reply_markup = InlineKeyboardMarkup(keyboard_rows)

    if message_id:
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    else:
        await context.bot.send_message(chat_id=chat_id, text=message_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)

async def show_user_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    query = update.callback_query
    await query.answer()
    try:
        # Callback format: user_details_{username}_{list_type}_{page_number}_{panel_id}
        parts = query.data.split('_')
        username = parts[2]
        list_type = parts[3]
        page_number = int(parts[4])
        # panel_id is optional, for global search results
        panel_id = int(parts[5]) if len(parts) > 5 else None

        if not username: raise ValueError("Extracted username is empty.")

        # ✨ NEW LOGIC: If panel_id comes from the callback, store it in context
        # This is crucial for global search to work correctly.
        if panel_id:
            context.user_data['selected_panel_id'] = panel_id
    except (ValueError, IndexError) as e:
        LOGGER.error(f"CRITICAL: Could not parse complex user_details callback_data '{query.data}': {e}")
        await query.edit_message_text(translator.get("marzban.marzban_display.list_display_error"))
        return
    context.user_data['current_list_type'] = list_type
    context.user_data['current_page'] = page_number
    loading_message = None
    loading_text = translator.get("marzban.marzban_display.getting_details_for", username=f"`{username}`")
    if query.message.photo:
        await query.message.delete()
        loading_message = await context.bot.send_message(chat_id=query.message.chat_id, text=loading_text, parse_mode=ParseMode.MARKDOWN)
    else:
        await query.edit_message_text(loading_text, parse_mode=ParseMode.MARKDOWN)
        loading_message = query.message
    await show_user_details_panel(
        context=context, chat_id=loading_message.chat_id, message_id=loading_message.message_id,
        username=username, list_type=list_type, page_number=page_number
    )
    


async def handle_deep_link_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    now = time.time()
    last_call = context.user_data.get('last_deeplink_call', 0)
    if now - last_call < 2: return
    context.user_data['last_deeplink_call'] = now
    if update.effective_user.id not in config.AUTHORIZED_USER_IDS:
        await show_main_menu_action(update, context); return
    try:
        if not context.args or not context.args[0].startswith('details_'):
            await show_main_menu_action(update, context); return
        username = context.args[0].split('_', 1)[1]
    except (IndexError, AttributeError):
        await update.message.reply_text(translator.get("marzban.marzban_display.invalid_link"))
        await show_main_menu_action(update, context)
        return
    loading_msg = await update.message.reply_text(translator.get("marzban.marzban_display.getting_details_for", username=f"`{username}`"), parse_mode=ParseMode.MARKDOWN)
    await show_user_details_panel(
        context=context, chat_id=loading_msg.chat_id, message_id=loading_msg.message_id,
        username=username, list_type='all', page_number=1
    )

def format_subscription_links(user_data: dict) -> str:
    from shared.translator import translator
    links_text = ""
    subscription_url = user_data.get('subscription_url')
    if subscription_url:
        links_text += f"▫️ **لینک کلی:**\n`{subscription_url}`\n\n"
    inbounds = user_data.get('inbounds', {})
    if inbounds:
        for protocol, link_list in inbounds.items():
            if link_list:
                links_text += f"▫️ **لینک‌های {protocol.upper()}:**\n"
                for i, link in enumerate(link_list, 1): links_text += f"`{link}`\n"
                links_text += "\n"
    if not links_text:
        return translator.get("marzban.marzban_display.sub_link_not_found")
    return links_text.strip()
    
async def send_subscription_qr_code_and_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import translator
    query = update.callback_query
    await query.answer()
    try:
        username = query.data.split('_')[2]
    except IndexError:
        await query.edit_message_text(translator.get("marzban.marzban_display.internal_error_username_not_found"))
        return

    # ✨ MODIFIED: Get user data ONLY from the selected panel
    panel_id = context.user_data.get('selected_panel_id')
    if not panel_id:
        await query.edit_message_text(translator.get("marzban.marzban_display.no_panel_selected_error"))
        return
        
    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await query.edit_message_text(translator.get("panel_manager.delete.not_found"))
        return

    api = await panel_utils._get_api_for_panel(panel)
    if not api:
        await query.edit_message_text(translator.get("marzban.marzban_display.panel_connection_error"))
        return

    user_data = await api.get_user_data(username)
    subscription_url = user_data.get('subscription_url')
    if not subscription_url:
        await query.edit_message_text(text=translator.get("marzban.marzban_display.link_not_found_for_user", username=f"`{username}`"), parse_mode=ParseMode.MARKDOWN)
        return
    qr_image = qrcode.make(subscription_url)
    bio = io.BytesIO()
    bio.name = 'qrcode.png'
    qr_image.save(bio, 'PNG')
    bio.seek(0)
    caption = translator.get("marzban.marzban_display.qr_caption", username=f"`{username}`", url=f"`{subscription_url}`")
    list_type = context.user_data.get('current_list_type', 'all')
    page_number = context.user_data.get('current_page', 1)
    back_button_callback = f"user_details_{username}_{list_type}_{page_number}"
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(translator.get("marzban.marzban_display.back_to_user_details"), callback_data=back_button_callback)
    ]])
    await query.message.delete()
    await context.bot.send_photo(
        chat_id=query.message.chat_id, photo=bio, caption=caption,
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )
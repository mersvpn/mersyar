# FILE: modules/marzban/actions/add_user.py (FINAL, COMPLETE, AND REWRITTEN FOR MULTI-PANEL)

import datetime
import qrcode
import io
import logging
import copy
import secrets
import string
import re
import random
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

# ✨ NEW IMPORTS
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
from modules.marzban.actions import helpers as marzban_helpers
# ---
from database.models.panel_credential import PanelType
from shared.log_channel import send_log
from shared.callback_types import StartManualInvoice
from .constants import GB_IN_BYTES
from database.crud import bot_setting as crud_bot_setting
from database.crud import user as crud_user
from database.crud import template_config as crud_template
from database.crud import bot_managed_user as crud_bot_managed_user
from database.crud import user_note as crud_user_note
from database.crud import marzban_link as crud_marzban_link
from shared.keyboards import get_user_management_keyboard, get_customer_main_menu_keyboard

# --- ✨ NEW IMPORT FOR SMART RETURN ---
from shared.keyboards import get_back_to_main_menu_keyboard # برای منوی پشتیبان
from config import config
# -----------------------------------

from .data_manager import normalize_username
from shared.translator import _

LOGGER = logging.getLogger(__name__)

# Conversation states for admin adding a user
SELECT_PANEL, GET_USERNAME, GET_DATALIMIT, GET_EXPIRE, CONFIRM_CREATION = range(5)


def generate_random_username(length=8):
    alphabet = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))

async def _get_api_for_panel(panel_id: int) -> Optional[PanelAPI]:
    """Factory function to create an API object for a given panel ID."""
    try:
        panel = await crud_panel.get_panel_by_id(int(panel_id)) # Ensure int
        if not panel: 
            LOGGER.error(f"Panel with ID {panel_id} not found in DB.")
            return None
            
        # Check panel type case-insensitively
        p_type = str(panel.panel_type.value).lower().strip()
        
        if p_type == "marzban":
            credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
            return MarzbanPanel(credentials)
            
        LOGGER.warning(f"Unsupported panel type: {p_type} for panel {panel_id}")
        return None
    except Exception as e:
        LOGGER.error(f"Error creating API for panel {panel_id}: {e}")
        return None

async def add_user_to_panel_from_template(
    api: PanelAPI, panel_id: int, data_limit_gb: int, expire_days: int, username: Optional[str] = None, max_ips: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    template_config_obj = await crud_template.load_template_config(panel_id)
    if not template_config_obj or not template_config_obj.template_username:
        LOGGER.error("[Core Create User] Template user is not configured in the database.")
        return None

    base_username = username or generate_random_username()
    base_username = normalize_username(base_username)

    data_limit = int(data_limit_gb * GB_IN_BYTES) if data_limit_gb > 0 else 0
    expire_timestamp = (datetime.datetime.now() + datetime.timedelta(days=expire_days)).timestamp() if expire_days > 0 else 0
    expire = int(expire_timestamp)
    
    proxies_from_template = copy.deepcopy(template_config_obj.proxies or {})
    for proto in ['vless', 'vmess']:
        if proto in proxies_from_template and 'id' in proxies_from_template[proto]:
            del proxies_from_template[proto]['id']
    
    payload = { "inbounds": template_config_obj.inbounds or {}, "expire": expire, "data_limit": data_limit, "proxies": proxies_from_template, "status": "active" }
    if max_ips is not None and max_ips > 0:
        payload["on_hold_max_ips"] = max_ips

    current_username = base_username
    for attempt in range(4):
        payload["username"] = current_username
        success, result = await api.create_user(payload)
        
        if success:
            LOGGER.info(f"[Core Create User] Successfully created user '{current_username}' via API.")
            return result
        
        if isinstance(result, str) and "already exists" in result:
            current_username = f"{base_username}_{secrets.choice(string.digits)}{secrets.choice(string.digits)}"
            continue
        else:
            LOGGER.error(f"[Core Create User] Failed to create user '{current_username}'. API response: {result}")
            return None
    return None

async def _build_panel_selection_keyboard() -> Optional[InlineKeyboardMarkup]:
    from shared.translator import translator
    panels = await crud_panel.get_all_panels()
    if not panels: return None
    keyboard = [[InlineKeyboardButton(p.name, callback_data=f"add_user_panel_{p.id}")] for p in panels]
    keyboard.append([InlineKeyboardButton(translator.get("buttons.cancel"), callback_data="cancel_add_user")])
    return InlineKeyboardMarkup(keyboard)

async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    
    panel_id = context.user_data.get('selected_panel_id')
    
    if not panel_id:
        panels = await crud_panel.get_all_panels()
        
        if not panels:
            await update.message.reply_text(
                translator.get("panel_manager.add.no_panels_configured"),
                reply_markup=ReplyKeyboardRemove() 
            )
            return ConversationHandler.END
        
        if len(panels) == 1:
            panel_id = panels[0].id
            context.user_data['selected_panel_id'] = panel_id
            
        else:
            keyboard = await _build_panel_selection_keyboard()
            await update.message.reply_text(
                "🌐 لطفاً پنل (سرور) مورد نظر برای ساخت کاربر را انتخاب کنید:",
                reply_markup=keyboard
            )
            # هدایت به مرحله انتخاب پنل
            return SELECT_PANEL
    # -----------------------------------------------------------------------

    context.user_data['panel_id'] = panel_id
    context.user_data['new_user'] = {}

    template_config = await crud_template.load_template_config(panel_id)
    if not template_config or not template_config.template_username:
        await update.message.reply_text(
            translator.get("marzban.marzban_add_user.template_not_set"),
            reply_markup=get_user_management_keyboard()
        )
        return ConversationHandler.END
        
    prompt_text = translator.get("marzban.marzban_add_user.step1_ask_username")
    await update.message.reply_text(prompt_text, reply_markup=ReplyKeyboardRemove())
    
    return GET_USERNAME


async def add_user_for_customer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    query = update.callback_query
    await query.answer()
    customer_user_id = int(query.data.split('_')[-1])
    context.user_data['customer_user_id'] = customer_user_id
    
    keyboard = await _build_panel_selection_keyboard()
    if not keyboard:
        await query.message.reply_text(translator.get("panel_manager.add.no_panels_configured"))
        return ConversationHandler.END
        
    await query.edit_message_text(
        translator.get("panel_manager.add.select_panel_for_customer", customer_id=f"`{customer_user_id}`"),
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )
    return SELECT_PANEL

async def select_panel_for_creation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    query = update.callback_query
    await query.answer()
    
    panel_id = int(query.data.split('_')[-1])
    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await query.edit_message_text(translator.get("panel_manager.add.panel_not_found"))
        return ConversationHandler.END

    context.user_data['panel_id'] = panel.id
    context.user_data['new_user'] = {}
    
    prompt_text = translator.get("marzban.marzban_add_user.step1_ask_username_for_customer") if 'customer_user_id' in context.user_data else translator.get("marzban.marzban_add_user.step1_ask_username")
        
    await query.edit_message_text(prompt_text)
    
    return GET_USERNAME

async def add_user_get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username = normalize_username(update.message.text)
    panel_id = int(context.user_data.get('panel_id', 0))
    
    api = await _get_api_for_panel(panel_id)
    if not api:
        await update.message.reply_text(_("panel_manager.add.panel_not_found"))
        return ConversationHandler.END

    try:
        existing_user = await api.get_user_data(username)
        if existing_user:
            await update.message.reply_text(_("marzban.marzban_add_user.username_exists", username=username))
            return GET_USERNAME
    except Exception as e:
        LOGGER.error(f"Failed to check existing user: {e}")
        await update.message.reply_text(f"Error checking user: {e}")
        return ConversationHandler.END
    
    context.user_data['new_user']['username'] = username
    await update.message.reply_text(_("marzban.marzban_add_user.step2_ask_datalimit"))
    return GET_DATALIMIT

async def add_user_get_datalimit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        data_gb = int(update.message.text)
        if data_gb < 0: raise ValueError
        context.user_data['new_user']['data_limit_gb'] = data_gb
        await update.message.reply_text(_("marzban.marzban_add_user.step3_ask_expire"))
        return GET_EXPIRE
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban.marzban_add_user.invalid_number"))
        return GET_DATALIMIT

async def add_user_get_expire(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        expire_days = int(update.message.text)
        if expire_days < 0: raise ValueError
        context.user_data['new_user']['expire_days'] = expire_days
        user_info = context.user_data['new_user']
        
        summary = _("marzban.marzban_add_user.confirm_prompt_title") + "\n"
        summary += _("marzban.marzban_add_user.confirm_username", username=f"`{user_info['username']}`") + "\n"
        summary += _("marzban.marzban_add_user.confirm_datalimit", datalimit=f"`{user_info['data_limit_gb'] or 'نامحدود'}`") + "\n"
        summary += _("marzban.marzban_add_user.confirm_expire", duration=f"`{expire_days or 'نامحدود'}`")

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(_("marzban.marzban_add_user.button_confirm_create"), callback_data="confirm_add_user")],
            [InlineKeyboardButton(_("marzban.marzban_add_user.button_cancel"), callback_data="cancel_add_user")]
        ])
        await update.message.reply_text(summary, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        return CONFIRM_CREATION
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban.marzban_add_user.invalid_number"))
        return GET_EXPIRE

# --- ✨ SMART FIX: INTELLIGENT CREATE FUNCTION ---

async def add_user_create(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(translator.get("marzban.marzban_add_user.creating_user"))

    user_info = context.user_data.get('new_user', {})
    panel_id = context.user_data.get('panel_id')
    admin_user = update.effective_user
    
    if not all([user_info, panel_id]):
        await query.edit_message_text(translator.get("errors.conversation_data_lost"))
        return ConversationHandler.END

    api = await _get_api_for_panel(panel_id)
    if not api:
        await query.edit_message_text(translator.get("panel_manager.add.panel_not_found"))
        return ConversationHandler.END

    new_user_data = await add_user_to_panel_from_template(
        api=api, panel_id=panel_id, data_limit_gb=user_info['data_limit_gb'], 
        expire_days=user_info['expire_days'], username=user_info['username']
    )
    
    if new_user_data:
        marzban_username = new_user_data['username']
        await crud_bot_managed_user.add_to_managed_list(
            marzban_username=marzban_username,
            created_by_admin_id=admin_user.id
        )

        customer_id = context.user_data.get('customer_user_id') 

        if customer_id:
            await crud_marzban_link.create_or_update_link(marzban_username, customer_id, panel_id)
        
        await crud_user_note.create_or_update_user_note(
            marzban_username=marzban_username, duration=user_info['expire_days'],
            data_limit_gb=user_info['data_limit_gb'], price=0
        )
        
        log_message = translator.get("marzban.marzban_add_user.log_new_user_created", username=marzban_username, datalimit=user_info['data_limit_gb'], duration=user_info['expire_days'], admin_mention=admin_user.full_name)
        await send_log(context.bot, log_message)

        # ✨ SMART FIX 1: ONLY send message to customer if customer_id exists AND is valid
        if customer_id and customer_id != 0:
            customer_message = await marzban_helpers.format_user_info_for_customer(api, marzban_username)
            subscription_url = new_user_data.get('subscription_url', '')

            qr_image = qrcode.make(subscription_url)
            bio = io.BytesIO(); bio.name = 'qrcode.png'; qr_image.save(bio, 'PNG'); bio.seek(0)
            try:
                await context.bot.send_photo(chat_id=customer_id, photo=bio, caption=customer_message, parse_mode=ParseMode.MARKDOWN)
                
                # Only show invoice option to Super Admin
                if admin_user.id in config.AUTHORIZED_USER_IDS:
                    callback_obj = StartManualInvoice(customer_id=customer_id, username=marzban_username)
                    admin_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(translator.get("marzban.marzban_add_user.button_send_invoice"), callback_data=callback_obj.to_string())]])
                    await context.bot.send_message(chat_id=admin_user.id, text=translator.get("marzban.marzban_add_user.config_sent_to_customer", customer_id=customer_id), reply_markup=admin_keyboard)
                else:
                    # For Support admin, just confirm sending
                    await context.bot.send_message(chat_id=admin_user.id, text="✅ کانفیگ برای مشتری ارسال شد.")

            except Exception as e:
                LOGGER.warning(f"Failed to send message to customer {customer_id}: {e}")
                # Don't spam error to support admin if it's just a blocked user
                if admin_user.id in config.AUTHORIZED_USER_IDS:
                    await context.bot.send_message(chat_id=admin_user.id, text=translator.get("marzban.marzban_add_user.error_sending_to_customer", url=subscription_url))
        
        # --- END OF FIX 1 ---

        if admin_user.id in config.AUTHORIZED_USER_IDS:
            list_type = 'all'      
        else:
            list_type = 'myusers'

        final_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                translator.get("keyboards.buttons.view_user_details"),
                callback_data=f"user_details_{marzban_username}_{list_type}_1_{panel_id}" 
            )
        ]])
        # ------------------------------
        
        await query.edit_message_text(
            translator.get("marzban.marzban_add_user.user_created_successfully", username=f"`{marzban_username}`"),
            reply_markup=final_keyboard, 
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.edit_message_text(translator.get("marzban.marzban_add_user.error_creating_user"))
    
    context.user_data.clear()
    
    # ✨ SMART FIX 2: Return to correct menu based on user role
    is_super_admin = admin_user.id in config.AUTHORIZED_USER_IDS
    
    if is_super_admin:
        # Super Admin -> User Management Menu
        await update.effective_message.reply_text(
            translator.get("marzban.shared.menu_returned"), 
            reply_markup=get_user_management_keyboard()
        )
    else:
        # Support Admin -> Back to Support Panel (Simulated by sending main menu logic)
        # Since support panel is part of main menu structure for them
        from modules.support_panel.actions import show_support_menu
        await show_support_menu(update, context)
        
    # --- END OF FIX 2 ---

    return ConversationHandler.END

async def cancel_add_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    query = update.callback_query
    user = update.effective_user
    
    if query:
        await query.answer()
        try:
            await query.edit_message_text(_("general.operation_cancelled"))
        except Exception as e:
            logging.warning(f"Could not edit message on cancel: {e}")
    
    # ✨ SMART FIX 3: Return to correct menu on cancel too
    is_super_admin = user.id in config.AUTHORIZED_USER_IDS
    
    if is_super_admin:
        await update.effective_chat.send_message(
            _("shared.menu_returned"), 
            reply_markup=get_user_management_keyboard()
        )
    else:
        from modules.support_panel.actions import show_support_menu
        await show_support_menu(update, context)
        
    return ConversationHandler.END
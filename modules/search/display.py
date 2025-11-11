# FILE: modules/user_info/actions/display.py

import asyncio
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from datetime import datetime
from database.crud import user as crud_user
from database.crud import marzban_link as crud_marzban_link
from shared.keyboards import get_admin_main_menu_keyboard
from shared.callback_types import UserInfoCallback
from shared.translator import _
from shared import panel_utils
from telegram.helpers import escape_markdown

LOGGER = logging.getLogger(__name__)

AWAIT_USER_ID, MAIN_MENU, EDIT_NOTE = range(3)

async def start_customer_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        _("user_info.prompts.enter_user_id"),
        reply_markup=ReplyKeyboardMarkup(
            [[KeyboardButton(_("user_info.menu.back_to_main"))]],
            resize_keyboard=True
        )
    )
    return AWAIT_USER_ID

async def process_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes a user ID, either from a message or from context.user_data,
    and displays the main management menu for that user.
    """
    target_user_id = context.user_data.get('target_user_id')
    
    # If the ID was not passed via context (e.g., from search), get it from the user's message.
    if not target_user_id:
        user_input = update.message.text.strip()
        if not user_input.isdigit():
            await update.message.reply_text(_("user_info.prompts.invalid_user_id"))
            return AWAIT_USER_ID
        target_user_id = int(user_input)
    
    user_data = await crud_user.get_user_with_relations(target_user_id)
    
    if not user_data:
        message_text = _("user_info.prompts.user_not_found", user_id=target_user_id)
        # If the call came from the search module, we don't need the big keyboard.
        if 'target_user_id' in context.user_data:
            await context.bot.send_message(update.effective_chat.id, message_text, parse_mode=ParseMode.MARKDOWN)
            # We need to explicitly re-enter the search prompt.
            # A better approach is to let search handle this, which it now does.
            # This return is for the user_info conversation context.
            return AWAIT_USER_ID
        else:
            await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)
        return AWAIT_USER_ID
    
    # At this point, we have a valid target_user_id, so save it to context
    context.user_data['target_user_id'] = target_user_id
    
    user_name = user_data.first_name or "N/A"
    user_username = f"@{user_data.username}" if user_data.username else _("user_info.profile.no_username")
    
    menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton(_("user_info.menu.user_profile"))],
        [KeyboardButton(_("user_info.menu.services")), KeyboardButton(_("user_info.menu.note_management"))],
        [KeyboardButton(_("user_info.menu.back_to_main"))]
    ],
    resize_keyboard=True
)
    
    # Send a new message to ensure the correct keyboard is displayed
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_("user_info.prompts.user_header", name=user_name, username=user_username, user_id=target_user_id),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_keyboard
    )
    
    return MAIN_MENU

async def show_comprehensive_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await update.message.reply_text(_("user_info.prompts.error_no_user_id"))
        return ConversationHandler.END
    
    user_data = await crud_user.get_user_with_relations(target_user_id)
    if not user_data:
        await update.message.reply_text(_("user_info.prompts.user_not_found", user_id=target_user_id))
        return ConversationHandler.END
    
    # --- 1. Gather Data ---
    user_name = user_data.first_name or "N/A"
    user_username = f"@{user_data.username}" if user_data.username else _("user_info.profile.no_username")
    join_date = user_data.join_date.strftime("%Y/%m/%d - %H:%M") if user_data.join_date else "N/A"
    last_activity = _("user_info.profile.never_active")
    if user_data.last_activity:
        # ... (Your logic for last_activity)
        pass
    wallet_balance = int(user_data.wallet_balance) if user_data.wallet_balance else 0
    pending_count = len(user_data.pending_invoices) if user_data.pending_invoices else 0

    # --- 2. Build the message using Unicode characters and correct translator calls ---
    message_parts = [
        f"┌─ {_('user_info.profile.title')}",
        "│",
        _('user_info.profile.section_header'),
        _('user_info.profile.user_id', user_id=target_user_id),
        _('user_info.profile.name', name=user_name),
        _('user_info.profile.username', username=user_username),
        _('user_info.profile.join_date', date=join_date),
        _('user_info.profile.last_activity', activity=last_activity),
        "│",
        # --- FIX: Correctly call the translator function ---
        f"├─ {_('user_info.financial.title')}",
        "│",
        _('user_info.financial.section_wallet'),
        _('user_info.financial.balance', balance=f"{wallet_balance:,}"),
        "│",
        _('user_info.financial.section_invoices'),
        _('user_info.financial.pending_invoices', count=pending_count),
        "└" + "─" * 25
    ]
    message_text = "\n".join(message_parts)
    
    inline_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_("user_info.buttons.refresh"), callback_data=UserInfoCallback("refresh", target_user_id, "profile").to_string()),
            InlineKeyboardButton(_("user_info.buttons.close"), callback_data=UserInfoCallback("close").to_string())
        ]
    ])
    
    # --- 3. Send or Edit WITHOUT any ParseMode ---
    # Plain text does not need a parse mode.
    target_message = update.effective_message
    if update.callback_query:
        await target_message.edit_text(message_text, reply_markup=inline_keyboard)
    else:
        await target_message.reply_text(message_text, reply_markup=inline_keyboard)
    
    return MAIN_MENU


async def show_services(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await update.message.reply_text(_("user_info.prompts.error_no_user_id"))
        return ConversationHandler.END
    
    links = await crud_marzban_link.get_links_by_telegram_id(target_user_id)
    
    message_parts = [f"┌─ {_('user_info.services.title')}"]
    
    if not links:
        message_parts.append(f"│   {_('user_info.services.no_services')}")
    else:
        active_services_text = []
        expired_services_text = []
        
        tasks = [panel_utils.get_user_from_any_panel(link.marzban_username) for link in links]
        user_details_list = await asyncio.gather(*tasks)

        for user_detail in user_details_list:
            if not user_detail: continue
            username = user_detail.get("username", "N/A")

            if user_detail.get("status") == "active":
                data_limit = user_detail.get("data_limit", 0)
                used_traffic = user_detail.get("used_traffic", 0)
                data_info = ""
                time_info = ""

                if data_limit > 0:
                    data_limit_gb = data_limit / (1024**3); used_traffic_gb = used_traffic / (1024**3)
                    data_info = f"{used_traffic_gb:.1f} GB / {data_limit_gb:.1f} GB"
                else:
                    data_info = _("user_info.services.unlimited_data")
                
                expire_timestamp = user_detail.get("expire")
                if expire_timestamp:
                    expire_date = datetime.fromtimestamp(expire_timestamp)
                    days_left = (expire_date - datetime.now()).days
                    time_info = _("user_info.services.days_left", days=days_left) if days_left >= 0 else _("user_info.services.expired")
                else:
                    time_info = _("user_info.services.unlimited_time")
                
                active_services_text.append(_("user_info.services.active_service", username=username, data=data_info, time=time_info))
            else:
                expired_services_text.append(_("user_info.services.expired_service", username=username))
        
        if active_services_text:
            message_parts.append("│")
            message_parts.append(_('user_info.services.section_active', count=len(active_services_text)))
            message_parts.extend(active_services_text)
        
        if expired_services_text:
            message_parts.append("│")
            message_parts.append(_('user_info.services.section_expired', count=len(expired_services_text)))
            message_parts.extend(expired_services_text)

    message_parts.append("└" + "─" * 25)
    message_text = "\n".join(message_parts)
    
    inline_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_("user_info.buttons.refresh"), callback_data=UserInfoCallback("refresh", target_user_id, "services").to_string()),
            InlineKeyboardButton(_("user_info.buttons.close"), callback_data=UserInfoCallback("close").to_string())
        ]
    ])
    
    target_message = update.effective_message
    if update.callback_query:
        await target_message.edit_text(message_text, reply_markup=inline_keyboard)
    else:
        await target_message.reply_text(message_text, reply_markup=inline_keyboard)
    
    return MAIN_MENU
async def show_note_manager(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    target_user_id = context.user_data.get('target_user_id')
    if not target_user_id:
        await update.message.reply_text(_("user_info.prompts.error_no_user_id"))
        return ConversationHandler.END
    
    user_data = await crud_user.get_user_by_id(target_user_id)
    if not user_data:
        await update.message.reply_text(_("user_info.prompts.user_not_found", user_id=target_user_id))
        return ConversationHandler.END
    
    current_note = user_data.admin_note if user_data.admin_note else _("user_info.note.no_note")
    
    message_parts = [
        f"┌─ {_('user_info.note.title')}",
        "│",
        _('user_info.note.section_current'),
        f"│   {current_note}",
        "└" + "─" * 25,
    ]
    message_text = "\n".join(message_parts)
    
    buttons = [[InlineKeyboardButton(_("user_info.buttons.edit_note"), callback_data=UserInfoCallback("edit_note", target_user_id).to_string())]]
    if user_data.admin_note:
        buttons.append([InlineKeyboardButton(_("user_info.buttons.delete_note"), callback_data=UserInfoCallback("delete_note", target_user_id).to_string())])
    buttons.append([InlineKeyboardButton(_("user_info.buttons.close"), callback_data=UserInfoCallback("close").to_string())])
    
    inline_keyboard = InlineKeyboardMarkup(buttons)
    
    target_message = update.effective_message
    if update.callback_query:
        await target_message.edit_text(message_text, reply_markup=inline_keyboard)
    else:
        await target_message.reply_text(message_text, reply_markup=inline_keyboard)
    
    return MAIN_MENU

async def prompt_for_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    callback_data = UserInfoCallback.from_str(query.data)
    if not callback_data:
        return MAIN_MENU
    
    if callback_data.action == "delete_note":
        success = await crud_user.update_user_note(callback_data.user_id, None)
        if success:
            await query.edit_message_text(_("user_info.note.note_deleted"))
        else:
            await query.edit_message_text(_("user_info.note.delete_error"))
        return MAIN_MENU
    
    await query.message.reply_text(_("user_info.prompts.note_prompt"))
    
    context.user_data['editing_note_for'] = callback_data.user_id
    return EDIT_NOTE

async def save_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note_text = update.message.text.strip()
    target_user_id = context.user_data.get('editing_note_for')
    
    if not target_user_id:
        await update.message.reply_text(_("user_info.prompts.error_no_user_id"))
        return ConversationHandler.END
    
    success = await crud_user.update_user_note(target_user_id, note_text)
    
    if success:
        await update.message.reply_text(_("user_info.note.note_saved"))
    else:
        await update.message.reply_text(_("user_info.note.note_error"))
    
    del context.user_data['editing_note_for']
    return MAIN_MENU

async def refresh_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer(_("user_info.messages.refreshing"))
    
    callback_data = UserInfoCallback.from_str(query.data)
    if not callback_data or not callback_data.user_id:
        return MAIN_MENU
    
    target_user_id = callback_data.user_id
    context.user_data['target_user_id'] = target_user_id
    
    # We don't need to delete the message, edit_message_text will replace it.
    
    # Create a mock update object to pass to the show functions
    temp_update = Update(update.update_id, callback_query=query) # Pass the query object
    
    # --- KEY CHANGE: Route all relevant refreshes to the new comprehensive view ---
    if callback_data.param in ["profile", "financial"]:
        # Both "profile" and "financial" refresh actions now call the single merged function
        return await show_comprehensive_info(temp_update, context)
    elif callback_data.param == "services":
        return await show_services(temp_update, context)
    
    # Fallback in case of an unknown param, although it shouldn't happen
    return MAIN_MENU

async def close_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.delete()
        await update.callback_query.message.reply_text(
            _("user_info.messages.back_to_main"),
            reply_markup=get_admin_main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            _("user_info.messages.back_to_main"),
            reply_markup=get_admin_main_menu_keyboard()
        )
    
    if 'target_user_id' in context.user_data:
        del context.user_data['target_user_id']
    if 'editing_note_for' in context.user_data:
        del context.user_data['editing_note_for']
    
    return ConversationHandler.END

# --- ADD THIS NEW FUNCTION to the end of modules/user_info/actions/display.py ---

async def display_user_info_action(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int):
    """
    A wrapper action to display user info, callable from other modules.
    It simulates the user entering an ID.
    """
    user_data = await crud_user.get_user_with_relations(telegram_id)
    
    if not user_data:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=_("user_info.prompts.user_not_found", user_id=telegram_id),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    context.user_data['target_user_id'] = telegram_id
    
    user_name = user_data.first_name or "N/A"
    user_username = f"@{user_data.username}" if user_data.username else _("user_info.profile.no_username")
    
    menu_keyboard = ReplyKeyboardMarkup(
    [
        [KeyboardButton(_("user_info.menu.user_profile"))],
        [KeyboardButton(_("user_info.menu.services")), KeyboardButton(_("user_info.menu.note_management"))],
        [KeyboardButton(_("user_info.menu.back_to_main"))]
    ],
    resize_keyboard=True
)
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_("user_info.prompts.user_header", name=user_name, username=user_username, user_id=telegram_id),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=menu_keyboard
    )

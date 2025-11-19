# --- START OF FILE modules/bot_settings/actions.py ---
import logging
from telegram import Update, error
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from shared.keyboards import (
    get_settings_and_tools_keyboard, get_helper_tools_keyboard,
    get_test_account_settings_keyboard, get_cancel_keyboard
)
from .data_manager import is_bot_active, set_bot_status
from database.crud import bot_setting as crud_bot_setting
from shared.translator import _
from shared.keyboards import get_settings_and_tools_keyboard
from shared.translator import _

LOGGER = logging.getLogger(__name__)

MENU_STATE = 0
SET_CHANNEL_ID = 1
GET_FORCED_JOIN_CHANNEL = 2

ADMIN_TEST_ACCOUNT_MENU = 10
GET_HOURS = 11
GET_GB = 12
GET_LIMIT = 13


async def show_helper_tools_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    target = update.effective_message
    if not target:
        return
    await target.reply_text(_("bot_settings.helper_tools_menu_title"), reply_markup=get_helper_tools_keyboard())


async def back_to_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    chat_id = update.effective_chat.id
    query = update.callback_query

    if query:
        await query.answer()
        try:
            await query.edit_message_text(
                text=_("bot_settings.back_to_settings_menu"),
                reply_markup=None
            )
        except error.BadRequest as e:
            if "Message is not modified" not in str(e):
                LOGGER.error(f"Error editing message on back action: {e}")
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=_("bot_settings.back_to_settings_menu"),
            reply_markup=get_settings_and_tools_keyboard()
        )

    return ConversationHandler.END


async def _build_and_send_main_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    bot_settings = await crud_bot_setting.load_bot_settings()
    is_active_status = await is_bot_active()
    
    maintenance_btn_text = _("bot_settings.status_on") if is_active_status else _("bot_settings.status_off_maintenance")
    maintenance_callback = "toggle_maintenance_disable" if is_active_status else "toggle_maintenance_enable"

    log_channel_is_enabled = bot_settings.get('is_log_channel_enabled', False)
    log_channel_btn_text = _("bot_settings.status_active") if log_channel_is_enabled else _("bot_settings.status_inactive")
    log_channel_callback = "toggle_log_channel_disable" if log_channel_is_enabled else "toggle_log_channel_enable"


    is_forced_join_enabled = bot_settings.get('is_forced_join_active', False)
    forced_join_btn_text = _("bot_settings.status_active") if is_forced_join_enabled else _("bot_settings.status_inactive")
    forced_join_callback = "toggle_forced_join_disable" if is_forced_join_enabled else "toggle_forced_join_enable"
    auto_confirm_is_enabled = bot_settings.get('auto_confirm_invoices', False)
    auto_confirm_btn_text = _("bot_settings.status_active") if auto_confirm_is_enabled else _("bot_settings.status_inactive")
    auto_confirm_callback = "toggle_auto_confirm_disable" if auto_confirm_is_enabled else "toggle_auto_confirm_enable"
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [
        [InlineKeyboardButton(maintenance_btn_text, callback_data=maintenance_callback), InlineKeyboardButton(_("bot_settings.label_bot_status"), callback_data="noop")],
        [InlineKeyboardButton(log_channel_btn_text, callback_data=log_channel_callback), InlineKeyboardButton(_("bot_settings.label_log_channel"), callback_data="noop")],
        [InlineKeyboardButton(forced_join_btn_text, callback_data=forced_join_callback), InlineKeyboardButton(_("bot_settings.label_forced_join"), callback_data="noop")],
        [InlineKeyboardButton(auto_confirm_btn_text, callback_data=auto_confirm_callback), InlineKeyboardButton(_("bot_settings.label_auto_confirm"), callback_data="noop")],
        [InlineKeyboardButton(_("bot_settings.button_back_to_tools"), callback_data="bot_status_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    menu_text = _("bot_settings.menu_title")

    target_message = query.message if query else update.message
    if query:
        await query.answer()
        try:
            await query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        except error.BadRequest as e:
            if "Message is not modified" not in str(e): LOGGER.error(f"Error editing bot settings menu: {e}")
    else:
        if update.message: await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=menu_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def start_bot_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE


async def toggle_maintenance_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    new_status_is_active = (query.data == "toggle_maintenance_enable")
    await set_bot_status(new_status_is_active)
    feedback = _("bot_settings.feedback_bot_enabled") if new_status_is_active else _("bot_settings.feedback_bot_disabled")
    await query.answer(feedback, show_alert=True)
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE


async def toggle_log_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # ✨ FIX: Determine new status directly from callback data for reliability
    new_status = (query.data == "toggle_log_channel_enable")

    await crud_bot_setting.save_bot_settings({"is_log_channel_enabled": new_status})
    feedback = _("bot_settings.feedback_log_channel_enabled") if new_status else _("bot_settings.feedback_log_channel_disabled")
    await query.answer(feedback, show_alert=True)
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE


async def toggle_wallet_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    new_status = (query.data == "toggle_wallet_enable")
    await crud_bot_setting.save_bot_settings({"is_wallet_enabled": new_status})
    feedback = _("bot_settings.feedback_wallet_enabled") if new_status else _("bot_settings.feedback_wallet_disabled")
    await query.answer(feedback, show_alert=True)
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE


async def toggle_forced_join_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    # ✨ FIX: Determine new status directly from callback data for reliability
    new_status = (query.data == "toggle_forced_join_enable")

    await crud_bot_setting.save_bot_settings({"is_forced_join_active": new_status})
    feedback = _("bot_settings.feedback_forced_join_enabled") if new_status else _("bot_settings.feedback_forced_join_disabled")
    await query.answer(feedback, show_alert=True)
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE


async def prompt_for_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_settings = await crud_bot_setting.load_bot_settings()
    current_channel_id = bot_settings.get('log_channel_id', _("marzban_credentials.not_set"))
    text = _("bot_settings.current_log_channel_id", id=f"`{current_channel_id}`") + _("bot_settings.prompt_for_channel_id")
    
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_cancel_keyboard()
    )
    return SET_CHANNEL_ID


async def process_channel_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    channel_id = update.message.text.strip()
    if not (channel_id.startswith('@') or channel_id.startswith('-100')):
        await update.message.reply_text(
            _("bot_settings.invalid_channel_id"), 
            reply_markup=get_cancel_keyboard()
        )
        return SET_CHANNEL_ID

    await crud_bot_setting.save_bot_settings({'log_channel_id': channel_id})
    await update.message.reply_text(
        _("bot_settings.channel_id_updated", id=f"`{channel_id}`"), 
        parse_mode=ParseMode.MARKDOWN, 
        reply_markup=get_settings_and_tools_keyboard()
    )
    return ConversationHandler.END


async def prompt_for_forced_join_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    bot_settings = await crud_bot_setting.load_bot_settings()
    current_channel = bot_settings.get("forced_join_channel")
    
    if current_channel:
        message_text = _("bot_settings.forced_join.prompt_with_current", channel=f"@{current_channel}")
    else:
        message_text = _("bot_settings.forced_join.prompt_no_current")
        
    await update.message.reply_text(
        message_text,
        reply_markup=get_cancel_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return GET_FORCED_JOIN_CHANNEL


async def process_forced_join_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    channel_username = update.message.text.strip()
    
    if channel_username.startswith('@'):
        channel_username = channel_username[1:]

    if not channel_username or not channel_username.replace("_", "").isalnum():
        await update.message.reply_text(
            _("bot_settings.forced_join.invalid_username"),
            reply_markup=get_cancel_keyboard()
        )
        return GET_FORCED_JOIN_CHANNEL
        
    await crud_bot_setting.save_bot_settings({"forced_join_channel": channel_username})
    
    await update.message.reply_text(
        _("bot_settings.forced_join.success", channel=f"@{channel_username}"),
        reply_markup=get_helper_tools_keyboard(),
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END


async def _get_test_account_menu_text() -> str:
    settings = await crud_bot_setting.load_bot_settings()
    status = _("bot_settings.status_active") if settings.get('is_test_account_enabled', False) else _("bot_settings.status_inactive")
    limit = settings.get('test_account_limit', _("marzban_credentials.not_set"))
    hours = settings.get('test_account_hours', _("marzban_credentials.not_set"))
    gb = settings.get('test_account_gb', _("marzban_credentials.not_set"))
    
    return _(
        "bot_settings.test_account_v2.menu_title",
        status=status, limit=limit, hours=hours, gb=gb
    )


async def start_test_account_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, should_delete_trigger_message: bool = True) -> int:
    text = await _get_test_account_menu_text()
    keyboard = await get_test_account_settings_keyboard()
    
    if should_delete_trigger_message and update.message:
        try:
            await update.message.delete()
        except error.BadRequest:
            LOGGER.warning("Trigger message for test account settings not found for deletion (might be a refresh).")
        
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=text, 
        reply_markup=keyboard, 
        parse_mode=ParseMode.HTML
    )
    return ADMIN_TEST_ACCOUNT_MENU


async def toggle_test_account_activation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    new_status = query.data == "admin_test_acc_enable"
    await crud_bot_setting.save_bot_settings({'is_test_account_enabled': new_status})
    
    text = await _get_test_account_menu_text()
    keyboard = await get_test_account_settings_keyboard()
    
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    except error.BadRequest as e:
        if "Message is not modified" not in str(e):
            LOGGER.error(f"Error editing test account menu: {e}")
            
    return ADMIN_TEST_ACCOUNT_MENU


async def prompt_for_value(update: Update, context: ContextTypes.DEFAULT_TYPE, setting_key: str, prompt_text_key: str) -> int:
    query = update.callback_query
    await query.answer()
    
    settings = await crud_bot_setting.load_bot_settings()
    current_value = settings.get(setting_key, _("marzban_credentials.not_set"))
    prompt_text = _(prompt_text_key, current=current_value)
    
    context.user_data['setting_to_change'] = setting_key
    
    try:
        await query.message.delete()
    except error.BadRequest:
        LOGGER.warning("Could not delete test account menu message (it might have been deleted already).")

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=prompt_text,
        parse_mode=ParseMode.HTML
    )
    
    if setting_key == 'test_account_hours': return GET_HOURS
    if setting_key == 'test_account_gb': return GET_GB
    if setting_key == 'test_account_limit': return GET_LIMIT


async def prompt_for_hours(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await prompt_for_value(update, context, 'test_account_hours', "bot_settings.test_account_v2.prompt_for_hours")


async def prompt_for_gb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await prompt_for_value(update, context, 'test_account_gb', "bot_settings.test_account_v2.prompt_for_gb")


async def prompt_for_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await prompt_for_value(update, context, 'test_account_limit', "bot_settings.test_account_v2.prompt_for_limit")


# --- START: Replace this function in modules/bot_settings/actions.py ---

async def process_and_save_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    value_text = update.message.text.strip()
    setting_key = context.user_data.get('setting_to_change')
    
    if not setting_key:
        return await back_to_management_menu(update, context)

    try:
        # ✨ FIX: Allow both 'hours' and 'gb' to be float values
        if setting_key in ['test_account_hours', 'test_account_gb']:
            value = float(value_text)
        else:
            value = int(value_text)
            
        if value <= 0:
            raise ValueError("Value must be positive.")
            
    except (ValueError, TypeError):
        await update.message.reply_text(_("bot_settings.test_account_v2.invalid_number"))
        if setting_key == 'test_account_hours': return GET_HOURS
        if setting_key == 'test_account_gb': return GET_GB
        if setting_key == 'test_account_limit': return GET_LIMIT

    await crud_bot_setting.save_bot_settings({setting_key: value})
    
    try:
        await update.message.delete()
    except error.BadRequest:
        LOGGER.warning("Could not delete user input message (it might have been deleted already).")

    context.user_data.clear()
    
    return await start_test_account_settings(update, context, should_delete_trigger_message=False)

# --- END: Replace this function ---


async def back_to_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    chat_id = update.effective_chat.id
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except error.BadRequest:
            pass
    
    await context.bot.send_message(chat_id, _("bot_settings.helper_tools_menu_title"), reply_markup=get_helper_tools_keyboard())

    return ConversationHandler.END


async def end_conv_and_show_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Displays the main 'Settings & Tools' menu to the admin
    and ends any conversation that led here.
    """
    from shared.keyboards import get_settings_and_tools_keyboard
    from shared.translator import translator

    # Clear user_data to prevent state leakage from previous conversations
    context.user_data.clear()
    
    await update.message.reply_text(
        translator.get("bot_settings.welcome_to_settings_and_tools"),
        reply_markup=get_settings_and_tools_keyboard()
    )
    
    # This is the crucial part that ends the conversation
    return ConversationHandler.END

# --- ADD THIS FUNCTION to the end of modules/bot_settings/actions.py ---
async def toggle_auto_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Toggles the auto-confirmation of invoices."""
    query = update.callback_query
    # Determine the new status based on the callback data
    new_status = (query.data == "toggle_auto_confirm_enable")

    await crud_bot_setting.save_bot_settings({"auto_confirm_invoices": new_status})
    feedback = _("bot_settings.feedback_auto_confirm_enabled") if new_status else _("bot_settings.feedback_auto_confirm_disabled")
    await query.answer(feedback, show_alert=True)
    
    # Rebuild and show the menu with the updated button
    await _build_and_send_main_settings_menu(update, context)
    return MENU_STATE

async def show_settings_and_tools_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Just displays the 'Settings & Tools' menu without ending any conversation."""
    from shared.keyboards import get_settings_and_tools_keyboard
    from shared.translator import translator
    
    await update.message.reply_text(
        translator.get("bot_settings.welcome_to_settings_and_tools"),
        reply_markup=get_settings_and_tools_keyboard()
    )
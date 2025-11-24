# FILE: shared/auth.py 
# --- START OF FILE ---

from functools import wraps
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler, MessageHandler, filters, CommandHandler
from telegram import error, InlineKeyboardButton, InlineKeyboardMarkup
from config import config
from shared.translator import _
from database.crud.admin import is_support_admin

LOGGER = logging.getLogger(__name__)

async def is_admin(user_id: int) -> bool:
    """
    Checks if a user is either a Super Admin (from .env) OR a Support Admin (from DB).
    """
    # 1. Check Super Admin (File .env)
    if user_id in config.AUTHORIZED_USER_IDS:
        return True
    
    # 2. Check Support Admin (Database)
    try:
        if await is_support_admin(user_id):
            return True
    except Exception as e:
        LOGGER.error(f"Database error checking admin status for {user_id}: {e}")
        
    return False

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not await is_admin(user.id):
            LOGGER.warning(f"Unauthorized access denied for {user.id if user else 'Unknown'} in '{func.__name__}'.")
            if update.message:
                await update.message.reply_text(_("errors.admin_only_command"))
            elif update.callback_query:
                await update.callback_query.answer(_("errors.admin_only_callback"), show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def admin_only_conv(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or not await is_admin(user.id):
            LOGGER.warning(f"Unauthorized access for {user.id if user else 'Unknown'} to conv '{func.__name__}'.")
            if update.message:
                await update.message.reply_text(_("errors.admin_only_section"))
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapped
def admin_only_callback(func):
    """
    Decorator to restrict access to callback query handlers to admins only.
    Shows an alert on the callback query if the user is not authorized.
    """
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        query = update.callback_query
        user = query.from_user
        
        if not user or not await is_admin(user.id):
            LOGGER.warning(f"Unauthorized callback query access denied for {user.id if user else 'Unknown'} in '{func.__name__}'.")
            # Answer the callback query with an error message to give feedback to the user
            await query.answer(_("errors.admin_only_callback"), show_alert=True)
            return  # Stop further execution
            
        # If authorized, proceed with the original function
        return await func(update, context, *args, **kwargs)
    return wrapped

def get_admin_fallbacks():
    """
    Returns a list of universal fallback handlers for all admin conversations.
    This function should be called at RUNTIME to ensure translations are loaded.
    """
    # ✨ FIX: Import the correct, existing fallback function.
    from shared.callbacks import main_menu_fallback
    
    # ✨ FIX: Create a comprehensive list of all possible main menu and "back to main menu" buttons
    # that an admin might press to exit a conversation.
    admin_menu_and_back_buttons = [
        # Main Menu Buttons
        _("keyboards.admin_main_menu.manage_users"),
        _("keyboards.admin_main_menu.search_user"),
        _("keyboards.admin_main_menu.notes_management"),
        _("keyboards.admin_main_menu.settings_and_tools"),
        _("keyboards.admin_main_menu.customer_info"),
        _("keyboards.admin_main_menu.send_message"),
        _("keyboards.admin_main_menu.guides_settings"),
        _("keyboards.admin_main_menu.customer_panel_view"),
        
        # "Back to Main Menu" buttons from various sub-menus
        _("keyboards.user_management.back_to_main_menu"),
        _("keyboards.settings_and_tools.back_to_main_menu"),
        _("keyboards.notes_management.back_to_main_menu"),
        _("keyboards.general.back_to_main_menu") # Generic back button
    ]
    
    # Filter out any potential None values if a translation key is missing
    valid_buttons = [btn for btn in admin_menu_and_back_buttons if btn]
    
    # Create a single filter for all these buttons
    main_menu_filter = filters.Text(valid_buttons)

    # ✨ FIX: The fallback list is now simple and clear. Both pressing a menu button
    # and using /cancel will trigger the same clean exit function.
    return [
        MessageHandler(main_menu_filter, main_menu_fallback),
        CommandHandler('cancel', main_menu_fallback)
    ]

# The rest of the file remains unchanged.

def _create_join_channel_keyboard(channel_username: str) -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton(_("keyboards.forced_join.join_channel_button"), url=f"https://t.me/{channel_username}")],
        [InlineKeyboardButton(_("keyboards.forced_join.check_membership_button"), callback_data="check_join_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

def ensure_channel_membership(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        from database.crud import bot_setting as crud_bot_setting
        user = update.effective_user
        if not user:
            return

        if await is_admin(user.id):
            return await func(update, context, *args, **kwargs)

        settings = await crud_bot_setting.load_bot_settings()
        is_enabled = settings.get('is_forced_join_active', False)
        
        if not is_enabled:
            return await func(update, context, *args, **kwargs)

        channel_username = settings.get('forced_join_channel')
        
        if not channel_username:
            LOGGER.warning("Forced join is active, but no channel username is configured.")
            return await func(update, context, *args, **kwargs)

        try:
            member = await context.bot.get_chat_member(chat_id=f"@{channel_username}", user_id=user.id)
            if member.status in ['member', 'administrator', 'creator']:
                return await func(update, context, *args, **kwargs)
        except (error.BadRequest, error.Forbidden) as e:
            LOGGER.error(f"Error checking membership for @{channel_username}: {e}. Disabling check temporarily for this user.")
            return await func(update, context, *args, **kwargs)

        message_text = _("general.forced_join_message", channel=f"@{channel_username}")
        keyboard = _create_join_channel_keyboard(channel_username)
        
        target_message = update.effective_message
        if update.callback_query:
            await update.callback_query.answer(_("general.errors.not_joined_yet"), show_alert=True)
            try:
                await target_message.edit_text(text=message_text, reply_markup=keyboard, parse_mode='HTML')
            except error.BadRequest as e:
                if "Message is not modified" not in str(e):
                    await context.bot.send_message(chat_id=user.id, text=message_text, reply_markup=keyboard, parse_mode='HTML')
        else:
            await target_message.reply_html(text=message_text, reply_markup=keyboard)

    return wrapped

is_user_admin = is_admin
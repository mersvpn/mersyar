# --- START OF FILE modules/general/actions.py ---
import logging
from telegram import Update, User
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from database.crud import user as crud_user
from database.crud import bot_setting as crud_bot_setting
from config import config
from shared.auth import is_admin, admin_only, ensure_channel_membership
import html
from telegram.ext import ConversationHandler
from modules.bot_settings.data_manager import is_bot_active
from shared.log_channel import log_new_user_joined
from shared.translator import _
from shared.keyboards import (
    get_customer_main_menu_keyboard,
    get_admin_main_menu_keyboard,
    get_customer_view_for_admin_keyboard
)
from telegram.ext import ContextTypes, ConversationHandler, ApplicationHandlerStop
from modules.marzban.actions.data_manager import normalize_username
from database.crud import marzban_link as crud_marzban_link
# ✨ NEW IMPORTS FOR MULTI-PANEL ARCHITECTURE (TEMPORARY FIX)
from typing import Optional, List, Dict, Any
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
import logging

async def get_user_data(username: str):
    """Temporary stand-in function to get user data from the first available panel."""
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        logging.getLogger(__name__).warning("ACTION FAILED: No panels are configured in the database.")
        return None
    
    first_panel = all_panels[0]
    credentials = {'api_url': first_panel.api_url, 'username': first_panel.username, 'password': first_panel.password}
    api = MarzbanPanel(credentials)
    return await api.get_user_data(username)
# --- END OF TEMPORARY FIX ---

LOGGER = logging.getLogger(__name__)


# --- REPLACE THIS ENTIRE FUNCTION in modules/general/actions.py ---

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Sends the appropriate main menu and ends any conversation that leads to it.
    """
    user = update.effective_user
    
    # This logic determines the message text based on whether it's a fresh start or a return.
    if context.user_data.pop('is_rerouted_from_conv', False):
        message_text = _("general.returned_to_main_menu")
    else:
        message_text = _("general.welcome", first_name=html.escape(user.first_name))


    # Determine the correct keyboard and append the dashboard message
    if user.id in config.AUTHORIZED_USER_IDS and not context.user_data.get('is_admin_in_customer_view'):
        reply_markup = get_admin_main_menu_keyboard()
        if not context.user_data.get('is_rerouted_from_conv'): # Check flag again
            message_text += "\n" + _("general.admin_dashboard_active")
    else:
        if context.user_data.get('is_admin_in_customer_view'):
            reply_markup = await get_customer_view_for_admin_keyboard()
        else:
            reply_markup = await get_customer_main_menu_keyboard(update.effective_user.id)
        if not context.user_data.get('is_rerouted_from_conv'): # Check flag again
            message_text += "\n" + _("general.customer_dashboard_prompt")

    target_message = update.effective_message
    if update.callback_query:
        try:
            await target_message.delete()
        except Exception: 
            pass
        await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=reply_markup)
    else:
        await target_message.reply_text(message_text, reply_markup=reply_markup)
        
    return ConversationHandler.END


@ensure_channel_membership
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    The main entry point. It intelligently displays the correct welcome message
    based on whether the user is starting fresh or returning from a conversation.
    """
    user = update.effective_user
    is_return_from_conv = context.user_data.pop('is_rerouted_from_conv', False)

    if not is_return_from_conv:
        LOGGER.critical(f"!!!!!! [CRITICAL LOG] Fresh 'start' CALLED for user {user.id}. !!!!!!")
        if not await is_bot_active() and not await is_admin(user.id):
            await update.message.reply_markdown(
                "**🛠 ربات در حال تعمیر و به‌روزرسانی است**\n\n"
                "در حال حاضر امکان پاسخگویی وجود ندارد. لطفاً کمی بعد دوباره تلاش کنید.\n\n"
                "از شکیبایی شما سپاسگزاریم."
            )
            return
        
        try:
            is_new_user = await crud_user.add_or_update_user(user)
            if is_new_user:
                await log_new_user_joined(context.bot, user)
                bot_settings = await crud_bot_setting.load_bot_settings()
                welcome_gift = bot_settings.get('welcome_gift_amount', 0)
                if welcome_gift > 0:
                    await crud_user.increase_wallet_balance(user.id, welcome_gift)
                    gift_message = _("general.welcome_gift_received", amount=f"{welcome_gift:,}")
                    await context.bot.send_message(chat_id=user.id, text=gift_message)
        except Exception as e:
            LOGGER.error(_("errors.db_user_save_failed", user_id=user.id, error=e))

    if is_return_from_conv:
        message_text = _("general.returned_to_main_menu")
    else:
        message_text = _("general.welcome", first_name=html.escape(user.first_name))

    if user.id in config.AUTHORIZED_USER_IDS and not context.user_data.get('is_admin_in_customer_view'):
        reply_markup = get_admin_main_menu_keyboard()
        if not is_return_from_conv:
            message_text += "\n" + _("general.admin_dashboard_active")
    else:
        if context.user_data.get('is_admin_in_customer_view'):
            reply_markup = await get_customer_view_for_admin_keyboard()
        else:
            reply_markup = await get_customer_main_menu_keyboard(user.id)
        if not is_return_from_conv:
             message_text += "\n" + _("general.customer_dashboard_prompt")
    
    await update.effective_message.reply_text(message_text, reply_markup=reply_markup)


@admin_only
async def switch_to_customer_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['is_admin_in_customer_view'] = True
    await update.message.reply_text(
        _("general.views.switched_to_customer"),
        reply_markup=await get_customer_view_for_admin_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )

@admin_only
async def switch_to_admin_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop('is_admin_in_customer_view', 'None')
    await update.message.reply_text(
        _("general.views.switched_to_admin"),
        reply_markup=get_admin_main_menu_keyboard(), parse_mode=ParseMode.MARKDOWN
    )
    
async def show_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    message_text = _("general.your_telegram_id", user_id=user_id)
    await update.message.reply_text(message_text, parse_mode=ParseMode.MARKDOWN)


async def end_conv_and_reroute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from modules.customer.actions import panel, service, guide
    text = update.message.text
    LOGGER.info(f"--- Main menu override for user {update.effective_user.id} by '{text}'. Ending conversation and rerouting. ---")

    shop_button_text = _("keyboards.customer_main_menu.shop")
    services_button_text = _("keyboards.customer_main_menu.my_services")
    guide_button_text = _("keyboards.customer_main_menu.connection_guide")

    if text == shop_button_text:
        await panel.show_customer_panel(update, context)
    elif text == services_button_text:
        await service.handle_my_service(update, context)
    elif text == guide_button_text:
        await guide.show_guides_to_customer(update, context)
    else:
        await start(update, context)

    context.user_data.clear()
    return ConversationHandler.END


async def notify_admins_on_link(context: ContextTypes.DEFAULT_TYPE, customer: User, marzban_username: str):
    message = _(
        "general.linking_admin_notification", 
        customer_name=html.escape(customer.full_name), 
        customer_id=customer.id, 
        username=html.escape(marzban_username)
    )
    for admin_id in config.AUTHORIZED_USER_IDS:
        try:
            await context.bot.send_message(chat_id=admin_id, text=message, parse_mode=ParseMode.HTML)
        except Exception as e:
            LOGGER.error(f"Failed to send linking notification to admin {admin_id}: {e}")

# --- START: Replace the entire handle_deep_link function ---

async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if args and len(args) > 0 and args[0].startswith("link-"):
        marzban_username_raw = args[0].split('-', 1)[1]
        marzban_username_normalized = normalize_username(marzban_username_raw)
        telegram_user_id = user.id
        LOGGER.info(f"User {telegram_user_id} started bot with deep link for Marzban user '{marzban_username_raw}'.")
        
        # In a multi-panel setup, a deep link doesn't know which panel the user is on.
        # We must search all panels.
        user_panel_data = await get_user_data(marzban_username_normalized) # Uses our temporary function
        
        if not user_panel_data:
            await update.message.reply_text(_("marzban.linking.user_not_found"))
        else:
            # ✨ NEW LOGIC: We found the user, now we need to know which panel it was on.
            # The panel_id should be in the user_panel_data from our temporary function,
            # but for a robust solution, we find the panel again.
            panel_id_to_link = user_panel_data.get('panel_id')

            if not panel_id_to_link:
                # Fallback: if the temporary get_user_data doesn't return panel_id, we just use the first panel.
                all_panels = await crud_panel.get_all_panels()
                if all_panels:
                    panel_id_to_link = all_panels[0].id
                else:
                    LOGGER.error(f"Cannot link user {marzban_username_normalized}: No panels configured.")
                    await update.message.reply_text(_("marzban.linking.link_error"))
                    await start(update, context)
                    return
            
            # ✨ MODIFIED: Use the new CRUD function with panel_id
            success = await crud_marzban_link.create_or_update_link(marzban_username_normalized, telegram_user_id, panel_id_to_link)
            
            if success:
                safe_username = html.escape(marzban_username_raw)
                await update.message.reply_text(_("marzban.linking.link_successful", username=safe_username), parse_mode=ParseMode.HTML)
                await notify_admins_on_link(context, user, marzban_username_raw)
            else:
                await update.message.reply_text(_("marzban.linking.link_error"))

    await start(update, context)

# FILE: modules/general/actions.py
# REPLACE THIS FUNCTION

async def end_conversation_and_show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    A wrapper for send_main_menu, designed to be used as a fallback in ConversationHandlers.
    It sets a flag, shows the main menu, and explicitly ends the conversation.
    """
    # ✨ FIX: Set the flag BEFORE calling send_main_menu
    context.user_data['is_rerouted_from_conv'] = True
    
    # Now, call send_main_menu which will read the flag and show the correct message.
    await send_main_menu(update, context)
    
    async def end_conversation_and_show_main_menu(update, context):
        context.user_data['is_rerouted_from_conv'] = True
        await send_main_menu(update, context)
        return ConversationHandler.END


async def close_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes the message containing the callback query button."""
    query = update.callback_query
    await query.answer()  # Answer the callback to remove the "loading" icon
    try:
        await query.message.delete()
    except Exception as e:
        # Log if the message couldn't be deleted (e.g., too old, no rights)
        LOGGER.warning(f"Could not delete message {query.message.message_id} for user {query.from_user.id}: {e}")

# --- ADD THIS FUNCTION to the end of modules/general/actions.py ---
async def back_to_main_menu_simple(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.critical("!!!!!! [TRACE] Function 'back_to_main_menu_simple' in general/actions.py CALLED. !!!!!!")
    """
    A simple action that only shows the "Returned to main menu" message.
    It's meant to be used by a global MessageHandler.
    """
    from shared.keyboards import get_admin_main_menu_keyboard
    from shared.translator import _
    
    await update.message.reply_text(
        _("general.returned_to_main_menu"),
        reply_markup=get_admin_main_menu_keyboard()
    )

    raise ApplicationHandlerStop
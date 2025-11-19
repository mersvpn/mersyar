# --- START OF FILE modules/general/actions.py ---
import logging
import html
from typing import Optional, List, Dict, Any
from decimal import Decimal

from telegram import Update, User
from telegram.ext import ContextTypes, ConversationHandler, ApplicationHandlerStop
from telegram.constants import ParseMode

from database.crud import user as crud_user
from database.crud import bot_setting as crud_bot_setting
from database.crud import marzban_link as crud_marzban_link
from database.crud import panel_credential as crud_panel
from config import config
from shared.auth import is_admin, admin_only, ensure_channel_membership
from modules.bot_settings.data_manager import is_bot_active
from shared.log_channel import log_new_user_joined
from shared.translator import _
from shared.keyboards import (
    get_customer_main_menu_keyboard,
    get_admin_main_menu_keyboard,
    get_customer_view_for_admin_keyboard
)
from modules.marzban.actions.data_manager import normalize_username
from core.panel_api.marzban import MarzbanPanel

LOGGER = logging.getLogger(__name__)

# --- TEMPORARY FIX FOR MULTI-PANEL ARCHITECTURE ---
async def get_user_data(username: str):
    """Temporary stand-in function to get user data from the first available panel."""
    all_panels = await crud_panel.get_all_panels()
    if not all_panels:
        LOGGER.warning("ACTION FAILED: No panels are configured in the database.")
        return None
    
    # Try to find user in all panels
    for panel in all_panels:
        try:
            credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
            api = MarzbanPanel(credentials)
            user_data = await api.get_user_data(username)
            if user_data:
                # Attach panel_id to result for linking logic
                user_data['panel_id'] = panel.id
                return user_data
        except Exception as e:
            LOGGER.warning(f"Failed to check panel {panel.name} for user {username}: {e}")
            continue
            
    return None
# --- END OF TEMPORARY FIX ---


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
        if not context.user_data.get('is_rerouted_from_conv'): 
            message_text += "\n" + _("general.admin_dashboard_active")
    else:
        if context.user_data.get('is_admin_in_customer_view'):
            reply_markup = await get_customer_view_for_admin_keyboard()
        else:
            reply_markup = await get_customer_main_menu_keyboard(update.effective_user.id)
        if not context.user_data.get('is_rerouted_from_conv'): 
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
            # Maintenance Mode Message
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
                    await crud_user.increase_wallet_balance(user.id, Decimal(welcome_gift))
                    gift_message = _("general.welcome_gift_received", amount=f"{welcome_gift:,}")
                    await context.bot.send_message(chat_id=user.id, text=gift_message)
        except Exception as e:
            LOGGER.error(_("errors.db_user_save_failed", user_id=user.id, error=e))

    # Reuse send_main_menu logic manually here to avoid recursion issues or complex logic duplication
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


async def handle_deep_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if args and len(args) > 0 and args[0].startswith("link-"):
        marzban_username_raw = args[0].split('-', 1)[1]
        marzban_username_normalized = normalize_username(marzban_username_raw)
        telegram_user_id = user.id
        LOGGER.info(f"User {telegram_user_id} started bot with deep link for Marzban user '{marzban_username_raw}'.")
        
        user_panel_data = await get_user_data(marzban_username_normalized)
        
        if not user_panel_data:
            await update.message.reply_text(_("marzban.linking.user_not_found"))
        else:
            panel_id_to_link = user_panel_data.get('panel_id')

            if not panel_id_to_link:
                all_panels = await crud_panel.get_all_panels()
                if all_panels:
                    panel_id_to_link = all_panels[0].id
                else:
                    LOGGER.error(f"Cannot link user {marzban_username_normalized}: No panels configured.")
                    await update.message.reply_text(_("marzban.linking.link_error"))
                    await start(update, context)
                    return
            
            success = await crud_marzban_link.create_or_update_link(marzban_username_normalized, telegram_user_id, panel_id_to_link)
            
            if success:
                safe_username = html.escape(marzban_username_raw)
                await update.message.reply_text(_("marzban.linking.link_successful", username=safe_username), parse_mode=ParseMode.HTML)
                await notify_admins_on_link(context, user, marzban_username_raw)
            else:
                await update.message.reply_text(_("marzban.linking.link_error"))

    await start(update, context)


# --- COMPATIBILITY FIX: BOTH FUNCTIONS EXIST ---

async def end_conversation_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    New function name as required by panel_manager.
    """
    context.user_data['is_rerouted_from_conv'] = True
    await send_main_menu(update, context)
    return ConversationHandler.END

async def end_conversation_and_show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Old function name kept for backward compatibility with other modules.
    Redirects to the new function logic.
    """
    return await end_conversation_and_show_menu(update, context)


async def close_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Deletes the message containing the callback query button."""
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception as e:
        LOGGER.warning(f"Could not delete message {query.message.message_id} for user {query.from_user.id}: {e}")


async def back_to_main_menu_simple(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    A simple action that only shows the "Returned to main menu" message.
    It's meant to be used by a global MessageHandler.
    """
    logging.critical("!!!!!! [TRACE] Function 'back_to_main_menu_simple' in general/actions.py CALLED. !!!!!!")
    
    await update.message.reply_text(
        _("general.returned_to_main_menu"),
        reply_markup=get_admin_main_menu_keyboard()
    )

    raise ApplicationHandlerStop
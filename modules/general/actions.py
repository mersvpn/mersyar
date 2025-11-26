# --- START OF FILE modules/general/actions.py ---
import logging
import html
import re
from typing import Optional, List, Dict, Any
from decimal import Decimal

from telegram import Update, User
from telegram.ext import ContextTypes, ConversationHandler, ApplicationHandlerStop # <--- ایمپورت مهم
from telegram.constants import ParseMode
from database.crud.admin import is_support_admin
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
                user_data['panel_id'] = panel.id
                return user_data
        except Exception as e:
            LOGGER.warning(f"Failed to check panel {panel.name} for user {username}: {e}")
            continue
            
    return None
# --- END OF TEMPORARY FIX ---

async def send_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Sends the appropriate main menu and ends any conversation.
    """
    user = update.effective_user
    
    # تشخیص اینکه آیا این یک "بازگشت" است یا "شروع"
    message_text_content = update.message.text if update.message else ""
    back_button_text = _("keyboards.general.back_to_main_menu")
    
    is_returning = context.user_data.pop('is_rerouted_from_conv', False) or \
                   (message_text_content and back_button_text and back_button_text in message_text_content)

    if is_returning:
        message_text = _("general.returned_to_main_menu")
    else:
        message_text = _("general.welcome", first_name=html.escape(user.first_name))

    is_super_admin = user.id in config.AUTHORIZED_USER_IDS
    
    if is_super_admin and not context.user_data.get('is_admin_in_customer_view'):
        reply_markup = get_admin_main_menu_keyboard()
        if not is_returning: 
            message_text += "\n" + _("general.admin_dashboard_active")
    else:
        if context.user_data.get('is_admin_in_customer_view'):
            reply_markup = await get_customer_view_for_admin_keyboard()
        else:
            reply_markup = await get_customer_main_menu_keyboard(user.id)
            
        if not is_returning: 
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
    user = update.effective_user
    
    # --- CHECK FOR BACK BUTTON (Emergency Stop) ---
    # اگر متن پیام "بازگشت" بود، فوراً متوقف شو و به back_to_main_menu_simple برو
    text = update.message.text if update.message else ""
    back_text = _("keyboards.general.back_to_main_menu")
    if text and (text == back_text or "بازگشت به منوی اصلی" in text):
        await back_to_main_menu_simple(update, context)
        return # اینجا ریترن میکنیم چون back_to_main_menu_simple خودش raise میکند
    # ----------------------------------------------

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
                    await crud_user.increase_wallet_balance(user.id, Decimal(welcome_gift))
                    gift_message = _("general.welcome_gift_received", amount=f"{welcome_gift:,}")
                    await context.bot.send_message(chat_id=user.id, text=gift_message)
        except Exception as e:
            LOGGER.error(_("errors.db_user_save_failed", user_id=user.id, error=e))

        if context.args and len(context.args) > 0:
            arg = context.args[0]
            if arg.startswith("link-"):
                marzban_username_raw = arg.split('-', 1)[1]
                marzban_username_normalized = normalize_username(marzban_username_raw)
                user_panel_data = await get_user_data(marzban_username_normalized)
                
                if not user_panel_data:
                    await update.message.reply_text(_("marzban.linking.user_not_found"))
                else:
                    panel_id_to_link = user_panel_data.get('panel_id')
                    if not panel_id_to_link:
                        all_panels = await crud_panel.get_all_panels()
                        if all_panels: panel_id_to_link = all_panels[0].id
                    
                    if panel_id_to_link:
                        success = await crud_marzban_link.create_or_update_link(marzban_username_normalized, user.id, panel_id_to_link)
                        if success:
                            safe_username = html.escape(marzban_username_raw)
                            await update.message.reply_text(_("marzban.linking.link_successful", username=safe_username), parse_mode=ParseMode.HTML)
                            await notify_admins_on_link(context, user, marzban_username_raw)
                        else:
                            await update.message.reply_text(_("marzban.linking.link_error"))
                context.args.clear()

            elif arg.startswith("details_"):
                from modules.marzban.actions import display
                if await is_admin(user.id):
                    await display.handle_deep_link_details(update, context)
                    return 

    await send_main_menu(update, context)


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
    """
    Central hub for handling text buttons when a user is stuck or navigating.
    """
    from modules.customer.actions import panel, service, guide
    text = update.message.text
    LOGGER.info(f"--- Reroute triggered by: '{text}' ---")

    shop_button_text = _("keyboards.customer_main_menu.shop")
    services_button_text = _("keyboards.customer_main_menu.my_services")
    guide_button_text = _("keyboards.customer_main_menu.connection_guide")
    back_button_text = _("keyboards.general.back_to_main_menu")

    # --- CHECK FOR BACK BUTTON FIRST ---
    if text == back_button_text or "بازگشت به منوی اصلی" in str(text):
        # This is the fix: Stop here, don't go to start()
        await back_to_main_menu_simple(update, context)
        # The above function raises ApplicationHandlerStop, but we return END just in case
        return ConversationHandler.END
    # -----------------------------------

    if text == shop_button_text:
        await panel.show_customer_panel(update, context)
    elif text == services_button_text:
        await service.handle_my_service(update, context)
    elif text == guide_button_text:
        await guide.show_guides_to_customer(update, context)
    else:
        # If unknown text, fall back to start (but start now has checks too)
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
        # ... (Deep link logic remains same) ...
        pass
    await start(update, context)


# --- COMPATIBILITY FUNCTIONS ---

async def end_conversation_and_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['is_rerouted_from_conv'] = True
    await send_main_menu(update, context)
    return ConversationHandler.END

async def end_conversation_and_show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await end_conversation_and_show_menu(update, context)


async def close_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    try:
        await query.message.delete()
    except Exception:
        pass


async def back_to_main_menu_simple(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the main menu button click.
    Super Admin -> Admin Panel.
    Everyone else (including Support Admin) -> Customer Menu.
    """
    user = update.effective_user
    
    # ذخیره حالت نمای مشتری برای سوپر ادمین
    was_in_customer_view = context.user_data.get('is_admin_in_customer_view', False)
    
    context.user_data.clear()
    
    is_super_admin = user.id in config.AUTHORIZED_USER_IDS
    
    if is_super_admin:
        if was_in_customer_view:
            # سوپر ادمین در حال تست -> منوی مشتری
            context.user_data['is_admin_in_customer_view'] = True
            reply_markup = await get_customer_view_for_admin_keyboard()
        else:
            # سوپر ادمین عادی -> منوی مدیریت
            reply_markup = get_admin_main_menu_keyboard()
    else:
        # *** تغییر مهم اینجاست ***
        # همه افراد دیگر (کاربر عادی + ادمین پشتیبان) به منوی مشتری می‌روند.
        # ادمین پشتیبان دکمه ورود به پنلش را در همین منو خواهد دید.
        reply_markup = await get_customer_main_menu_keyboard(user.id)

    await update.message.reply_text(
        _("general.returned_to_main_menu"),
        reply_markup=reply_markup
    )

    raise ApplicationHandlerStop
# FILE: modules/customer/actions/test_account.py (FULLY REWRITTEN FOR MULTI-PANEL AND STABILITY)
import random
import logging
import qrcode
import io
import html
import re
import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from typing import Optional
from database.models.panel_credential import PanelType

# Local project imports
from database.crud import (
    bot_setting as crud_bot_setting,
    user as crud_user,
    user_note as crud_user_note,
    marzban_link as crud_marzban_link,
    bot_managed_user as crud_bot_managed_user,
    panel_credential as crud_panel
)
from modules.marzban.actions.add_user import add_user_to_panel_from_template
from shared.translator import translator
from shared.log_channel import send_log
from shared.keyboards import get_connection_guide_keyboard
from shared.auth import is_user_admin
from core.panel_api.base import PanelAPI
from core.panel_api.marzban import MarzbanPanel

LOGGER = logging.getLogger(__name__)

# Conversation state
ASK_USERNAME = 0


async def _get_api_for_panel(panel) -> Optional[PanelAPI]:
    """Helper factory to create an API object from a panel DB object."""
    # اصلاح شده: استفاده از PanelType.MARZBAN برای مقایسه دقیق
    if panel.panel_type == PanelType.MARZBAN:
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        return MarzbanPanel(credentials)
    return None


async def _cleanup_test_account_job(context: ContextTypes.DEFAULT_TYPE):
    """
    This job runs when a test account expires, notifies the user, and deletes the account.
    """
    job = context.job
    marzban_username = job.data['marzban_username']
    chat_id = job.data['chat_id']
    
    LOGGER.info(f"Job triggered: Notifying user {chat_id} about expired test account '{marzban_username}'.")
    
    link = await crud_marzban_link.get_link_with_panel_by_username(marzban_username)
    if not link or not link.panel:
        LOGGER.error(f"Cleanup job for '{marzban_username}' failed: Could not find panel link in DB.")
        return

    api = await _get_api_for_panel(link.panel)
    if not api:
        LOGGER.error(f"Cleanup job for '{marzban_username}' failed: Could not create API object for panel.")
        return

    try:
        keyboard = get_connection_guide_keyboard(is_for_test_account_expired=True)
        message_text = translator.get("customer.test_account.account_expired_notification", username=f"<code>{marzban_username}</code>")
        
        await context.bot.send_message(
            chat_id=chat_id, text=message_text,
            parse_mode=ParseMode.HTML, reply_markup=keyboard
        )

        success, message = await api.delete_user(marzban_username)
        
        if success or ("User not found" in str(message)):
            LOGGER.info(f"Successfully deleted or confirmed deletion of test account '{marzban_username}' from panel '{link.panel.name}'.")
            await crud_marzban_link.delete_marzban_link(marzban_username)
            await crud_user_note.delete_user_note(marzban_username)
            await crud_bot_managed_user.remove_from_managed_list(marzban_username)
        else:
            LOGGER.error(f"Failed to delete expired test account '{marzban_username}'. API Error: {message}")
            await context.bot.send_message(
                chat_id=chat_id,
                text=translator.get("customer.test_account.account_expired_notification_api_fail"),
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        LOGGER.error(f"Critical error in _cleanup_test_account_job for {marzban_username}: {e}", exc_info=True)


async def handle_test_account_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    chat_id = update.effective_chat.id
    query = update.callback_query

    async def reply(text):
        if query:
            await query.answer()
            await context.bot.send_message(chat_id, text)
        else:
            await update.message.reply_text(text)

    bot_settings = await crud_bot_setting.load_bot_settings()
    is_enabled = bot_settings.get('is_test_account_enabled', False)
    
    if not is_enabled:
        await reply(translator.get("customer.test_account.not_available"))
        return ConversationHandler.END

    if query and query.message:
        await query.message.delete()

    if not await is_user_admin(user.id):
        limit = bot_settings.get('test_account_limit', 1)
        received_count = await crud_user.get_user_test_account_count(user.id)
        if received_count >= limit:
            await reply(translator.get("customer.test_account.limit_reached", limit=limit))
            return ConversationHandler.END
    
    await reply(translator.get("customer.test_account.prompt_for_username"))
    return ASK_USERNAME


async def get_username_and_create_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    base_username = update.message.text.strip()
    
    if not base_username or ' ' in base_username or not re.match(r"^[a-zA-Z0-9_]+$", base_username):
        await update.message.reply_text(translator.get("customer.test_account.invalid_username"))
        return ASK_USERNAME

    final_username = f"{base_username}test"

    active_test_panels = await crud_panel.get_active_test_panels()
    if not active_test_panels:
        await update.message.reply_text(translator.get("customer.test_account.not_available_now"))
        return ConversationHandler.END

    # Select one panel randomly from the active ones
    panel_for_test = random.choice(active_test_panels)
    panel_name_for_log = panel_for_test.name
    api = await _get_api_for_panel(panel_for_test)
    if not api:
        await update.message.reply_text(translator.get('marzban.marzban_add_user.error_generic'))
        return ConversationHandler.END

    existing_user = await api.get_user_data(final_username)
    if existing_user:
        await update.message.reply_text(
            translator.get("customer.test_account.username_taken", final_username=final_username),
            parse_mode=ParseMode.MARKDOWN
        )
        return ASK_USERNAME

    processing_message = await update.message.reply_text(translator.get("customer.test_account.processing"))

    bot_settings = await crud_bot_setting.load_bot_settings()
    
    # ✨ FIX: Provide default values and validate them to prevent 'None' error
    try:
        hours = float(bot_settings.get('test_account_hours', 3.0))
        gb = float(bot_settings.get('test_account_gb', 1.0))
        if hours <= 0 or gb <= 0: raise ValueError
    except (ValueError, TypeError):
        LOGGER.warning("Invalid test account settings in DB. Using defaults (3 hours, 1 GB).")
        hours = 3.0
        gb = 1.0
        
    days_from_hours = hours / 24

    try:
        new_user_data = await add_user_to_panel_from_template(
            api=api, 
            panel_id=panel_for_test.id,
            data_limit_gb=gb, 
            expire_days=days_from_hours, 
            username=final_username
        )
    except Exception as e:
        LOGGER.error(f"Failed to create user from template on panel {panel_for_test.name}: {e}")
        new_user_data = None

    if not new_user_data:
        await processing_message.edit_text(translator.get("customer.test_account.api_failed"))
        await send_log(bot=context.bot, text=f"🔴 API Error for Test Account\nUser: {user.id}\nUsername: `{final_username}`")
        return ConversationHandler.END

    # --- Process successful creation ---
    marzban_username = new_user_data['username']
    sub_link = new_user_data.get("subscription_url", "N/A")
    all_links = new_user_data.get("links", [])
    expire_timestamp = new_user_data.get('expire')

    await crud_user.increment_user_test_account_count(user.id)
    await crud_marzban_link.create_or_update_link(marzban_username, user.id, panel_for_test.id)
    await crud_bot_managed_user.add_to_managed_list(marzban_username)
    await crud_user_note.create_or_update_user_note(
        marzban_username=marzban_username, duration=round(days_from_hours, 2),
        data_limit_gb=gb, price=0, is_test_account=True
    )
    
    if expire_timestamp and context.job_queue:
        try:
            cleanup_time_utc = datetime.datetime.utcfromtimestamp(expire_timestamp)
            context.job_queue.run_once(
                _cleanup_test_account_job, when=cleanup_time_utc,
                data={'marzban_username': marzban_username, 'chat_id': update.effective_chat.id},
                name=f"cleanup_test_{marzban_username}"
            )
            LOGGER.info(f"Scheduled cleanup job for '{marzban_username}' at {cleanup_time_utc} UTC.")
        except Exception as e:
            LOGGER.error(f"CRITICAL: Failed to schedule cleanup job for '{marzban_username}': {e}", exc_info=True)
    
    caption_text = translator.get(
        "customer.test_account.success_v2", 
        hours=hours, 
        gb=gb, 
        username=f"<code>{html.escape(marzban_username)}</code>",
        panel_name=f"<b>{html.escape(panel_name_for_log)}</b>" # ✨ ADD THIS
    )
    caption_text += f"\n\n<code>{html.escape(sub_link)}</code>"
    reply_markup = get_connection_guide_keyboard()
    
    qr_code_image = None
    if "N/A" not in sub_link:
        try:
            img = qrcode.make(sub_link)
            buffer = io.BytesIO()
            img.save(buffer, 'PNG')
            buffer.seek(0)
            qr_code_image = buffer
        except Exception as e:
            LOGGER.error(f"Failed to generate QR code for test account: {e}")

    await processing_message.delete()
    
    if qr_code_image:
        await update.message.reply_photo(photo=qr_code_image, caption=caption_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text=caption_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)

    if all_links:
        links_str = "\n".join([f"<code>{html.escape(link)}</code>" for link in all_links])
        await update.message.reply_text(
            translator.get("customer.test_account.individual_links_title") + "\n\n" + links_str,
            parse_mode=ParseMode.HTML, disable_web_page_preview=True
        )

    user_is_admin = await is_user_admin(user.id)
    admin_flag = " (Admin)" if user_is_admin else ""
    log_message = (
        f"🧪 *Test Account Created*{admin_flag}\n\n"
        f"👤 **User:** {user.mention_html()}\n"
        f"🆔 **ID:** `{user.id}`\n"
        f"🤖 **Marzban User:** `{marzban_username}`\n"
        f"🖥️ **Panel:** `{panel_name_for_log}`" # ✨ ADD THIS LINE
    )
    await send_log(bot=context.bot, text=log_message, parse_mode=ParseMode.HTML)

    from shared.keyboards import get_customer_main_menu_keyboard
    keyboard = await get_customer_main_menu_keyboard(user_id=user.id)
    await update.message.reply_text(translator.get("general.returned_to_main_menu"), reply_markup=keyboard)
    
    return ConversationHandler.END
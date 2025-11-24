# FILE: modules/customer/actions/purchase.py (FINAL - RETURNS TO SHOP MENU)

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown
from config import config
from shared.translator import _
# ✨ MODIFIED: Import the shop keyboard instead of the main menu one
from shared.keyboards import get_customer_shop_keyboard

LOGGER = logging.getLogger(__name__)

# Define states for the conversation
GET_REQUEST_MESSAGE = 0

async def start_purchase_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Starts the purchase conversation by asking the user for their request and saving the prompt message ID.
    """
    target = update.callback_query.message if update.callback_query else update.message

    cancel_button = InlineKeyboardButton(_("buttons.cancel"), callback_data="cancel_conv")
    reply_markup = InlineKeyboardMarkup([[cancel_button]])

    prompt_message = await target.reply_text(
        text=_("manual_purchase.request_prompt"),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data['prompt_message_id'] = prompt_message.message_id
    
    return GET_REQUEST_MESSAGE

async def handle_request_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Receives the user's request, deletes the prompt, forwards it to the admin, 
    shows the shop menu, and ends the conversation.
    """
    user_request_message = update.message.text
    user = update.effective_user
    chat_id = update.effective_chat.id

    prompt_message_id = context.user_data.pop('prompt_message_id', None)
    if prompt_message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=prompt_message_id)
        except Exception as e:
            LOGGER.warning(f"Could not delete prompt message {prompt_message_id} in chat {chat_id}: {e}")

    # ✨ MODIFIED: Now sends the success message along with the 'customer shop' keyboard
    await update.message.reply_text(
        text=_("manual_purchase.request_sent_success"),
        reply_markup=await get_customer_shop_keyboard()
    )

    if config.AUTHORIZED_USER_IDS:
        safe_full_name = escape_markdown(user.full_name, version=2)
        user_info = f"کاربر {safe_full_name}"
        if user.username:
            safe_username = escape_markdown(user.username, version=2)
            user_info += f" \\(@{safe_username}\\)"
        user_info += f"\nUser ID: `{user.id}`"
        
        safe_user_request = escape_markdown(user_request_message, version=2)

        message_to_admin = _(
            "manual_purchase.admin_notification_with_request",
            user_info=user_info,
            user_request=safe_user_request
        )

        admin_keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(_("buttons.create_config_for_user"), callback_data=f"create_user_for_{user.id}")]
        ])

        for admin_id in config.AUTHORIZED_USER_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=message_to_admin,
                    reply_markup=admin_keyboard,
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            except Exception as e:
                LOGGER.error(f"Failed to send purchase notification to admin {admin_id}: {e}")
    
    return ConversationHandler.END

async def handle_support_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the direct support button, separate from the conversation."""
    if config.SUPPORT_USERNAME:
        clean_username = config.SUPPORT_USERNAME.lstrip('@')
        support_link = f"https://t.me/{clean_username}"
        message = _("manual_purchase.support_prompt", username=clean_username, support_link=support_link)
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    else:
        await update.message.reply_text(_("manual_purchase.support_unavailable"))
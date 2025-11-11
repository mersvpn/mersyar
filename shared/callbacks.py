# FILE: shared/callbacks.py

import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from .keyboards import get_admin_main_menu_keyboard, get_customer_main_menu_keyboard, get_helper_tools_keyboard
from shared.translator import _
from config import config

LOGGER = logging.getLogger(__name__)


async def admin_fallback_reroute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Handles admin main menu button presses during a conversation to gracefully
    exit the conversation and navigate to the requested menu.
    """
    from modules.marzban.actions.display import show_user_management_menu
    from modules.financials.handler import show_financial_menu
    
    user = update.effective_user
    text = update.message.text
    
    LOGGER.critical(f"!!!!!! [CRITICAL LOG] Fallback triggered for user {user.id} with text: '{text}'. Entering admin_fallback_reroute. !!!!!!")
    
    LOGGER.info(f"--- [Admin Fallback] Admin {user.id} triggered reroute with '{text}'. Ending conversation. ---")
    
    user_management_text = _("keyboards.admin_main_menu.manage_users")
    financial_settings_text = _("keyboards.admin_main_menu.financial_settings")
    
    context.user_data.clear()

    if text == user_management_text:
        from modules.marzban.actions.display import prompt_for_panel_selection
        await prompt_for_panel_selection(update, context)
    elif text == financial_settings_text:
        await show_financial_menu(update, context)
    else: 
        await update.message.reply_text(
            _("general.operation_cancelled"),
            reply_markup=get_admin_main_menu_keyboard()
        )
        
    return ConversationHandler.END



async def cancel_to_helper_tools(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels a conversation and returns the user to the helper tools menu."""
    LOGGER.debug(f"Conversation cancelled by user {update.effective_user.id}, returning to helper tools.")
    context.user_data.clear()

    message_text = "عملیات لغو شد."
    target_message = update.message or (update.callback_query and update.callback_query.message)

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.message.delete()
        except Exception as e:
            LOGGER.warning(f"Could not delete message on cancel: {e}")
    
    await context.bot.send_message(
        chat_id=target_message.chat_id,
        text=f"{message_text}\nبه منوی ابزارهای کمکی بازگشتید.",
        reply_markup=get_helper_tools_keyboard()
    )
    return ConversationHandler.END


async def show_coming_soon(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Shows a 'Coming Soon' alert to the user for features not yet implemented."""
    query = update.callback_query
    if query:
        await query.answer(text=_("general.coming_soon"), show_alert=True)


# =================================================================
# ===== START OF MODIFIED SECTION =================================
# =================================================================

async def main_menu_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    The standard and correct way to end a conversation.
    It displays the main menu and returns ConversationHandler.END.
    This prevents duplicate messages and ensures the conversation state is cleared.
    """
    from modules.general.actions import start 

    # We must clear user_data specific to the conversation
    context.user_data.clear()
    
    # Set a flag that the 'start' function will use to show the correct message
    context.user_data['is_rerouted_from_conv'] = True
    
    # Manually call the main start function
    await start(update, context) 

    # This is the most crucial part for correctly ending any conversation.
    return ConversationHandler.END

# =================================================================
# ===== END OF MODIFIED SECTION ===================================
# =================================================================


async def cancel_and_remove_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    A simple callback that answers the query and deletes the message it's attached to.
    Useful for "Cancel" buttons in inline keyboards.
    """
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.message.delete()
        except Exception as e:
            LOGGER.warning(f"Could not delete message on inline cancel callback: {e}")


async def reroute_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    This special fallback ends the current conversation and returns -1,
    which tells PTB to reprocess the update with the next handlers.
    This allows a global main menu button handler to take over.
    """
    from shared.translator import translator
    
    LOGGER.info(f"Rerouting from a conversation for user {update.effective_user.id}. Ending conversation.")
    
    await update.message.reply_text(translator.get("general.operation_cancelled"))
    
    return -1

from telegram.ext import ApplicationHandlerStop

async def cancel_conversation_and_stop_propagation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from modules.general.actions import end_conversation_and_show_main_menu

    user = update.effective_user
    LOGGER.info(f"--- [STOP] Fallback triggered for user {user.id}. Stopping propagation. ---")

    if update.callback_query:
        try:
            await update.callback_query.message.delete()
        except:
            pass
    elif update.message:
        try:
            await update.message.delete()
        except:
            pass

    await end_conversation_and_show_main_menu(update, context)

    raise ApplicationHandlerStop

async def cancel_to_panel_management(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Cancels the current conversation and shows the panel management menu.
    Used as a fallback for conversations originating from the panel manager.
    """
    from shared.keyboards import get_panel_management_keyboard
    from shared.translator import _

    context.user_data.clear()
    
    await update.message.reply_text(
        _("panel_manager.list.title_select_reply"),
        reply_markup=await get_panel_management_keyboard()
    )
    return ConversationHandler.END

async def search_back_to_main(update, context):
    from modules.general.actions import send_main_menu

    # فقط دیتای سرچ پاک شود
    for k in list(context.user_data.keys()):
        if 'search' in k or 'SEARCH' in k:
            context.user_data.pop(k, None)

    # این بار فقط این فلگ را بگذار و پاک نکن
    context.user_data['is_rerouted_from_conv'] = True

    # توجه: این تابع start را فراخوانی نمی‌کند
    await send_main_menu(update, context)

    return ConversationHandler.END


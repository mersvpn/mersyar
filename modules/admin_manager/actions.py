# FILE: modules/admin_manager/actions.py

import logging
from telegram import Update, error
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from database.crud import admin as crud_admin
from shared.translator import _
# فرض بر این است که فایل keyboards.py را در این پوشه کپی کرده‌اید
from .keyboards import (
    get_admin_list_keyboard, 
    get_admin_detail_keyboard, 
    get_add_admin_cancel_keyboard
)
from shared.keyboards import get_settings_and_tools_keyboard

LOGGER = logging.getLogger(__name__)

# استیت برای مکالمه افزودن مدیر
GET_ADMIN_ID = 1

async def show_admin_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Lists all admins using inline buttons.
    """
    admins = await crud_admin.get_all_admins()
    count = len(admins)
    
    keyboard = await get_admin_list_keyboard()
    text = _("support_panel.management.menu_title", count=count)
    
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        except error.BadRequest:
            pass
    else:
        await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


async def show_admin_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Shows details of a specific admin.
    """
    query = update.callback_query
    await query.answer()
    
    target_user_id = int(query.data.split("_")[-1])
    
    admins = await crud_admin.get_all_admins()
    target_admin = next((a for a in admins if a.user_id == target_user_id), None)
    
    if not target_admin:
        await query.answer("❌ ادمین یافت نشد.", show_alert=True)
        await show_admin_management_menu(update, context)
        return

    join_date = target_admin.created_at.strftime("%Y-%m-%d") if target_admin.created_at else "N/A"
    promoter = target_admin.promoted_by if target_admin.promoted_by else "System"
    
    text = _("support_panel.management.admin_details", 
             user_id=target_admin.user_id, 
             name=target_admin.username or "بی‌نام", 
             date=join_date, 
             promoter=promoter)
             
    keyboard = get_admin_detail_keyboard(target_user_id)
    
    await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


async def delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Deletes the selected admin.
    """
    query = update.callback_query
    target_user_id = int(query.data.split("_")[-1])
    
    success = await crud_admin.remove_admin(target_user_id)
    
    if success:
        msg = _("support_panel.management.delete_success", user_id=target_user_id)
        await query.answer(msg, show_alert=True)
    else:
        await query.answer("❌ خطا در حذف.", show_alert=True)
        
    await show_admin_management_menu(update, context)


async def start_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    msg = _("support_panel.management.prompt_add_admin")
    await query.message.delete()
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=msg,
        reply_markup=get_add_admin_cancel_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    return GET_ADMIN_ID

async def process_add_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message
    target_id = None
    target_username = None
    
    if user_input.forward_origin:
        origin = user_input.forward_origin
        if origin.type == 'user':
            target_id = origin.sender_user.id
            target_username = origin.sender_user.username or origin.sender_user.first_name
        elif origin.type == 'hidden_user':
            await update.message.reply_text("⚠️ کاربر Hidden است. لطفاً آیدی عددی وارد کنید.")
            return GET_ADMIN_ID
        else:
            await update.message.reply_text("⚠️ این نوع فوروارد پشتیبانی نمی‌شود.")
            return GET_ADMIN_ID
            
    elif user_input.text and user_input.text.isdigit():
        target_id = int(user_input.text)
        target_username = "User"
    else:
        await update.message.reply_text(_("support_panel.management.add_error"))
        return GET_ADMIN_ID

    promoter_name = update.effective_user.first_name
    success = await crud_admin.add_admin(target_id, target_username, promoted_by=promoter_name)
    
    if success:
        await update.message.reply_text(
            _("support_panel.management.add_success", name=target_username or target_id),
            reply_markup=get_settings_and_tools_keyboard() 
        )
        try:
            await context.bot.send_message(target_id, "🎉 شما ادمین شدید. /start بزنید.")
        except:
            pass 
        return ConversationHandler.END
    else:
        await update.message.reply_text(
            _("support_panel.management.add_exists"),
            reply_markup=get_settings_and_tools_keyboard()
        )
        return ConversationHandler.END

async def cancel_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("❌ عملیات لغو شد.", reply_markup=get_settings_and_tools_keyboard())
    return ConversationHandler.END
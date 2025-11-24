# FILE: modules/support_panel/actions.py

import logging
import math
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from shared.translator import _
from database.crud import bot_setting as crud_bot_setting
from database.crud import bot_managed_user as crud_bot_managed_user
from shared import panel_utils
from config import config

# استفاده از ابزارهای نمایش ماژول مرزبان برای هماهنگی ظاهری
from modules.marzban.actions.display import build_users_keyboard
from modules.marzban.actions.constants import USERS_PER_PAGE

LOGGER = logging.getLogger(__name__)

async def show_support_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Displays the Support Admin Dashboard.
    """
    context.user_data.clear()
    
    # ساخت ردیف اول دکمه‌ها (همیشه ثابت)
    row_1 = [
        KeyboardButton(_("keyboards.user_management.add_user")),
        KeyboardButton(_("keyboards.admin_main_menu.search_user"))
    ]
    
    # ردیف دوم: استفاده از ترجمه برای دکمه "کاربران من"
    row_2 = [KeyboardButton(_("keyboards.support_panel.my_users"))]
    
    keyboard = [
        row_1,
        row_2,
        [KeyboardButton(_("keyboards.general.back_to_main_menu"))]
    ]
    
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
    await update.message.reply_text(
        _("support_panel.welcome"),
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )

async def show_my_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Fetches and displays users created by the current support admin.
    """
    user_id = update.effective_user.id
    
    # پیام "لطفا صبر کنید"
    waiting_msg = await update.message.reply_text(_("support_panel.my_users.loading"))

    try:
        # 1. دریافت لیست از دیتابیس
        my_usernames = await crud_bot_managed_user.get_users_created_by(user_id)
        
        if not my_usernames:
            await waiting_msg.edit_text(_("support_panel.my_users.empty"))
            return

        # 2. دریافت اطلاعات زنده از پنل
        all_panel_users = await panel_utils.get_all_users_from_all_panels()
        
        if not all_panel_users:
             await waiting_msg.edit_text(_("marzban_display.panel_connection_error"))
             return

        # 3. فیلتر کردن
        my_usernames_set = set(my_usernames)
        
        my_filtered_users = [
            u for u in all_panel_users 
            if u.get('username') in my_usernames_set
        ]
        
        my_filtered_users.sort(key=lambda u: u.get('username', '').lower())
        
        if not my_filtered_users:
            await waiting_msg.edit_text(_("support_panel.my_users.panel_empty"))
            return

        # 4. ذخیره در user_data
        context.user_data['last_search_results'] = my_filtered_users
        
        # 5. نمایش
        page_users = my_filtered_users[:USERS_PER_PAGE]
        total_pages = math.ceil(len(my_filtered_users) / USERS_PER_PAGE)
        
        keyboard = build_users_keyboard(
            users=page_users, 
            current_page=1, 
            total_pages=total_pages, 
            list_type='myusers' 
        )
        
        title = _("support_panel.my_users.title", count=len(my_filtered_users))
        
        await waiting_msg.delete()
        await update.message.reply_text(title, reply_markup=keyboard)

    except Exception as e:
        LOGGER.error(f"Error fetching my users: {e}", exc_info=True)
        await waiting_msg.edit_text(_("support_panel.my_users.internal_error"))

async def handle_my_users_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles pagination with auto-refetch logic.
    """
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id
    
    try:
        page = int(query.data.split('_')[-1])
    except:
        page = 1
        
    users_list = context.user_data.get('last_search_results', [])
    
    # --- بازیابی خودکار اطلاعات ---
    if not users_list:
        try:
            await query.edit_message_text(_("support_panel.my_users.refreshing"))
        except:
            pass

        try:
            my_usernames = await crud_bot_managed_user.get_users_created_by(user_id)
            if not my_usernames:
                await query.edit_message_text(_("support_panel.my_users.empty"))
                return

            all_panel_users = await panel_utils.get_all_users_from_all_panels()
            if not all_panel_users:
                await query.edit_message_text(_("marzban_display.panel_connection_error"))
                return

            my_usernames_set = set(my_usernames)
            users_list = [
                u for u in all_panel_users 
                if u.get('username') in my_usernames_set
            ]
            users_list.sort(key=lambda u: u.get('username', '').lower())
            
            context.user_data['last_search_results'] = users_list
            
        except Exception as e:
            LOGGER.error(f"Auto-refetch failed: {e}")
            await query.edit_message_text(_("support_panel.my_users.refetch_error"))
            return
    # -----------------------------

    if not users_list:
        await query.edit_message_text(_("support_panel.my_users.not_found"))
        return

    total_pages = math.ceil(len(users_list) / USERS_PER_PAGE)
    if page > total_pages: page = total_pages
    if page < 1: page = 1

    start_idx = (page - 1) * USERS_PER_PAGE
    end_idx = start_idx + USERS_PER_PAGE
    
    page_users = users_list[start_idx:end_idx]
    
    keyboard = build_users_keyboard(
        users=page_users, 
        current_page=page, 
        total_pages=total_pages, 
        list_type='myusers'
    )
    
    title = _("support_panel.my_users.title_page", count=len(users_list), page=page, total=total_pages)

    try:
        await query.edit_message_text(text=title, reply_markup=keyboard)
    except Exception as e:
        LOGGER.warning(f"Pagination edit warning: {e}")
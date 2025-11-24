# FILE: modules/support_panel/keyboards.py

from telegram import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from database.crud import admin as crud_admin
from shared.translator import _

async def get_admin_list_keyboard() -> InlineKeyboardMarkup:
    """
    Creates a dynamic list of admins with an 'Add' button.
    Reads directly from the database.
    """
    admins = await crud_admin.get_all_admins()
    
    keyboard = []
    
    # 1. لیست مدیران موجود
    for admin in admins:
        # اگر نام دارد نامش را نشان بده، اگر نه آیدی عددی
        display_name = f"👤 {admin.username}" if admin.username else f"👤 {admin.user_id}"
        # پترن کال‌بک: detail + user_id
        callback_data = f"admin_manage_detail_{admin.user_id}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])
    
    # 2. دکمه افزودن مدیر جدید
    keyboard.append([InlineKeyboardButton(_("support_panel.management.btn_add_admin"), callback_data="admin_manage_add")])
    
    # 3. دکمه بازگشت (به منوی تنظیمات اصلی برمی‌گردد)
    keyboard.append([InlineKeyboardButton(_("support_panel.management.btn_back"), callback_data="bot_status_back")])
    
    return InlineKeyboardMarkup(keyboard)

def get_admin_detail_keyboard(target_user_id: int) -> InlineKeyboardMarkup:
    """
    Control buttons for a specific admin (Delete / Back).
    """
    keyboard = [
        [InlineKeyboardButton(_("support_panel.management.btn_delete"), callback_data=f"admin_manage_delete_{target_user_id}")],
        [InlineKeyboardButton(_("support_panel.management.btn_back_to_list"), callback_data="admin_manage_list")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_add_admin_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Cancel button for the conversation."""
    # فرض بر این است که کلید عمومی 'cancel' یا 'back' در فایل‌های ترجمه اصلی دارید.
    # اگر ندارید، متن هاردکد شده "انصراف" را می‌گذاریم.
    return ReplyKeyboardMarkup(
        [[KeyboardButton("/cancel")]], 
        resize_keyboard=True, 
        one_time_keyboard=True
    )
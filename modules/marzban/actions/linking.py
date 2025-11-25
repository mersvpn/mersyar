# FILE: modules/marzban/actions/linking.py

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from shared.translator import _
from database.crud import marzban_link as crud_marzban_link
from shared.keyboards import get_back_to_main_menu_keyboard
from modules.marzban.actions.display import show_user_details_panel
from shared.panel_utils import get_user_data_from_panels as get_user_data
from config import config

# وضعیت مکالمه
GET_CUSTOMER_ID = 0

# ============================================================================
#  بخش جدید: اتصال سرویس به مشتری (توسط دکمه در پنل)
# ============================================================================

async def start_linking_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Start the linking process when 'Connect to Customer' button is clicked.
    """
    query = update.callback_query
    await query.answer()
    
    # استخراج نام کاربری از کالبک link_customer_{username}
    try:
        username = query.data.split('_', 2)[2]
    except IndexError:
        await query.edit_message_text("❌ خطا در خواندن نام کاربری.")
        return ConversationHandler.END

    context.user_data['linking_username'] = username
    
    # ذخیره اطلاعات برای بازگشت صحیح
    context.user_data['linking_return_info'] = {
        'chat_id': query.message.chat_id,
        'message_id': query.message.message_id,
        'list_type': context.user_data.get('current_list_type', 'all'),
        'page_number': context.user_data.get('current_page', 1)
    }

    await query.message.delete()
    
    msg_text = (
        f"🔗 **اتصال سرویس `{username}` به مشتری**\n\n"
        "لطفاً یکی از کارهای زیر را انجام دهید:\n"
        "1️⃣ یک پیام از مشتری را به اینجا **فوروارد (Forward)** کنید.\n"
        "2️⃣ یا **آیدی عددی (User ID)** مشتری را ارسال کنید.\n\n"
        "(برای انصراف دکمه بازگشت را بزنید)"
    )
    
    # نمایش پیام + کیبورد بازگشت بزرگ
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=msg_text,
        reply_markup=get_back_to_main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    
    return GET_CUSTOMER_ID

async def process_linking_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Processes the forwarded message or text ID to link the user.
    """
    target_id = None
    user_input = update.message
    username = context.user_data.get('linking_username')
    
    if not username:
        await update.message.reply_text("❌ خطای نشست (Session). لطفاً دوباره از لیست انتخاب کنید.")
        return ConversationHandler.END

    # --- 1. تشخیص آیدی مشتری ---
    if user_input.forward_origin:
        origin = user_input.forward_origin
        if origin.type == 'user':
            target_id = origin.sender_user.id
        elif origin.type == 'hidden_user':
            await update.message.reply_text("⚠️ کاربر پروفایل خود را بسته است (Hidden). لطفاً آیدی عددی را دستی وارد کنید.")
            return GET_CUSTOMER_ID
    elif user_input.text and user_input.text.isdigit():
        target_id = int(user_input.text)
    else:
        await update.message.reply_text("❌ ورودی نامعتبر. لطفاً یک پیام فوروارد کنید یا آیدی عددی بفرستید.")
        return GET_CUSTOMER_ID
    # ---------------------------

    # --- 2. ذخیره در دیتابیس ---
    # پنل آیدی را از کانتکست می‌گیریم (که در display.py ست شده)
    panel_id = context.user_data.get('selected_panel_id')
    
    # اگر پنل آیدی نبود (محض احتیاط)، سعی می‌کنیم اتوماتیک پیدا کنیم (توسط متد لینک)
    # اما اینجا فرض می‌کنیم هست.
    await crud_marzban_link.create_or_update_link(
        marzban_username=username,
        telegram_user_id=target_id,
        panel_id=panel_id
    )
    
    # --- 3. پیام موفقیت ---
    await update.message.reply_text(
        f"✅ سرویس `{username}` با موفقیت به مشتری با آیدی `{target_id}` متصل شد.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # (اختیاری) پیام خوش‌آمد به مشتری
    try:
        await context.bot.send_message(
            chat_id=target_id,
            text=f"🎉 تبریک! سرویس **{username}** به حساب شما متصل شد.\nمی‌توانید از بخش «سرویس‌های من» وضعیت آن را مشاهده کنید.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass # شاید مشتری ربات را استارت نکرده باشد

    # --- 4. بازگشت به پنل جزئیات ---
    return_info = context.user_data.get('linking_return_info', {})
    
    await show_user_details_panel(
        context=context,
        chat_id=update.effective_chat.id,
        username=username,
        list_type=return_info.get('list_type', 'all'),
        page_number=return_info.get('page_number', 1),
        message_id=None # پیام جدید بفرست
    )
    
    # اگر پشتیبان است، منوی دکمه‌ای پشتیبانی را هم برگردان
    if update.effective_user.id not in config.AUTHORIZED_USER_IDS:
         from modules.support_panel.actions import show_support_menu
         await show_support_menu(update, context)

    return ConversationHandler.END

async def cancel_linking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancels the operation."""
    await update.message.reply_text("❌ عملیات لغو شد.")
    
    # بازگرداندن منوی صحیح
    if update.effective_user.id not in config.AUTHORIZED_USER_IDS:
         from modules.support_panel.actions import show_support_menu
         await show_support_menu(update, context)
    else:
        from shared.keyboards import get_user_management_keyboard
        await update.message.reply_text("منوی مدیریت:", reply_markup=get_user_management_keyboard())
        
    return ConversationHandler.END


# ============================================================================
#  بخش موجود (حفظ شده): ارسال لینک اشتراک
# ============================================================================

async def send_subscription_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles the 'Subscription Link' button click.
    """
    query = update.callback_query
    await query.answer()
    
    username = query.data.split('_', 2)[-1]
    
    await query.edit_message_text(f"⏳ در حال دریافت لینک اشتراک برای `{username}`...", parse_mode=ParseMode.MARKDOWN)
    
    user_data = await get_user_data(username)
    sub_url = user_data.get('subscription_url') if user_data else None
    
    list_type = context.user_data.get('current_list_type', 'all')
    page_number = context.user_data.get('current_page', 1)
    # اصلاح منطق دکمه بازگشت برای پشتیبان
    if list_type == 'myusers':
        back_callback = f"user_details_{username}_{list_type}_{page_number}"
    else:
        # پنل آیدی هم برای جستجو لازم است اگر باشد
        panel_id = context.user_data.get('selected_panel_id', 0)
        back_callback = f"user_details_{username}_{list_type}_{page_number}_{panel_id}"

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 بازگشت به جزئیات", callback_data=back_callback)]
    ])

    if not sub_url:
        await query.edit_message_text(f"❌ لینک اشتراک یافت نشد.", reply_markup=keyboard)
        return

    message = (
        f"🔗 **لینک اشتراک کاربر:** `{username}`\n\n"
        f"`{sub_url}`"
    )
    
    await query.edit_message_text(message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
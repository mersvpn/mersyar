# --- START OF FILE modules/reminder/actions/daily_note.py ---
import logging
import uuid
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    filters, CallbackQueryHandler, CommandHandler
)
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from database.crud import admin_daily_note as crud_daily_note
from shared.keyboards import get_settings_and_tools_keyboard

LOGGER = logging.getLogger(__name__)

(
    MAIN_MENU, LIST_NOTES, VIEW_NOTE,
    ADD_GET_TITLE, ADD_GET_TEXT, CONFIRM_DELETE,
    EDIT_CHOICE, EDIT_GET_TITLE, EDIT_GET_TEXT
) = range(9)


async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    is_entry = update.message is not None

    keyboard = [
        [
            InlineKeyboardButton("➕ افزودن یادداشت جدید", callback_data="dnote_add_prompt"),
            InlineKeyboardButton(" L️ لیست یادداشت‌ها", callback_data="dnote_list_prompt")
        ],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="cancel_conv")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "🗒️ **مدیریت یادداشت‌های روزانه**\n\nلطفاً یک گزینه را انتخاب کنید."

    if is_entry:
        if update.message:
            await update.message.delete()
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
        context.user_data['main_menu_message'] = sent_message
    else:
        await update.callback_query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )

    return MAIN_MENU


async def _build_list_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    notes = await crud_daily_note.get_all_daily_notes()
    keyboard = []
    text = " L️ **لیست یادداشت‌ها**\n\n"

    if not notes:
        text += "هیچ یادداشتی برای نمایش وجود ندارد."
    else:
        text += "برای مشاهده، ویرایش یا حذف، روی عنوان کلیک کنید."
        for note in notes:
            keyboard.append([InlineKeyboardButton(note.title or "بدون عنوان", callback_data=f"dnote_view_{note.id}")])
    
    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منو", callback_data="dnote_main_menu_prompt")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)


async def _build_view_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note_id = context.user_data.get('current_note_id')
    note_to_show = await crud_daily_note.get_daily_note_by_id(note_id)

    if not note_to_show:
        await update.callback_query.answer("خطا: یادداشت یافت نشد.", show_alert=True)
        await _build_list_message(update, context)
        return LIST_NOTES

    title = escape_markdown(note_to_show.title or '')
    body = escape_markdown(note_to_show.text or '')
    text = f"**عنوان:** {title}\n\n**متن:**\n{body}"
    keyboard = [
        [
            InlineKeyboardButton("✏️ ویرایش", callback_data="dnote_edit_prompt"),
            InlineKeyboardButton("🗑️ حذف", callback_data="dnote_delete_prompt")
        ],
        [InlineKeyboardButton("🔙 بازگشت به لیست", callback_data="dnote_list_prompt")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    return VIEW_NOTE


async def list_notes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await _build_list_message(update, context)
    return LIST_NOTES


async def view_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data['current_note_id'] = update.callback_query.data.split('_')[-1]
    return await _build_view_message(update, context)


async def add_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("۱/۲ - لطفاً **عنوان** یادداشت را وارد کنید.\n\nبرای لغو /cancel را ارسال کنید.")
    return ADD_GET_TITLE


async def add_get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_note_title'] = update.message.text
    await update.message.reply_text("✅ عنوان ذخیره شد.\n\n۲/۲ - لطفاً **متن کامل** یادداشت را وارد کنید.\n\nبرای لغو /cancel را ارسال کنید.")
    return ADD_GET_TEXT


async def add_get_text_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note_id = str(uuid.uuid4())
    title = context.user_data.pop('new_note_title', 'Untitled')
    text = update.message.text
    await crud_daily_note.add_daily_note({'id': note_id, 'title': title, 'text': text})
    
    await update.message.reply_text("✅ یادداشت جدید با موفقیت ذخیره شد.", reply_markup=get_settings_and_tools_keyboard())
    
    if 'main_menu_message' in context.user_data:
        try:
            await context.user_data['main_menu_message'].delete()
        except Exception:
            pass
    
    context.user_data.clear()
    return ConversationHandler.END


async def delete_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    keyboard = [
        [InlineKeyboardButton("✅ بله، حذف کن", callback_data="dnote_delete_confirm")],
        [InlineKeyboardButton("❌ خیر", callback_data=f"dnote_view_{context.user_data['current_note_id']}")]
    ]
    await update.callback_query.edit_message_text("آیا از حذف این یادداشت اطمینان دارید؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_DELETE


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note_id = context.user_data.pop('current_note_id')
    await crud_daily_note.delete_daily_note_by_id(note_id)
    await update.callback_query.answer("یادداشت حذف شد.")
    return await list_notes(update, context)


async def edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    keyboard = [
        [
            InlineKeyboardButton("ویرایش عنوان", callback_data="dnote_edit_title"),
            InlineKeyboardButton("ویرایش متن", callback_data="dnote_edit_text")
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data=f"dnote_view_{context.user_data['current_note_id']}")]
    ]
    await update.callback_query.edit_message_text("کدام بخش را ویرایش می‌کنید؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return EDIT_CHOICE


async def edit_get_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data['edit_field'] = 'title'
    await update.callback_query.edit_message_text("لطفاً **عنوان** جدید را وارد کنید.\n\nبرای لغو /cancel را ارسال کنید.")
    return EDIT_GET_TITLE


async def edit_get_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.callback_query.answer()
    context.user_data['edit_field'] = 'text'
    await update.callback_query.edit_message_text("لطفاً **متن** جدید را وارد کنید.\n\nبرای لغو /cancel را ارسال کنید.")
    return EDIT_GET_TEXT


async def edit_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    note_id = context.user_data.get('current_note_id')
    field_to_edit = context.user_data.pop('edit_field', None)
    
    if not note_id or not field_to_edit:
        await update.message.reply_text("خطا: اطلاعات ویرایش یافت نشد.")
        return await main_menu(update, context)

    update_data = {field_to_edit: update.message.text}
    success = await crud_daily_note.update_daily_note(note_id, update_data)

    if success:
        await update.message.reply_text("✅ یادداشت با موفقیت ویرایش شد.")
    else:
        await update.message.reply_text("خطا: یادداشت برای ویرایش یافت نشد.")
    
    dummy_update = Update(update.update_id, callback_query=update.callback_query)
    # The callback_query object needs to be constructed correctly for _build_view_message
    if dummy_update.callback_query:
        dummy_update.callback_query.message = update.message

    return await _build_view_message(dummy_update, context)


daily_notes_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex('^🗒️ یادداشت‌های روزانه$'), main_menu)],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(add_prompt, pattern='^dnote_add_prompt$'),
            CallbackQueryHandler(list_notes, pattern='^dnote_list_prompt$'),
        ],
        ADD_GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_title)],
        ADD_GET_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_get_text_and_save)],
        LIST_NOTES: [
            CallbackQueryHandler(view_note, pattern=r'^dnote_view_'),
            CallbackQueryHandler(main_menu, pattern='^dnote_main_menu_prompt$'),
        ],
        VIEW_NOTE: [
            CallbackQueryHandler(edit_prompt, pattern='^dnote_edit_prompt$'),
            CallbackQueryHandler(delete_prompt, pattern='^dnote_delete_prompt$'),
            CallbackQueryHandler(list_notes, pattern='^dnote_list_prompt$'),
        ],
        CONFIRM_DELETE: [
            CallbackQueryHandler(delete_confirm, pattern='^dnote_delete_confirm$'),
            CallbackQueryHandler(view_note, pattern=r'^dnote_view_'),
        ],
        EDIT_CHOICE: [
            CallbackQueryHandler(edit_get_title, pattern='^dnote_edit_title$'),
            CallbackQueryHandler(edit_get_text, pattern='^dnote_edit_text$'),
            CallbackQueryHandler(view_note, pattern=r'^dnote_view_'),
        ],
        EDIT_GET_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
        EDIT_GET_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_save)],
    },
    fallbacks=[

    ],
    conversation_timeout=600,
    per_user=True,
    per_chat=True
)
# --- END OF FILE modules/reminder/actions/daily_note.py ---
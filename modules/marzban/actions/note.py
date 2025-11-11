# --- START OF FILE modules/marzban/actions/note.py (REVISED) ---
import math
import logging
from decimal import Decimal
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

from .data_manager import normalize_username
from shared.keyboards import get_user_management_keyboard
from shared import panel_utils
from database.crud import user_note as crud_user_note

LOGGER = logging.getLogger(__name__)

GET_DURATION, GET_DATA_LIMIT, GET_PRICE = range(3)
USERS_PER_PAGE = 10

async def prompt_for_note_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    LOGGER.critical("!!!!!! [NOTE DEBUG] Entering prompt_for_note_details (Step 1) !!!!!!")
    from shared.translator import _

    query = update.callback_query
    await query.answer()
    username = normalize_username(query.data.split('_', 1)[1])
    context.user_data['note_username'] = username
    context.user_data['note_details'] = {}
    
    current_note = await crud_user_note.get_user_note(username)
    undefined_str = _("marzban.marzban_note.undefined")
    
    current_duration = current_note.subscription_duration if current_note and current_note.subscription_duration is not None else undefined_str
    current_datalimit = current_note.subscription_data_limit_gb if current_note and current_note.subscription_data_limit_gb is not None else undefined_str
    current_price = f"{current_note.subscription_price:,}" if current_note and current_note.subscription_price is not None else undefined_str
    username_md = escape_markdown(username, version=2)

    message = _("marzban.marzban_note.title", username=username_md)
    message += _("marzban.marzban_note.current_duration", duration=current_duration)
    message += _("marzban.marzban_note.current_datalimit", datalimit=current_datalimit)
    message += _("marzban.marzban_note.current_price", price=current_price)
    message += _("marzban.marzban_note.step1_ask_duration")

    keyboard = []
    if current_note and any([current_note.subscription_duration, current_note.subscription_data_limit_gb, current_note.subscription_price]):
        keyboard.append([InlineKeyboardButton(_("marzban.marzban_note.button_delete_note"), callback_data=f"delete_note_{username}")])

    await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None, parse_mode=ParseMode.MARKDOWN_V2)
    return GET_DURATION

async def get_duration_and_ask_for_data_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    LOGGER.critical("!!!!!! [NOTE DEBUG] Entering get_duration_and_ask_for_data_limit (Step 2) !!!!!!")
    from shared.translator import _
    try:
        duration = int(update.message.text)
        if duration <= 0:
            await update.message.reply_text(_("marzban.marzban_note.duration_must_be_positive")); return GET_DURATION
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban.marzban_note.invalid_number_input")); return GET_DURATION
        
    context.user_data['note_details']['duration'] = duration
    message = _("marzban.marzban_note.duration_saved", duration=duration) + _("marzban.marzban_note.step2_ask_datalimit")
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    return GET_DATA_LIMIT

async def get_data_limit_and_ask_for_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        data_limit = int(update.message.text)
        if data_limit < 0:
            await update.message.reply_text(_("marzban.marzban_note.datalimit_cannot_be_negative")); return GET_DATA_LIMIT
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban.marzban_note.invalid_number_input")); return GET_DATA_LIMIT
        
    context.user_data['note_details']['data_limit_gb'] = data_limit
    message = _("marzban.marzban_note.datalimit_saved", datalimit=data_limit) + _("marzban.marzban_note.step3_ask_price")
    await update.message.reply_text(message, parse_mode=ParseMode.HTML)
    return GET_PRICE

async def get_price_and_save_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from modules.general.actions import end_conversation_and_show_menu
    from shared.translator import _
    
    username = context.user_data.get('note_username')
    if not username: return await end_conversation_and_show_menu(update, context)
    
    try:
        price = int(update.message.text)
        if price < 0:
            await update.message.reply_text(_("marzban.marzban_note.price_cannot_be_negative")); return GET_PRICE
    except (ValueError, TypeError):
        await update.message.reply_text(_("marzban.marzban_note.invalid_number_input")); return GET_PRICE
        
    note_details = context.user_data.get('note_details', {})
    await crud_user_note.create_or_update_user_note(
        marzban_username=username,
        price=Decimal(price),
        duration=note_details.get('duration'),
        data_limit_gb=note_details.get('data_limit_gb')
    )
    await update.message.reply_text(
        _("marzban.marzban_note.note_saved_successfully", username=f"`{username}`"), 
        parse_mode=ParseMode.MARKDOWN, reply_markup=get_user_management_keyboard()
    )
    context.user_data.clear()
    return ConversationHandler.END

async def delete_note_from_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    
    query = update.callback_query
    await query.answer(_("marzban.marzban_note.note_deleted_successfully"), show_alert=True)
    username = normalize_username(query.data.split('_', 2)[2])
    
    await crud_user_note.delete_user_note(username)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(_("marzban.marzban_display.back_to_subs_list"), callback_data="list_subs_page_1")]
    ])
    await query.edit_message_text(
        _("marzban.marzban_note.note_deleted_message", username=f"`{username}`"),
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )
    context.user_data.clear()
    return ConversationHandler.END

async def list_users_with_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    
    query = update.callback_query
    page = 1
    
    if query:
        await query.answer()
        if query.data.startswith('list_subs_page_'): page = int(query.data.split('_')[-1])
        message_to_edit = query.message
    else:
        message_to_edit = await update.message.reply_text(_("marzban.marzban_note.loading_subscriptions"))

    all_notes_obj = await crud_user_note.get_all_users_with_notes()
    marzban_users = await panel_utils.get_all_users_from_all_panels()
    
    if marzban_users is None:
        await message_to_edit.edit_text(_("marzban.marzban_display.panel_connection_error")); return
        
    marzban_usernames = {normalize_username(u['username']) for u in marzban_users if u.get('username')}
    valid_notes = sorted(
        [note for note in all_notes_obj if normalize_username(note.username) in marzban_usernames],
        key=lambda x: x.username.lower()
    )

    if not valid_notes:
        await message_to_edit.edit_text(_("marzban.marzban_note.no_active_subscriptions")); return

    total_pages = math.ceil(len(valid_notes) / USERS_PER_PAGE)
    page = max(1, min(page, total_pages))
    page_notes = valid_notes[(page - 1) * USERS_PER_PAGE : page * USERS_PER_PAGE]

    keyboard_rows = []
    it = iter(page_notes)
    for note1 in it:
        row = [InlineKeyboardButton(_("marzban.marzban_note.button_user_prefix", username=note1.username), callback_data=f"user_details_{note1.username}_subs_{page}")]
        try:
            note2 = next(it)
            row.append(InlineKeyboardButton(_("marzban.marzban_note.button_user_prefix", username=note2.username), callback_data=f"user_details_{note2.username}_subs_{page}"))
        except StopIteration:
            pass
        keyboard_rows.append(row)

    nav_row = []
    if page > 1: nav_row.append(InlineKeyboardButton(_("marzban.marzban_display.pagination_prev"), callback_data=f"list_subs_page_{page - 1}"))
    if total_pages > 1: nav_row.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages: nav_row.append(InlineKeyboardButton(_("marzban.marzban_display.pagination_next"), callback_data=f"list_subs_page_{page + 1}"))
    if nav_row: keyboard_rows.append(nav_row)
    keyboard_rows.append([InlineKeyboardButton(_("marzban.marzban_display.pagination_close"), callback_data="close_pagination")])
    
    message_parts = [_("marzban.marzban_note.subscriptions_list_title")]
    undefined_str = _("marzban.marzban_note.undefined")
    for note in page_notes:
        price = note.subscription_price
        line = _("marzban.marzban_note.subscription_list_item", 
                username=note.username,
                duration=note.subscription_duration or undefined_str,
                datalimit=note.subscription_data_limit_gb or undefined_str,
                price=f"{price:,}" if price is not None else undefined_str)
        message_parts.append(line)

    await message_to_edit.edit_text("\n\n".join(message_parts), reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode=ParseMode.MARKDOWN)

# --- END OF FILE modules/marzban/actions/note.py (REVISED) ---
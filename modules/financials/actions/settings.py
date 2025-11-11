# --- START OF FILE modules/financials/actions/settings.py ---
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, MessageHandler,
    CallbackQueryHandler, CommandHandler, filters
)
from telegram.constants import ParseMode

from database.crud import financial_setting as crud_financial
from database.crud import bot_setting as crud_bot_setting
from shared.keyboards import get_financial_settings_keyboard, get_payment_methods_keyboard, get_plan_management_keyboard

from shared.auth import admin_only

LOGGER = logging.getLogger(__name__)

(CARD_MENU, EDITING_HOLDER, EDITING_CARD) = range(3)
(PLAN_NAME_MENU, EDITING_VOLUMETRIC_NAME, EDITING_UNLIMITED_NAME) = range(3, 6)


@admin_only
async def show_financial_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, query_to_use=None) -> None:
    from shared.translator import _
    text = _("financials_settings.main_menu_title_inline")
    
    query = query_to_use or update.callback_query

    if query:
        context.user_data['financial_menu_query'] = query

    bot_settings = await crud_bot_setting.load_bot_settings()
    is_wallet_enabled = bot_settings.get('is_wallet_enabled', False)
    
    keyboard_rows = [
        [
            InlineKeyboardButton(_("financials_settings.button_payment_settings"), callback_data="show_payment_methods"),
            InlineKeyboardButton(_("financials_settings.button_plan_management"), callback_data="show_plan_management")
        ]
    ]

    if is_wallet_enabled:
        keyboard_rows.append([
            InlineKeyboardButton(_("financials_settings.button_wallet_settings"), callback_data="admin_wallet_settings"),
            InlineKeyboardButton(_("financials_settings.button_gift_management"), callback_data="admin_gift_management")
        ])
        keyboard_rows.append([
            InlineKeyboardButton(_("financials_settings.button_balance_management"), callback_data="admin_manage_balance")
        ])

    keyboard_rows.append(
        [InlineKeyboardButton(_("financials_settings.button_back_to_settings"), callback_data="back_to_main_settings")]
    )
    
    keyboard = InlineKeyboardMarkup(keyboard_rows)

    if query:
        await query.answer()
        await query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        if update.message: await update.message.delete()
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard)


@admin_only
async def show_payment_methods_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    text = _("financials_settings.payment_methods_title")
    keyboard = get_payment_methods_keyboard()
    
    target_message = update.message or (update.callback_query.message if update.callback_query else None)
    if not target_message: return

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await target_message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def show_plan_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    text = _("financials_settings.plan_management_title")
    keyboard = get_plan_management_keyboard()
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    else:
        await update.message.reply_text(text=text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


async def format_financial_info_message() -> str:
    from shared.translator import _
    financials = await crud_financial.load_financial_settings()
    not_set_str = _("marzban_credentials.not_set")
    
    card_holder = not_set_str
    card_number = not_set_str
    if financials:
        card_holder = financials.card_holder or not_set_str
        card_number = financials.card_number or not_set_str
    
    message = _("financials_settings.card_settings_title")
    message += _("financials_settings.card_holder_label", holder=card_holder)
    message += _("financials_settings.card_number_label", number=card_number)
    message += _("financials_settings.card_menu_prompt")
    return message


def build_card_menu_keyboard():
    from shared.translator import _
    keyboard = [[
        InlineKeyboardButton(_("financials_settings.button_edit_holder"), callback_data="fin_edit_holder"),
        InlineKeyboardButton(_("financials_settings.button_edit_card"), callback_data="fin_edit_card")
    ],[InlineKeyboardButton(_("financials_settings.button_back_to_payment_methods"), callback_data="back_to_payment_methods")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_card_settings_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    message_text = await format_financial_info_message()
    keyboard = build_card_menu_keyboard()
    await query.edit_message_text(text=message_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
    return CARD_MENU


async def prompt_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    action = query.data.split('_')[-1]
    context.user_data['financial_action'] = action
    
    if action == 'holder':
        prompt_text = _("financials_settings.prompt_edit_holder")
        next_state = EDITING_HOLDER
    elif action == 'card':
        prompt_text = _("financials_settings.prompt_edit_card")
        next_state = EDITING_CARD
    else:
        return CARD_MENU
        
    await query.edit_message_text(text=prompt_text)
    return next_state


async def save_financial_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from modules.general.actions import end_conversation_and_show_menu
    from shared.translator import _
    action = context.user_data.get('financial_action')
    new_value = update.message.text.strip()
    if not action:
        await update.message.reply_text(_("financials_settings.error_unknown_action"))
        return await end_conversation_and_show_menu(update, context)
        
    settings_to_save = {}
    if action == 'holder':
        settings_to_save['card_holder'] = new_value
        confirmation_text = _("financials_settings.holder_updated_success")
    elif action == 'card':
        card_number = "".join(filter(str.isdigit, new_value))
        if len(card_number) != 16:
            await update.message.reply_text(_("financials_settings.invalid_card_number"))
            return EDITING_CARD
        settings_to_save['card_number'] = card_number
        confirmation_text = _("financials_settings.card_updated_success")
        
    await crud_financial.save_financial_settings(settings_to_save)
    await update.message.reply_text(confirmation_text)
    context.user_data.pop('financial_action', None)
    await show_payment_methods_menu(update, context)
    return ConversationHandler.END


card_settings_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_card_settings_conv, pattern=r'^admin_set_card_info$')],
    states={
        CARD_MENU: [
            CallbackQueryHandler(prompt_for_edit, pattern=r'^fin_edit_'),
            CallbackQueryHandler(show_payment_methods_menu, pattern=r'^back_to_payment_methods$'),
        ],
        EDITING_HOLDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_financial_info)],
        EDITING_CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_financial_info)],
    },
    fallbacks=[],
    conversation_timeout=300, block=False
)


async def show_plan_name_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()

    settings = await crud_bot_setting.load_bot_settings()
    vol_name = settings.get("volumetric_plan_button_text", "♻️ اشتراک با حجم دلخواه")
    unl_name = settings.get("unlimited_plan_button_text", "💎 اشتراک با حجم نامحدود")

    text = _("financials_settings.plan_names_title")
    text += _("financials_settings.plan_names_description")
    text += _("financials_settings.volumetric_plan_name_label", name=f"`{vol_name}`")
    text += _("financials_settings.unlimited_plan_name_label", name=f"`{unl_name}`")

    keyboard = [[
        InlineKeyboardButton(_("financials_settings.button_edit_volumetric_name"), callback_data="set_name_volumetric"),
        InlineKeyboardButton(_("financials_settings.button_edit_unlimited_name"), callback_data="set_name_unlimited")
    ],[InlineKeyboardButton(_("financials_settings.button_back_to_payment_methods"), callback_data="back_to_plan_management")]]
    
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return PLAN_NAME_MENU


async def prompt_for_new_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    action = query.data.split('_')[-1]
    context.user_data['plan_name_to_edit'] = action
    
    if action == 'volumetric':
        prompt_text = _("financials_settings.prompt_edit_volumetric_name")
        next_state = EDITING_VOLUMETRIC_NAME
    else:
        prompt_text = _("financials_settings.prompt_edit_unlimited_name")
        next_state = EDITING_UNLIMITED_NAME
        
    await query.answer()
    await query.edit_message_text(text=prompt_text, parse_mode=ParseMode.MARKDOWN)
    return next_state


async def save_new_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from modules.general.actions import end_conversation_and_show_menu
    from shared.translator import _
    new_name = update.message.text.strip()
    action = context.user_data.pop('plan_name_to_edit', None)

    if not action:
        await update.message.reply_text(_("financials_settings.error_unknown_action"))
        return await end_conversation_and_show_menu(update, context)

    key_to_save = "volumetric_plan_button_text" if action == 'volumetric' else "unlimited_plan_button_text"
    await crud_bot_setting.save_bot_settings({key_to_save: new_name})
    
    await update.message.reply_text(_("financials_settings.plan_name_updated_success", name=new_name))
    
    await show_plan_management_menu(update, context)
    return ConversationHandler.END


plan_name_settings_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(show_plan_name_settings_menu, pattern='^admin_set_plan_names$')],
    states={
        PLAN_NAME_MENU: [
            CallbackQueryHandler(prompt_for_new_name, pattern=r'^set_name_'),
            CallbackQueryHandler(show_plan_management_menu, pattern=r'^back_to_plan_management$')
        ],
        EDITING_VOLUMETRIC_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_plan_name)],
        EDITING_UNLIMITED_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_plan_name)],
    },
    fallbacks=[],
    conversation_timeout=300
)


async def back_to_main_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.keyboards import get_settings_and_tools_keyboard
    from shared.translator import _

    query = update.callback_query
    await query.answer()
    
    await query.message.delete()
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_("financials_settings.back_to_main_settings_text"),
        reply_markup=get_settings_and_tools_keyboard()
    )

# --- END OF FILE modules/financials/actions/settings.py ---
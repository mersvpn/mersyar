# --- START OF FILE modules/financials/actions/volumetric_plans_admin.py ---
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, CommandHandler, filters
)
from telegram.constants import ParseMode

from database.crud import volumetric_tier as crud_volumetric
from database.crud import financial_setting as crud_financial
from .settings import show_plan_management_menu


LOGGER = logging.getLogger(__name__)

GET_BASE_PRICE = 0
GET_TIER_NAME, GET_TIER_LIMIT, GET_TIER_PRICE, CONFIRM_TIER_ADD = range(1, 5)
EDIT_TIER_NAME, EDIT_TIER_LIMIT, EDIT_TIER_PRICE, CONFIRM_TIER_EDIT = range(5, 9)

async def manage_volumetric_plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    await query.answer()

    financial_settings = await crud_financial.load_financial_settings()
    base_price = financial_settings.base_daily_price if financial_settings else None
    tiers = await crud_volumetric.get_all_pricing_tiers()

    text = _("financials_volumetric.menu_title")
    keyboard_rows = []

    base_price_str = _("financials_volumetric.price_toman", price=base_price) if base_price is not None else _("financials_volumetric.not_set")
    text += _("financials_volumetric.base_price_section", price=base_price_str)
    keyboard_rows.append([InlineKeyboardButton(_("financials_volumetric.button_edit_base_price"), callback_data="vol_edit_base_price")])
    keyboard_rows.append([InlineKeyboardButton(" ", callback_data="noop")])

    text += _("financials_volumetric.tiers_section_title")
    if not tiers:
        text += _("financials_volumetric.no_tiers_defined")
    else:
        for tier in tiers:
            tier_text = _("financials_volumetric.tier_list_item", limit=tier.volume_limit_gb, price=f"{tier.price_per_gb:,}")
            keyboard_rows.append([InlineKeyboardButton(tier_text, callback_data=f"vol_noop_{tier.id}")])
            action_buttons = [
                InlineKeyboardButton(_("financials_volumetric.button_edit"), callback_data=f"vol_edit_tier_{tier.id}"),
                InlineKeyboardButton(_("financials_volumetric.button_delete"), callback_data=f"vol_delete_tier_{tier.id}")
            ]
            keyboard_rows.append(action_buttons)
    
    keyboard_rows.append([InlineKeyboardButton(" ", callback_data="noop")])
    keyboard_rows.append([InlineKeyboardButton(_("financials_volumetric.button_add_new_tier"), callback_data="vol_add_tier")])
    keyboard_rows.append([InlineKeyboardButton(_("financials_settings.button_back_to_payment_methods"), callback_data="back_to_plan_management")])
    
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode=ParseMode.MARKDOWN)

async def prompt_for_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    text = _("financials_volumetric.prompt_edit_base_price")
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_BASE_PRICE

async def save_new_base_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        price = int(update.message.text.strip())
        if price < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_volumetric.invalid_positive_number"))
        return GET_BASE_PRICE
    
    await crud_financial.save_financial_settings({'base_daily_price': price})
    await update.message.reply_text(_("financials_volumetric.base_price_updated_success", price=_("financials_volumetric.price_toman", price=price)))
    
    await show_plan_management_menu(update, context)
    return ConversationHandler.END

async def start_add_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    context.user_data['new_tier'] = {}
    text = _("financials_volumetric.add_tier_title") + _("financials_volumetric.step1_ask_name")
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_TIER_NAME

async def get_tier_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    context.user_data['new_tier']['tier_name'] = update.message.text.strip()
    text = _("financials_volumetric.step2_ask_limit")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_TIER_LIMIT

async def get_tier_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        limit = int(update.message.text.strip())
        if limit <= 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_volumetric.invalid_limit"))
        return GET_TIER_LIMIT
    
    context.user_data['new_tier']['volume_limit_gb'] = limit
    text = _("financials_volumetric.step3_ask_price")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_TIER_PRICE

async def get_tier_price_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        price = int(update.message.text.strip())
        if price < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_unlimited.invalid_price"))
        return GET_TIER_PRICE

    context.user_data['new_tier']['price_per_gb'] = price
    tier_data = context.user_data['new_tier']
    
    text = _("financials_volumetric.confirm_prompt_title")
    text += _("financials_volumetric.confirm_name", name=tier_data['tier_name'])
    text += _("financials_volumetric.confirm_limit", limit=tier_data['volume_limit_gb'])
    text += _("financials_volumetric.confirm_price", price=f"{tier_data['price_per_gb']:,}")
    text += _("financials_volumetric.confirm_prompt_question")

    keyboard = [[
        InlineKeyboardButton(_("financials_unlimited.button_confirm_save"), callback_data="vol_confirm_add"),
        InlineKeyboardButton(_("financials_unlimited.button_cancel_add"), callback_data="vol_cancel_add")
    ]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_TIER_ADD

async def save_new_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer(_("financials_volumetric.saving"))
    tier_data = context.user_data.pop('new_tier', {})
    
    await crud_volumetric.add_pricing_tier(tier_data)
    await query.edit_message_text(_("financials_volumetric.add_success"))
    await manage_volumetric_plans_menu(update, context)
    return ConversationHandler.END

async def cancel_add_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    context.user_data.pop('new_tier', None)
    await query.edit_message_text(_("financials_volumetric.add_cancelled"))
    await manage_volumetric_plans_menu(update, context)
    return ConversationHandler.END

async def start_edit_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    tier_id = int(query.data.split('_')[-1])
    tier = await crud_volumetric.get_pricing_tier_by_id(tier_id)
    if not tier:
        await query.answer(_("financials_unlimited.plan_not_found"), show_alert=True)
        return ConversationHandler.END

    context.user_data['edit_tier'] = {
        'id': tier.id,
        'tier_name': tier.tier_name,
        'volume_limit_gb': tier.volume_limit_gb,
        'price_per_gb': tier.price_per_gb
    }
    await query.answer()
    
    text = _("financials_volumetric.edit_tier_title", name=tier.tier_name)
    text += _("financials_volumetric.current_value", value=tier.tier_name)
    text += _("financials_volumetric.step1_ask_new_name")
    
    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
    return EDIT_TIER_NAME

async def get_new_tier_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    new_name = update.message.text.strip()
    if new_name.lower() != '/skip':
        context.user_data['edit_tier']['tier_name'] = new_name
    
    tier = context.user_data['edit_tier']
    text = _("financials_volumetric.current_value", value=f"{tier['volume_limit_gb']} گیگابایت")
    text += _("financials_volumetric.step2_ask_new_limit")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return EDIT_TIER_LIMIT

async def get_new_tier_limit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    new_limit_text = update.message.text.strip()
    if new_limit_text.lower() != '/skip':
        try:
            new_limit = int(new_limit_text)
            if new_limit <= 0: raise ValueError
            context.user_data['edit_tier']['volume_limit_gb'] = new_limit
        except (ValueError, TypeError):
            await update.message.reply_text(_("financials_volumetric.invalid_limit")); return EDIT_TIER_LIMIT
            
    tier = context.user_data['edit_tier']
    text = _("financials_volumetric.current_value", value=_("financials_volumetric.price_toman", price=tier['price_per_gb']))
    text += _("financials_volumetric.step3_ask_new_price")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return EDIT_TIER_PRICE

async def get_new_tier_price_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    new_price_text = update.message.text.strip()
    if new_price_text.lower() != '/skip':
        try:
            new_price = int(new_price_text)
            if new_price < 0: raise ValueError
            context.user_data['edit_tier']['price_per_gb'] = new_price
        except (ValueError, TypeError):
            await update.message.reply_text(_("financials_unlimited.invalid_price")); return EDIT_TIER_PRICE

    tier_data = context.user_data['edit_tier']
    text = _("financials_volumetric.confirm_edit_prompt_title")
    text += _("financials_volumetric.confirm_name", name=tier_data['tier_name'])
    text += _("financials_volumetric.confirm_limit", limit=tier_data['volume_limit_gb'])
    text += _("financials_volumetric.confirm_price", price=f"{tier_data['price_per_gb']:,}")
    text += _("financials_volumetric.confirm_edit_question")

    keyboard = [[
        InlineKeyboardButton(_("financials_unlimited.button_confirm_save"), callback_data="vol_confirm_edit"),
        InlineKeyboardButton(_("financials_unlimited.button_cancel_add"), callback_data="vol_cancel_edit")
    ]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_TIER_EDIT

async def save_edited_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer(_("financials_volumetric.saving_changes"))
    tier_data = context.user_data.pop('edit_tier', {})
    
    if not tier_data:
        await query.edit_message_text(_("financials_volumetric.error_tier_info_lost"))
        return ConversationHandler.END

    tier_id = tier_data.pop('id')
    await crud_volumetric.update_pricing_tier(
        tier_id=tier_id,
        update_data=tier_data
    )
    
    await query.edit_message_text(_("financials_volumetric.edit_success"))
    await manage_volumetric_plans_menu(update, context)
    return ConversationHandler.END

async def cancel_edit_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    context.user_data.pop('edit_tier', None)
    await query.edit_message_text(_("financials_volumetric.edit_cancelled"))
    await manage_volumetric_plans_menu(update, context)
    return ConversationHandler.END

async def confirm_delete_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    tier_id = int(query.data.split('_')[-1])
    tier = await crud_volumetric.get_pricing_tier_by_id(tier_id)
    if not tier:
        await query.answer(_("financials_unlimited.plan_not_found"), show_alert=True)
        return

    text = _("financials_volumetric.delete_confirm_prompt", name=tier.tier_name)
    keyboard = [[
        InlineKeyboardButton(_("financials_unlimited.button_confirm_delete"), callback_data=f"vol_do_delete_tier_{tier_id}"),
        InlineKeyboardButton(_("financials_unlimited.button_cancel_delete"), callback_data="admin_manage_volumetric")
    ]]
    await query.answer()
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def execute_delete_tier(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    tier_id = int(query.data.split('_')[-1])
    await query.answer(_("financials_volumetric.deleting"))
    await crud_volumetric.delete_pricing_tier(tier_id)
    await query.edit_message_text(_("financials_volumetric.delete_success"))
    await manage_volumetric_plans_menu(update, context)

edit_base_price_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(prompt_for_base_price, pattern='^vol_edit_base_price$')],
    states={GET_BASE_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_base_price)]},
    fallbacks=[]
)
add_tier_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_tier, pattern='^vol_add_tier$')],
    states={
        GET_TIER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tier_name)],
        GET_TIER_LIMIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tier_limit)],
        GET_TIER_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tier_price_and_confirm)],
        CONFIRM_TIER_ADD: [
            CallbackQueryHandler(save_new_tier, pattern='^vol_confirm_add$'),
            CallbackQueryHandler(cancel_add_tier, pattern='^vol_cancel_add$')
        ]
    },
    fallbacks=[], conversation_timeout=600
)
edit_tier_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_edit_tier, pattern=r'^vol_edit_tier_')],
    states={
        EDIT_TIER_NAME: [CommandHandler('skip', get_new_tier_name), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_tier_name)],
        EDIT_TIER_LIMIT: [CommandHandler('skip', get_new_tier_limit), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_tier_limit)],
        EDIT_TIER_PRICE: [CommandHandler('skip', get_new_tier_price_and_confirm), MessageHandler(filters.TEXT & ~filters.COMMAND, get_new_tier_price_and_confirm)],
        CONFIRM_TIER_EDIT: [
            CallbackQueryHandler(save_edited_tier, pattern='^vol_confirm_edit$'),
            CallbackQueryHandler(cancel_edit_tier, pattern='^vol_cancel_edit$')
        ]
    },
    fallbacks=[], conversation_timeout=600
)
# --- END OF FILE modules/financials/actions/volumetric_plans_admin.py ---
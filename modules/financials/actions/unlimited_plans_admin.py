# FILE: modules/financials/actions/unlimited_plans_admin.py (نسخه اصلاح شده)
# --- START OF FILE ---

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, CommandHandler, filters
)
from telegram.constants import ParseMode

from database.crud import unlimited_plan as crud_unlimited_plan
from .settings import show_plan_management_menu
# ✨ FIX: The problematic import line that caused the crash has been removed from here.

LOGGER = logging.getLogger(__name__)

GET_NAME, GET_PRICE, GET_IPS, GET_SORT_ORDER, CONFIRM_ADD = range(5)

async def manage_unlimited_plans_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    await query.answer()

    all_plans = await crud_unlimited_plan.get_all_unlimited_plans()
    
    text = _("financials_unlimited.menu_title")
    keyboard_rows = []

    if not all_plans:
        text += _("financials_unlimited.no_plans_found")
    else:
        text += _("financials_unlimited.plans_list_title")
        for plan in all_plans:
            status_icon = "✅" if plan.is_active else "❌"
            plan_name_escaped = html.escape(plan.plan_name)
            plan_text = _("financials.financials_unlimited.plan_list_item", 
                        status_icon=status_icon, name=plan_name_escaped,
                        price=f"{plan.price:,}", ips=plan.max_ips)
            
            plan_buttons = [
                InlineKeyboardButton(_("financials_unlimited.button_delete"), callback_data=f"unlimplan_delete_{plan.id}"),
                InlineKeyboardButton(_("financials_unlimited.button_toggle_status"), callback_data=f"unlimplan_toggle_{plan.id}")
            ]
            keyboard_rows.append([InlineKeyboardButton(plan_text, callback_data=f"unlimplan_noop_{plan.id}")])
            keyboard_rows.append(plan_buttons)

    keyboard_rows.append([InlineKeyboardButton(_("financials_unlimited.button_add_new"), callback_data="unlimplan_add_new")])
    keyboard_rows.append([InlineKeyboardButton(_("financials_settings.button_back_to_payment_methods"), callback_data="back_to_plan_management")])
    
    await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode=ParseMode.HTML)


async def start_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    context.user_data['new_unlimited_plan'] = {}
    
    text = _("financials_unlimited.add_plan_title") + _("financials_unlimited.step1_ask_name")
    await query.edit_message_text(text=text, parse_mode=ParseMode.MARKDOWN)
    return GET_NAME


async def get_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    plan_name = update.message.text.strip()
    context.user_data['new_unlimited_plan']['plan_name'] = plan_name
    
    text = _("financials_unlimited.name_saved", name=plan_name) + _("financials_unlimited.step2_ask_price")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_PRICE


async def get_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        price = int(update.message.text.strip())
        if price < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_unlimited.invalid_price"))
        return GET_PRICE
    
    context.user_data['new_unlimited_plan']['price'] = price
    text = _("financials_unlimited.price_saved", price=f"{price:,}") + _("financials_unlimited.step3_ask_ips")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_IPS


async def get_max_ips(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        max_ips = int(update.message.text.strip())
        if max_ips <= 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_unlimited.invalid_ips"))
        return GET_IPS
        
    context.user_data['new_unlimited_plan']['max_ips'] = max_ips
    text = _("financials_unlimited.ips_saved", ips=max_ips) + _("financials_unlimited.step4_ask_sort_order")
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
    return GET_SORT_ORDER


async def get_sort_order_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    try:
        sort_order = int(update.message.text.strip())
    except (ValueError, TypeError):
        await update.message.reply_text(_("financials_unlimited.invalid_sort_order"))
        return GET_SORT_ORDER

    context.user_data['new_unlimited_plan']['sort_order'] = sort_order
    plan_data = context.user_data['new_unlimited_plan']

    text = _("financials_unlimited.confirm_prompt_title")
    text += _("financials_unlimited.confirm_name", name=plan_data['plan_name'])
    text += _("financials_unlimited.confirm_price", price=f"{plan_data['price']:,}")
    text += _("financials_unlimited.confirm_ips", ips=plan_data['max_ips'])
    text += _("financials_unlimited.confirm_sort_order", sort_order=plan_data['sort_order'])
    text += _("financials_unlimited.confirm_prompt_question")
    
    keyboard = [[
        InlineKeyboardButton(_("financials_unlimited.button_confirm_save"), callback_data="unlimplan_confirm_add"),
        InlineKeyboardButton(_("financials_unlimited.button_cancel_add"), callback_data="unlimplan_cancel_add")
    ]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    return CONFIRM_ADD


async def save_new_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer(_("financials_unlimited.saving"))
    plan_data = context.user_data.pop('new_unlimited_plan', {})
    if not plan_data:
        await query.edit_message_text(_("financials_unlimited.error_plan_info_lost"))
        return ConversationHandler.END

    await crud_unlimited_plan.add_unlimited_plan(plan_data)
    await query.edit_message_text(_("financials_unlimited.add_success"))
    await manage_unlimited_plans_menu(update, context)
    return ConversationHandler.END


async def cancel_add_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    await query.answer()
    context.user_data.pop('new_unlimited_plan', None)
    await query.edit_message_text(_("financials_unlimited.add_cancelled"))
    await manage_unlimited_plans_menu(update, context)
    return ConversationHandler.END


async def confirm_delete_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    plan = await crud_unlimited_plan.get_unlimited_plan_by_id(plan_id)
    if not plan:
        await query.answer(_("financials_unlimited.plan_not_found"), show_alert=True)
        return

    text = _("financials_unlimited.delete_confirm_prompt", name=plan.plan_name)
    keyboard = [[
        InlineKeyboardButton(_("financials_unlimited.button_confirm_delete"), callback_data=f"unlimplan_do_delete_{plan_id}"),
        InlineKeyboardButton(_("financials_unlimited.button_cancel_delete"), callback_data="admin_manage_unlimited")
    ]]
    await query.answer()
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))


async def execute_delete_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    await query.answer(_("financials_unlimited.deleting"))
    
    if await crud_unlimited_plan.delete_unlimited_plan(plan_id):
        await query.edit_message_text(_("financials_unlimited.delete_success"))
    else:
        await query.edit_message_text(_("financials_unlimited.delete_error"))
    await manage_unlimited_plans_menu(update, context)


async def toggle_plan_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from shared.translator import _
    query = update.callback_query
    plan_id = int(query.data.split('_')[-1])
    await query.answer(_("financials_unlimited.toggling_status"))
    
    plan = await crud_unlimited_plan.get_unlimited_plan_by_id(plan_id)
    if not plan:
        await query.answer(_("financials_unlimited.plan_not_found"), show_alert=True)
        return
        
    await crud_unlimited_plan.update_unlimited_plan(
        plan_id=plan_id,
        update_data={'is_active': not plan.is_active}
    )
    await manage_unlimited_plans_menu(update, context)


add_unlimited_plan_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_add_plan, pattern='^unlimplan_add_new$')],
    states={
        GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_plan_name)],
        GET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_plan_price)],
        GET_IPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_max_ips)],
        GET_SORT_ORDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sort_order_and_confirm)],
        CONFIRM_ADD: [
            CallbackQueryHandler(save_new_plan, pattern='^unlimplan_confirm_add$'),
            CallbackQueryHandler(cancel_add_plan, pattern='^unlimplan_cancel_add$')
        ]
    },
    fallbacks=[],
    conversation_timeout=600
)

# --- END OF FILE ---
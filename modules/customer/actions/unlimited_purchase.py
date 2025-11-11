# --- START OF FILE modules/customer/actions/unlimited_purchase.py ---
import logging
import re
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram.constants import ParseMode

from database.crud import unlimited_plan as crud_unlimited_plan
from modules.payment.actions.creation import create_and_send_invoice
from shared.keyboards import get_back_to_main_menu_keyboard, get_customer_shop_keyboard

from modules.marzban.actions.data_manager import normalize_username
from modules.general.actions import end_conv_and_reroute
from shared.translator import _
# ✨ NEW IMPORTS FOR MULTI-PANEL ARCHITECTURE
from typing import Optional, Dict, Any
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel
# ---
LOGGER = logging.getLogger(__name__)

# ✨ MODIFIED IMPORTS AND STATES
from typing import Optional, Dict, Any
from core.panel_api.marzban import MarzbanPanel
from database.crud import panel_credential as crud_panel

SELECT_PANEL, ASK_USERNAME, CHOOSE_PLAN, CONFIRM_UNLIMITED_PLAN = range(4)

USERNAME_PATTERN = r"^[a-zA-Z0-9_]{5,20}$"
CANCEL_CALLBACK_DATA = "cancel_unlimited_plan"

def _get_cancel_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(_("buttons.cancel_and_back_to_shop"), callback_data=CANCEL_CALLBACK_DATA)

async def _get_user_from_all_panels(username: str) -> Optional[Dict[str, Any]]:
    """Checks for a user's existence across all panels."""
    all_panels = await crud_panel.get_all_panels()
    for panel in all_panels:
        if panel.panel_type.value == "marzban":
            credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
            api = MarzbanPanel(credentials)
            user_data = await api.get_user_data(username)
            if user_data:
                return user_data
    return None

async def _build_panel_selection_keyboard() -> Optional[InlineKeyboardMarkup]:
    """Builds an inline keyboard for active panel selection by customers."""
    panels = await crud_panel.get_all_panels()
    if not panels:
        return None
    keyboard = [[InlineKeyboardButton(p.name, callback_data=f"unlim_select_panel_{p.id}")] for p in panels]
    keyboard.append([_get_cancel_button()])
    return InlineKeyboardMarkup(keyboard)

async def _get_user_from_all_panels(username: str) -> Optional[Dict[str, Any]]:
    """Checks for a user's existence across all panels."""
    all_panels = await crud_panel.get_all_panels()
    for panel in all_panels:
        if panel.panel_type.value == "marzban":
            credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
            api = MarzbanPanel(credentials)
            user_data = await api.get_user_data(username)
            if user_data:
                return user_data
    return None

async def start_unlimited_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    
    keyboard = await _build_panel_selection_keyboard()
    if not keyboard:
        await update.effective_message.reply_text(_("panel_manager.add.no_panels_configured"), reply_markup=get_customer_shop_keyboard())
        return ConversationHandler.END

    text = _("unlimited_purchase.step0_ask_panel")
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.effective_message.edit_text(text, reply_markup=keyboard)
    else:
        await update.effective_message.reply_text(text, reply_markup=keyboard)

    return SELECT_PANEL

async def select_panel_and_ask_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Stores the selected panel and asks for the username with a formatted message."""
    query = update.callback_query
    await query.answer()
    
    panel_id = int(query.data.split('_')[-1])
    context.user_data['unlimited_plan'] = {'panel_id': panel_id}

    text = (
        f"💎 <b>{_('unlimited_purchase.title')}</b>\n\n"
        f"{_('unlimited_purchase.step1_ask_username_v2')}\n\n"
        f"❗️ <b>{_('custom_purchase.username_rules_title')}</b>\n"
        f"▪️ {_('custom_purchase.username_rule_length', min=5, max=20)}\n"
        f"▪️ {_('custom_purchase.username_rule_chars')}\n"
        f"▪️ {_('custom_purchase.username_rule_no_space')}\n\n"
        f"{_('custom_purchase.cancel_instruction')}"
    )

    keyboard = InlineKeyboardMarkup([[_get_cancel_button()]])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)
    
    return ASK_USERNAME

async def get_username_and_ask_plan(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    username_input = update.message.text.strip()
    if not re.match(USERNAME_PATTERN, username_input):
        await update.message.reply_text(_("custom_purchase.username_invalid"))
        return ASK_USERNAME

    username_to_check = normalize_username(username_input)
    existing_user = await _get_user_from_all_panels(username_to_check)
    if existing_user and "error" not in existing_user:
        await update.message.reply_text(_("custom_purchase.username_taken"))
        return ASK_USERNAME

    existing_user = await _get_user_from_all_panels(username_to_check)
    context.user_data['unlimited_plan']['username'] = username_to_check
    active_plans = await crud_unlimited_plan.get_active_unlimited_plans()
    if not active_plans:
        await update.message.reply_text(_("unlimited_purchase.no_plans_available"), reply_markup=get_customer_shop_keyboard())
        return ConversationHandler.END

    keyboard_rows = [
        [InlineKeyboardButton(_("unlimited_purchase.plan_button_format", name=p.plan_name, price=f"{p.price:,}"), callback_data=f"unlim_select_{p.id}")] 
        for p in active_plans
    ]
    keyboard_rows.append([_get_cancel_button()])
    
    text = _("unlimited_purchase.step2_ask_plan", username=username_to_check)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode=ParseMode.HTML)
    return CHOOSE_PLAN

async def select_plan_and_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    plan_id = int(query.data.split('_')[-1])
    plan = await crud_unlimited_plan.get_unlimited_plan_by_id(plan_id)
    if not plan or not plan.is_active:
        await query.edit_message_text(_("unlimited_purchase.plan_not_available"), reply_markup=None)
        return ConversationHandler.END

    context.user_data['unlimited_plan'].update({
        'plan_id': plan.id, 
        'plan_name': plan.plan_name,
        'price': plan.price, 
        'max_ips': plan.max_ips
    })
    username = context.user_data['unlimited_plan']['username']

    text = _("unlimited_purchase.invoice_preview",
             username=username,
             plan_name=plan.plan_name,
             max_ips=plan.max_ips,
             price=f"{plan.price:,}")
             
    keyboard = [
        [InlineKeyboardButton(_("buttons.confirm_and_get_invoice"), callback_data="unlim_confirm_final")],
        [_get_cancel_button()]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    return CONFIRM_UNLIMITED_PLAN

async def generate_unlimited_invoice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from database.crud import user_note as crud_user_note # Import the necessary CRUD module

    query = update.callback_query
    await query.answer(_("customer_service.generating_invoice"))
    
    user_id = query.from_user.id
    plan_data = context.user_data.get('unlimited_plan')
    if not plan_data:
        await query.edit_message_text(_("errors.plan_info_not_found"))
        return ConversationHandler.END

    # Step 1: Save the chosen plan details to user_note BEFORE creating the invoice
    # For unlimited plans, duration is typically fixed (e.g., 30 days) and volume is 0
    await crud_user_note.create_or_update_user_note(
        marzban_username=plan_data['username'],
        duration=30,  # Assuming a fixed 30-day duration for unlimited plans
        data_limit_gb=0, # 0 indicates unlimited
        price=plan_data['price']
    )

    # Step 2: Prepare details for the invoice itself
    plan_details_for_invoice = {
        "invoice_type": "NEW_USER_UNLIMITED",
        "username": plan_data['username'],
        "plan_id": plan_data['plan_id'],
        "plan_name": plan_data['plan_name'],
        "max_ips": plan_data['max_ips'],
        "price": plan_data['price'],
        "panel_id": plan_data.get('panel_id'),
        "duration": 30, # Also add duration to invoice details for display
        "volume": 0
    }
    
    # Step 3: Delete the previous message and send the invoice
    await query.message.delete()
    invoice = await create_and_send_invoice(context, user_id, plan_details_for_invoice)

    if not invoice:
        await context.bot.send_message(chat_id=user_id, text=_("customer_service.system_error_retry"))

    context.user_data.clear()
    return ConversationHandler.END

async def cancel_unlimited_purchase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from .panel import show_customer_panel
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(_("unlimited_purchase.purchase_cancelled"), reply_markup=None)
    context.user_data.clear()
    
    class DummyUpdate:
        def __init__(self, original_update):
            self.message = original_update.effective_message
            self.effective_chat = original_update.effective_chat
            self.callback_query = None

    await show_customer_panel(DummyUpdate(update), context)
    
    return ConversationHandler.END

MAIN_MENU_REGEX = f'^({_("keyboards.customer_main_menu.shop")}|{_("keyboards.customer_main_menu.my_services")}|{_("keyboards.customer_main_menu.connection_guide")}|{_("keyboards.general.back_to_main_menu")})$'
IGNORE_MAIN_MENU_FILTER = filters.TEXT & ~filters.COMMAND & ~filters.Regex(MAIN_MENU_REGEX)

unlimited_purchase_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex(f'^{_("keyboards.customer_shop.unlimited_volume_plan")}$'), start_unlimited_purchase)],
    states={
        ASK_USERNAME: [MessageHandler(IGNORE_MAIN_MENU_FILTER, get_username_and_ask_plan)],
        CHOOSE_PLAN: [CallbackQueryHandler(select_plan_and_confirm, pattern=r'^unlim_select_')],
        CONFIRM_UNLIMITED_PLAN: [CallbackQueryHandler(generate_unlimited_invoice, pattern=r'^unlim_confirm_final$')],
    },
    fallbacks=[
        CallbackQueryHandler(cancel_unlimited_purchase, pattern=f'^{CANCEL_CALLBACK_DATA}$'),
        MessageHandler(filters.Regex(MAIN_MENU_REGEX), end_conv_and_reroute),
    ],
    conversation_timeout=600,
)
# --- END OF FILE modules/customer/actions/unlimited_purchase.py ---
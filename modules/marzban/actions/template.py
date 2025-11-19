# --- START: Final replacement for modules/marzban/actions/template.py ---
import logging
import html
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode

from database.crud import panel_credential as crud_panel
from .constants import SET_TEMPLATE_USER_PROMPT
from database.crud import template_config as crud_template
from .data_manager import normalize_username
from shared.keyboards import get_panel_management_keyboard
from shared.panel_utils import get_user_data_from_panels as get_user_data

LOGGER = logging.getLogger(__name__)

async def set_template_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    query = update.callback_query
    print(f"!!!!!!!!!!!!!!!!! RECEIVED CALLBACK DATA: {query.data} !!!!!!!!!!!!!!!!!")
    await query.answer()

    try:
        panel_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(_("errors.invalid_callback_data"))
        return ConversationHandler.END

    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await query.edit_message_text(_("panel_manager.delete.not_found"))
        return ConversationHandler.END

    context.user_data['template_panel_id'] = panel_id
    context.user_data['template_panel_name'] = panel.name

    template_config_obj = await crud_template.load_template_config(panel_id)
    current_template = template_config_obj.template_username if template_config_obj else _("marzban_template.not_set")
    LOGGER.info(f"[Template] Entering template setup for panel ID {panel_id}. Current: '{current_template}'")

    safe_panel_name = html.escape(panel.name)

    message = _("marzban_template.title_for_panel", panel_name=f"*{safe_panel_name}*")
    message += _("marzban_template.description")
    message += _("marzban_template.current_template", template=f"`{current_template}`")
    message += _("marzban_template.prompt")

    try:
        await query.edit_message_text(
            message, parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        LOGGER.error(f"Error editing message in template_start: {e}", exc_info=True)
        # Fallback for safety
        await query.message.reply_text("An error occurred displaying the menu.")

    return SET_TEMPLATE_USER_PROMPT

async def set_template_user_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    
    panel_id = context.user_data.get('template_panel_id')
    panel_name = context.user_data.get('template_panel_name', 'Unknown')

    if not panel_id:
        await update.message.reply_text(_("errors.generic_error_try_again"))
        return ConversationHandler.END

    username = normalize_username(update.message.text.strip())
    
    await update.message.reply_text(_("marzban_template.checking_user", username=f"`{username}`"))

    user_data = await get_user_data(username, panel_id)
    if not user_data:
        await update.message.reply_text(_("marzban_template.user_not_found", username=f"`{username}`"))
        return SET_TEMPLATE_USER_PROMPT

    proxies = user_data.get("proxies")
    inbounds = user_data.get("inbounds")
    if not proxies or not inbounds:
        await update.message.reply_text(_("marzban_template.validation_error", username=f"`{username}`"))
        return SET_TEMPLATE_USER_PROMPT

    template_config_data = {"template_username": username, "proxies": proxies, "inbounds": inbounds}
    LOGGER.info(f"[Template] Saving new template config for panel {panel_id}: {template_config_data}")
    await crud_template.save_template_config(panel_id, template_config_data)
    
    safe_panel_name = html.escape(panel_name)

    confirmation_message = _("marzban_template.success_title_for_panel", panel_name=f"*{safe_panel_name}*")
    confirmation_message += _("marzban_template.success_username", username=f"`{username}`")
    confirmation_message += _("marzban_template.success_inbounds", count=f"`{len(inbounds)}`")
    confirmation_message += _("marzban_template.success_proxies", count=f"`{len(proxies)}`")
    confirmation_message += _("marzban_template.success_footer")

    await update.message.reply_text(
        confirmation_message,
        reply_markup=await get_panel_management_keyboard(),
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data.clear()
    return ConversationHandler.END
# --- END: Replacement ---
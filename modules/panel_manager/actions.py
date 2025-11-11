# FILE: modules/panel_manager/actions.py (FINAL VERSION WITH CORRECT TRANSLATOR METHOD)

import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode
import html

# ✨ FIX: Import the translator object itself
from shared.translator import translator
from database.crud import panel_credential as crud_panel
from database.crud import marzban_link as crud_marzban_link
from shared.keyboards import get_panel_management_keyboard, get_panel_type_selection_keyboard
from shared.callbacks import cancel_and_remove_message

LOGGER = logging.getLogger(__name__)

# States for conversations remain the same
MANAGE_PANEL_MENU = 100
SELECT_PANEL_TYPE, GET_PANEL_NAME, GET_API_URL, GET_USERNAME, GET_PASSWORD = range(5)

async def show_panel_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Displays the dynamic panel list ReplyKeyboard and enters the conversation."""
    from shared.translator import translator
    
    await update.message.reply_text(
        translator.get("panel_manager.list.title_select_reply"),
        reply_markup=await get_panel_management_keyboard()
    )
    return MANAGE_PANEL_MENU


# --- Add Panel Conversation ---
async def start_add_panel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel'] = {}
    await update.message.reply_text(
        translator.get("panel_manager.add.prompt_type"),
        reply_markup=get_panel_type_selection_keyboard()
    )
    return SELECT_PANEL_TYPE

async def select_panel_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    panel_type = query.data.replace("add_panel_type_", "")
    context.user_data['new_panel']['panel_type'] = panel_type
    await query.edit_message_text(translator.get("panel_manager.add.prompt_name"))
    return GET_PANEL_NAME

async def get_panel_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['name'] = update.message.text.strip()
    await update.message.reply_text(translator.get("panel_manager.add.prompt_url"))
    return GET_API_URL

async def get_api_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    api_url = update.message.text.strip()
    if not api_url.startswith("http"): api_url = f"https://{api_url}"
    context.user_data['new_panel']['api_url'] = api_url
    await update.message.reply_text(translator.get("panel_manager.add.prompt_username"))
    return GET_USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['username'] = update.message.text.strip()
    await update.message.reply_text(translator.get("panel_manager.add.prompt_password"))
    return GET_PASSWORD

async def get_password_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['new_panel']['password'] = update.message.text.strip()
    new_panel = await crud_panel.add_panel(context.user_data['new_panel'])
    if new_panel:
        message_text = translator.get("panel_manager.add.success", name=new_panel.name, type=new_panel.panel_type.value)
        await update.message.reply_text(message_text, reply_markup=await get_panel_management_keyboard())
    else:
        await update.message.reply_text(translator.get("panel_manager.add.db_error"), reply_markup=await get_panel_management_keyboard())
    context.user_data.clear()
    return ConversationHandler.END

async def cancel_add_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data.clear()
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(translator.get("general.operation_cancelled"))
    return ConversationHandler.END


async def select_panel_from_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles a click on a panel name by querying the DB and shows the inline management menu."""
    from shared.translator import translator
    panel_name = update.message.text
    
    # ✨ FIX: Query the database directly instead of relying on user_data
    panel = await crud_panel.get_panel_by_name(panel_name)
    
    if not panel:
        await update.message.reply_text(translator.get("panel_manager.delete.not_found"))
        return
        
    panel_id = panel.id
    
    # --- The rest of the function remains the same ---
    test_status_emoji = "✅" if panel.is_test_panel else "❌"
    test_status_text = f'{test_status_emoji} ' + translator.get("keyboards.single_panel_management.test_panel_status")

    keyboard = [
        [
            InlineKeyboardButton(translator.get("keyboards.single_panel_management.connection_status"), callback_data=f"panel_status_{panel_id}"),
            InlineKeyboardButton(translator.get("keyboards.single_panel_management.delete_panel"), callback_data=f"confirm_delete_panel_{panel_id}")
        ],
        [
            InlineKeyboardButton(translator.get("keyboards.helper_tools.set_template_user"), callback_data=f"set_template_{panel_id}")
        ],
        [
            InlineKeyboardButton(test_status_text, callback_data=f"toggle_test_panel_{panel_id}")
        ]
    ]

    
    message_text = translator.get("panel_manager.single.menu_title_inline", name=html.escape(panel_name))
    
    await update.message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def check_panel_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer(translator.get("panel_manager.status.checking"), show_alert=False)

    panel_id = int(query.data.split('_')[-1])
    panel = await crud_panel.get_panel_by_id(panel_id)

    if not panel:
        await query.answer(translator.get("panel_manager.delete.not_found"), show_alert=True)
        try: await query.message.delete()
        except Exception: pass
        return

    api = None
    if panel.panel_type.value == "marzban":
        from core.panel_api.marzban import MarzbanPanel
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        api = MarzbanPanel(credentials)
    elif panel.panel_type.value == "x-ui": # ✨ ADD THIS PART
        from core.panel_api.xui import XUIPanel
        credentials = {'api_url': panel.api_url, 'username': panel.username, 'password': panel.password}
        api = XUIPanel(credentials)

    if not api:
        await query.message.reply_text(translator.get("panel_manager.status.unsupported_type"))
        return

    token = await api._get_token()
    message_text = translator.get("panel_manager.status.success" if token else "panel_manager.status.fail", name=panel.name)
    await query.message.reply_text(message_text)


# --- Delete Panel Flow ---

async def confirm_delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    panel_to_delete_id = int(query.data.split('_')[-1])
    panel_to_delete = await crud_panel.get_panel_by_id(panel_to_delete_id)

    if not panel_to_delete:
        await query.answer(translator.get("panel_manager.delete.not_found"), show_alert=True)
        await query.message.delete()
        return

    links_count = await crud_marzban_link.count_links_for_panel(panel_to_delete_id)

    if links_count == 0:
        text = translator.get("panel_manager.delete.confirm", name=html.escape(panel_to_delete.name))
        keyboard = [
            [InlineKeyboardButton(translator.get("keyboards.buttons.delete_confirm"), callback_data=f"do_delete_panel_{panel_to_delete_id}")],
            [InlineKeyboardButton(translator.get("buttons.cancel"), callback_data="cancel_generic")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)
    else:
        other_panels = await crud_panel.get_all_panels(exclude_ids=[panel_to_delete_id])
        
        if not other_panels:
            text = translator.get("panel_manager.delete.migration_impossible", name=html.escape(panel_to_delete.name), count=links_count)
            await query.edit_message_text(text, parse_mode=ParseMode.HTML)
            return

        text = translator.get("panel_manager.delete.migration_required", name=html.escape(panel_to_delete.name), count=links_count)
        
        keyboard = []
        for target_panel in other_panels:
            callback_data = f"migrate_del_{panel_to_delete_id}_{target_panel.id}"
            button_text = translator.get("panel_manager.buttons.migrate_to", name=html.escape(target_panel.name))
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        
        keyboard.append([InlineKeyboardButton(translator.get("buttons.cancel"), callback_data="cancel_generic")])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)


async def migrate_and_delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        _, _, source_panel_id_str, target_panel_id_str = query.data.split('_')
        source_panel_id = int(source_panel_id_str)
        target_panel_id = int(target_panel_id_str)
    except (ValueError, IndexError):
        await query.edit_message_text(translator.get("errors.invalid_callback_data"))
        return

    source_panel = await crud_panel.get_panel_by_id(source_panel_id)
    target_panel = await crud_panel.get_panel_by_id(target_panel_id)

    if not source_panel or not target_panel:
        await query.edit_message_text(translator.get("panel_manager.delete.not_found"))
        return

    in_progress_text = translator.get("panel_manager.delete.migration_inprogress", source=html.escape(source_panel.name), target=html.escape(target_panel.name))
    await query.edit_message_text(in_progress_text, parse_mode=ParseMode.HTML)

    migrated_count = await crud_marzban_link.migrate_users_to_new_panel(old_panel_id=source_panel_id, new_panel_id=target_panel_id)
    deleted = await crud_panel.delete_panel(source_panel_id)

    if deleted:
        final_text = translator.get("panel_manager.delete.migration_success", count=migrated_count, source=html.escape(source_panel.name), target=html.escape(target_panel.name))
    else:
        final_text = translator.get("panel_manager.delete.migration_fail", source=html.escape(source_panel.name))

    await query.edit_message_text(final_text, parse_mode=ParseMode.HTML)


async def do_delete_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    panel_id = int(query.data.split('_')[-1])
    panel = await crud_panel.get_panel_by_id(panel_id)
    if not panel:
        await query.edit_message_text(translator.get("panel_manager.delete.not_found"))
        return
        
    deleted = await crud_panel.delete_panel(panel_id)
    
    if deleted:
        final_text = translator.get("panel_manager.delete.success_final", name=html.escape(panel.name))
        await query.edit_message_text(final_text, parse_mode=ParseMode.HTML)
    else:
        await query.edit_message_text(translator.get("panel_manager.delete.fail"), parse_mode=ParseMode.HTML)

# --- ADD THIS NEW FUNCTION to the end of modules/panel_manager/actions.py ---
async def toggle_test_panel_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the callback to toggle the is_test_panel status."""
    from shared.translator import translator
    query = update.callback_query
    await query.answer()

    try:
        panel_id = int(query.data.split('_')[-1])
    except (ValueError, IndexError):
        await query.edit_message_text(translator.get("errors.invalid_callback_data"))
        return

    new_status = await crud_panel.toggle_test_panel_status(panel_id)

    if new_status is None:
        await query.answer(translator.get("panel_manager.errors.toggle_failed"), show_alert=True)
        return

    # After toggling, we need to rebuild and show the same menu again with the updated status
    # We can do this by calling the select_panel_from_reply function again with a mock update
    panel = await crud_panel.get_panel_by_id(panel_id)
    if panel:
        # Create a mock update object to re-trigger the menu display
        class MockMessage:
            def __init__(self, text):
                self.text = text
            async def reply_text(self, text, reply_markup, parse_mode=None):
                await query.message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        
        mock_update = type('obj', (object,), {'message': MockMessage(panel.name)})()
        await select_panel_from_reply(mock_update, context)
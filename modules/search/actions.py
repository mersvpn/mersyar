# --- START: Replace the ENTIRE content of modules/search/actions.py ---
import logging
import math
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from database.crud import bot_managed_user as crud_bot_managed_user
from config import config
# Database and utility imports
from database.crud import user as crud_user
from shared import panel_utils
from shared.keyboards import get_back_to_main_menu_keyboard
from shared.translator import _
from shared.callback_types import SEARCH_RESULT_PREFIX
from telegram.constants import ParseMode

# Imports from Marzban module for username search results
from modules.marzban.actions.display import build_users_keyboard, show_user_details
from modules.marzban.actions.data_manager import normalize_username
from modules.marzban.actions.constants import USERS_PER_PAGE
from database.crud import marzban_link as crud_marzban_link


# --- ✨ CORRECTED IMPORT: Import state constants from the local display.py file ---
from .display import MAIN_MENU

LOGGER = logging.getLogger(__name__)
SEARCH_PROMPT = 0 # Define the initial conversation state

async def prompt_for_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Asks the user for a search query and shows a 'Back' keyboard."""
    await update.message.reply_text(
        _("search.prompt"),
        reply_markup=get_back_to_main_menu_keyboard()
    )
    return SEARCH_PROMPT

async def process_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Intelligently determines the search type and returns the next conversation state.
    """
    query = update.message.text.strip()
    
    if query.isdigit():
        telegram_id = int(query)
        LOGGER.info(f"Search query '{query}' is a number. Treating as Telegram ID.")
        return await _search_by_telegram_id(update, context, telegram_id)
    else:
        LOGGER.info(f"Search query '{query}' is text. Treating as Service Username.")
        return await _search_by_service_username(update, context, query)

async def _search_by_telegram_id(update: Update, context: ContextTypes.DEFAULT_TYPE, telegram_id: int) -> int:
    """
    Handles search by Telegram ID.
    - Super Admins: See full User Profile Management menu.
    - Support Admins: See Service Details (Auto-cleans dead links).
    """
    searcher_id = update.effective_user.id

    if searcher_id in config.AUTHORIZED_USER_IDS:
        user_data = await crud_user.get_user_with_relations(telegram_id)
        if not user_data:
            await update.message.reply_text(_("search.user_not_found_by_id", query=telegram_id))
            return SEARCH_PROMPT 

        context.user_data['target_user_id'] = telegram_id
        
        user_name = user_data.first_name or "N/A"
        user_username = f"@{user_data.username}" if user_data.username else _("user_info.profile.no_username")
        
        menu_keyboard = ReplyKeyboardMarkup(
            [
                [KeyboardButton(_("user_info.menu.user_profile"))],
                [KeyboardButton(_("user_info.menu.services")), KeyboardButton(_("user_info.menu.note_management"))],
                [KeyboardButton(_("user_info.menu.back_to_main"))]
            ],
            resize_keyboard=True
        )

        await update.message.reply_text(
            _("user_info.prompts.user_header", name=user_name, username=user_username, user_id=telegram_id),
            reply_markup=menu_keyboard
        )
        return MAIN_MENU

    else:
        links = await crud_marzban_link.get_links_by_telegram_id_with_panel(telegram_id)
        
        if not links:
            await update.message.reply_text("❌ کاربری با این آیدی یافت نشد (یا سرویسی ندارد).")
            return SEARCH_PROMPT

        my_managed_usernames = await crud_bot_managed_user.get_users_created_by(searcher_id)
        
        await update.message.reply_text("🔍 در حال جستجو و اعتبارسنجی...")
        all_users_panel = await panel_utils.get_all_users_from_all_panels()
        
        if not all_users_panel:
            await update.message.reply_text(_("marzban_display.panel_connection_error"))
            return SEARCH_PROMPT

        valid_target_user = None
        
        for link in links:
            if link.marzban_username in my_managed_usernames:
                
                found_in_panel = next((u for u in all_users_panel if u['username'].lower() == link.marzban_username.lower()), None)
                
                if found_in_panel:
                    valid_target_user = found_in_panel
                    break
                else:
                    LOGGER.info(f"Auto-cleaning dead link: {link.marzban_username} for telegram_id {telegram_id}")
                    await crud_marzban_link.delete_marzban_link(link.marzban_username)
        
        if valid_target_user:
            context.user_data['last_search_results'] = [valid_target_user]
            
            keyboard = build_users_keyboard(
                users=[valid_target_user], 
                current_page=1, 
                total_pages=1, 
                list_type='myusers'
            )
            
            title = _("search.search_results_title_username", query=f"«{valid_target_user['username']}»")
            await update.message.reply_text(title, reply_markup=keyboard)
            return ConversationHandler.END
            
        else:
            # اگر هیچ لینک معتبری نماند (یا همه پاک شدند)
            await update.message.reply_text("⛔️ هیچ سرویس فعال و معتبری برای این کاربر در لیست شما یافت نشد.")
            return SEARCH_PROMPT

async def _search_by_service_username(update: Update, context: ContextTypes.DEFAULT_TYPE, query: str) -> int:
    """Handles searching for services with ownership filtering for support admins."""
    search_query_normalized = normalize_username(query)
    user_id = update.effective_user.id
    
    await update.message.reply_text(
        _("search.searching_for", query=f"«{query}»"),
        reply_markup=get_back_to_main_menu_keyboard()
    )

    try:
        all_users = await panel_utils.get_all_users_from_all_panels()
        if all_users is None:
            await update.message.reply_text(_("marzban_display.panel_connection_error"))
            return SEARCH_PROMPT

        found_users = [
            user for user in all_users 
            if user.get('username') and isinstance(user.get('username'), str) 
            and search_query_normalized in normalize_username(user['username'])
        ]

        if user_id not in config.AUTHORIZED_USER_IDS:
            my_managed_usernames = await crud_bot_managed_user.get_users_created_by(user_id)
            
            found_users = [u for u in found_users if u['username'] in my_managed_usernames]
        # ----------------------------------------

        found_users.sort(key=lambda u: u.get('username', '').lower())

        if not found_users:
            await update.message.reply_text(_("search.no_users_found_by_username", query=f"«{query}»"))
            return SEARCH_PROMPT
        else:
            context.user_data['last_search_results'] = found_users
            page_users = found_users[:USERS_PER_PAGE]
            total_pages = math.ceil(len(found_users) / USERS_PER_PAGE)
            
            keyboard = build_users_keyboard(users=page_users, current_page=1, total_pages=total_pages, list_type='search')
            title = _("search.search_results_title_username", query=f"«{query}»")
            
            await update.message.reply_text(title, reply_markup=keyboard)
            return ConversationHandler.END

    except Exception:
        LOGGER.error(f"An exception occurred during service username search!", exc_info=True)
        await update.message.reply_text("یک خطای داخلی در حین جستجو رخ داد.")
        return SEARCH_PROMPT

async def handle_search_result_click(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles clicks on service username search results."""
    query = update.callback_query
    await query.answer()
    username = query.data.replace(SEARCH_RESULT_PREFIX, "")
    context.user_data['selected_username'] = username
    await show_user_details(update, context)
# --- END: Replacement ---
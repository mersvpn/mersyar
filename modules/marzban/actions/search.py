# FILE: modules/marzban/actions/search.py (REVISED FOR I18N)
import logging
import math
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from .constants import SEARCH_PROMPT, USERS_PER_PAGE
from shared.keyboards import get_back_to_main_menu_keyboard

from .display import build_users_keyboard, get_all_users_from_all_panels
from shared.keyboards import get_user_management_keyboard
from .data_manager import normalize_username

LOGGER = logging.getLogger(__name__)

async def prompt_for_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import _
    await update.message.reply_text(
        _("marzban_search.prompt"),
        reply_markup=ReplyKeyboardRemove()
    )
    return SEARCH_PROMPT

# FILE: modules/marzban/actions/search.py (FINAL, CLEANED VERSION)
import logging
import math
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from .constants import SEARCH_PROMPT, USERS_PER_PAGE

from .display import build_users_keyboard, get_all_users_from_all_panels
from shared.keyboards import get_back_to_main_menu_keyboard
from .data_manager import normalize_username

LOGGER = logging.getLogger(__name__)

async def prompt_for_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    await update.message.reply_text(
        translator.get("marzban_search.prompt"),
        reply_markup=ReplyKeyboardRemove()
    )
    return SEARCH_PROMPT

# --- REPLACE THE ENTIRE search_user FUNCTION ---

async def search_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    from shared.translator import translator
    search_query_raw = update.message.text
    search_query_normalized = normalize_username(search_query_raw)
    
    # Send "Searching..." message and set the "Back" keyboard immediately
    await update.message.reply_text(
        translator.get("marzban_search.searching_for", query=f"«{search_query_raw}»"),
        reply_markup=get_back_to_main_menu_keyboard()
    )

    try:
        all_users = await get_all_users_from_all_panels()
        if all_users is None:
            await update.message.reply_text(translator.get("marzban_display.panel_connection_error"))
            return ConversationHandler.END

        found_users = sorted(
            [user for user in all_users if user.get('username') and search_query_normalized in normalize_username(user['username'])],
            key=lambda u: u['username'].lower()
        )

        if not found_users:
            await update.message.reply_text(translator.get("marzban_search.no_users_found", query=f"«{search_query_raw}»"))
        else:
            context.user_data['last_search_results'] = found_users
            total_pages = math.ceil(len(found_users) / USERS_PER_PAGE)
            page_users = found_users[:USERS_PER_PAGE]
            
            keyboard = build_users_keyboard(users=page_users, current_page=1, total_pages=total_pages, list_type='search')
            
            title = translator.get("marzban_search.search_results_title", query=f"«{search_query_raw}»")
            
            # Send the results as a separate message with the inline keyboard
            await update.message.reply_text(title, reply_markup=keyboard)

    except Exception as e:
        LOGGER.error(f"An exception occurred during search_user execution!", exc_info=True)
        await update.message.reply_text("یک خطای داخلی در حین جستجو رخ داد. لطفاً لاگ‌ها را بررسی کنید.")
    
    return ConversationHandler.END
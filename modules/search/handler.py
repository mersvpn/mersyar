# --- START: Replace the ENTIRE content of modules/search/handler.py ---
from telegram import Update
from telegram.ext import (
    Application, ConversationHandler,
    MessageHandler, filters, CallbackQueryHandler,
    CommandHandler,ContextTypes
)
from shared.callbacks import search_back_to_main
from shared.translator import _
from shared.auth import admin_only_conv, admin_only_callback
from shared.callbacks import main_menu_fallback
from shared.callback_types import SEARCH_RESULT_PREFIX

# --- Imports from local actions file ---
from .actions import (
    prompt_for_search, process_search_query, handle_search_result_click,
    SEARCH_PROMPT
)

# --- ✨ ALL IMPORTS from the old user_info handler are now here ✨ ---
from .display import (
    MAIN_MENU, EDIT_NOTE,
    show_comprehensive_info, show_services, show_note_manager,
    prompt_for_note, save_note, refresh_data, close_menu
)

async def silent_end_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Ends the conversation without sending any message."""
    return ConversationHandler.END

def register(application: Application) -> None:
    """Registers the new, unified search and user management conversation handler."""
    
    SEARCH_USER_TEXT = _("keyboards.admin_main_menu.search_user")
    
    # --- ✨ The new unified ConversationHandler ✨ ---
    unified_search_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f'^{SEARCH_USER_TEXT}$'), admin_only_conv(prompt_for_search))
        ],
        states={
            # --- State 1: Getting the search query ---
            SEARCH_PROMPT: [
                MessageHandler(filters.Regex(f"^{_('keyboards.general.back_to_main_menu')}$"), silent_end_conversation),
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_only_conv(process_search_query))
            ],
            
            # --- State 2: The main user management menu (from old user_info) ---
            MAIN_MENU: [
                MessageHandler(filters.Regex(f"^{_('user_info.menu.user_profile')}$"), admin_only_conv(show_comprehensive_info)),
                MessageHandler(filters.Regex(f"^{_('user_info.menu.services')}$"), admin_only_conv(show_services)),
                MessageHandler(filters.Regex(f"^{_('user_info.menu.note_management')}$"), admin_only_conv(show_note_manager)),
                
                # CallbackQueryHandlers for inline buttons within the user menu
                CallbackQueryHandler(admin_only_callback(refresh_data), pattern="^ui:refresh:"),
                CallbackQueryHandler(admin_only_callback(close_menu), pattern="^ui:close$"),
                CallbackQueryHandler(admin_only_callback(prompt_for_note), pattern="^ui:edit_note:"),
                CallbackQueryHandler(admin_only_callback(prompt_for_note), pattern="^ui:delete_note:")
            ],

            # --- State 3: Editing a user's note (from old user_info) ---
            EDIT_NOTE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_only_conv(save_note))
            ]
        },
        

            fallbacks=[
            CallbackQueryHandler(search_back_to_main, pattern=_( "keyboard.back_to_main")),
            CommandHandler("cancel", search_back_to_main),
        ],

        conversation_timeout=600,
        # Allow other handlers (like our username click handler) to work
        block=False,
        name="unified_search_and_manage_conv",
        allow_reentry=True
    )

    # This handler is for INLINE buttons from a USERNAME search (stateless)
    # It remains separate from the main conversation.
    search_result_handler = CallbackQueryHandler(
        admin_only_callback(handle_search_result_click), 
        pattern=f"^{SEARCH_RESULT_PREFIX}"
    )

    application.add_handler(unified_search_conv)
    application.add_handler(search_result_handler)
# --- END: Replacement ---
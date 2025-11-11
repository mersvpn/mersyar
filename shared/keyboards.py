
# FILE: shared/keyboards.py (FINAL VERSION - NAMESPACE CORRECTED)
from shared.translator import translator
from telegram import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from config import config
from shared.translator import _
# --- MODIFIED IMPORT ---
from database.crud import bot_setting as crud_bot_setting
# --- ----------------- ---
from math import ceil
from shared.translator import translator, _
# =============================================================================
#  ReplyKeyboardMarkup Section
# =============================================================================

def get_admin_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(translator.get("keyboards.admin_main_menu.manage_users"))],
        [KeyboardButton(translator.get("keyboards.admin_main_menu.search_user")), KeyboardButton(translator.get("keyboards.admin_main_menu.notes_management"))],
        [KeyboardButton(translator.get("keyboards.admin_main_menu.settings_and_tools"))],
        [KeyboardButton(translator.get("keyboards.admin_main_menu.send_message")), KeyboardButton(translator.get("keyboards.admin_main_menu.customer_panel_view"))],
        [KeyboardButton(translator.get("keyboards.admin_main_menu.guides_settings"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- ADD THIS NEW FUNCTION to shared/keyboards.py ---
async def get_panel_selection_keyboard() -> ReplyKeyboardMarkup:
    """Dynamically builds a ReplyKeyboard for selecting a panel to manage."""
    # Local import to prevent circular dependency issues
    from database.crud import panel_credential as crud_panel
    

    all_panels = await crud_panel.get_all_panels()
    
    keyboard = []
    # Create buttons for each panel, arranged 2 per row
    it = iter(all_panels)
    for panel1 in it:
        row = [KeyboardButton(panel1.name)]
        try:
            panel2 = next(it)
            row.append(KeyboardButton(panel2.name))
        except StopIteration:
            pass
        keyboard.append(row)
        
    # Add the static "Back" button at the end
    keyboard.append([KeyboardButton(translator.get("keyboards.panel_management.back_to_main_menu"))])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ADD THIS NEW FUNCTION
def get_panel_type_selection_keyboard() -> InlineKeyboardMarkup:
    """Creates the InlineKeyboardMarkup for selecting a panel type to add."""
    keyboard = [
        [InlineKeyboardButton("M A R Z B A N", callback_data="add_panel_type_marzban")],
        # Add other panel types here in the future
        # [InlineKeyboardButton("X - U I", callback_data="add_panel_type_xui")],
        [InlineKeyboardButton(_("buttons.cancel"), callback_data="cancel_add_panel")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_user_management_keyboard() -> ReplyKeyboardMarkup:
    """The main keyboard for managing users of a specific, selected panel."""
    

    keyboard = [
        [KeyboardButton(translator.get("keyboards.user_management.show_users")), KeyboardButton(translator.get("keyboards.user_management.expiring_users"))],
        [KeyboardButton(translator.get("keyboards.user_management.add_user"))],
        [KeyboardButton(translator.get("keyboards.user_management.back_to_panel_selection"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_settings_and_tools_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.settings_and_tools.panel_management"))],
        [KeyboardButton(_("keyboards.settings_and_tools.bot_settings")), KeyboardButton(_("keyboards.settings_and_tools.financial_settings"))],
        [KeyboardButton(_("keyboards.settings_and_tools.set_log_channel"))],
        [KeyboardButton(_("keyboards.settings_and_tools.helper_tools")), KeyboardButton(_("keyboards.settings_and_tools.bot_stats"))],
        [KeyboardButton(_("keyboards.settings_and_tools.back_to_main_menu"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_helper_tools_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [

        [KeyboardButton(_("keyboards.helper_tools.daily_automation"))],
        [KeyboardButton(_("keyboards.helper_tools.set_forced_join_channel"))],
        [KeyboardButton(_("keyboards.helper_tools.create_connect_link")), KeyboardButton(_("keyboards.helper_tools.test_account_settings"))],
        [KeyboardButton(_("keyboards.helper_tools.back_to_settings"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def get_customer_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    bot_settings = await crud_bot_setting.load_bot_settings()
    is_wallet_enabled = bot_settings.get('is_wallet_enabled', False)
    
    keyboard_layout = [
        [KeyboardButton(_("keyboards.customer_main_menu.shop"))],
        [
            KeyboardButton(_("keyboards.customer_main_menu.my_services")),
            KeyboardButton(_("keyboards.customer_main_menu.test_account"))
        ]
    ]
    
    # Third row: Wallet and Connection Guide
    third_row = []
    if is_wallet_enabled:
        third_row.append(KeyboardButton(_("keyboards.customer_main_menu.wallet_charge")))
    
    third_row.append(KeyboardButton(_("keyboards.customer_main_menu.connection_guide")))
    
    if third_row:
        keyboard_layout.append(third_row)

    # Last row for Support, if enabled
    if config.SUPPORT_USERNAME:
        keyboard_layout.append([KeyboardButton(_("keyboards.customer_main_menu.support"))])
    
    return ReplyKeyboardMarkup(keyboard_layout, resize_keyboard=True)

def get_customer_shop_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.customer_shop.assisted_purchase"))],
        [KeyboardButton(_("keyboards.customer_shop.custom_volume_plan")), KeyboardButton(_("keyboards.customer_shop.unlimited_volume_plan"))],
        [KeyboardButton(_("keyboards.customer_shop.send_receipt"))],
        [KeyboardButton(_("keyboards.customer_shop.back_to_main_menu"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_back_to_main_menu_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.general.back_to_main_menu"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def get_customer_view_for_admin_keyboard() -> ReplyKeyboardMarkup:
    bot_settings = await crud_bot_setting.load_bot_settings()
    is_wallet_enabled = bot_settings.get('is_wallet_enabled', False)

    # --- FIX: All keys now use the 'keyboards.' namespace ---
    keyboard_layout = [
        [KeyboardButton(_("keyboards.customer_main_menu.shop"))]
    ]
    second_row = [
        KeyboardButton(_("keyboards.customer_main_menu.my_services")),
        KeyboardButton(_("keyboards.customer_main_menu.test_account"))
    ]
    keyboard_layout.append(second_row)
    if is_wallet_enabled: 
        keyboard_layout.append([KeyboardButton(_("keyboards.customer_main_menu.wallet_charge"))])
    last_row = [KeyboardButton(_("keyboards.customer_main_menu.connection_guide"))]
    if config.SUPPORT_USERNAME:
        last_row.append(KeyboardButton(_("keyboards.customer_main_menu.support")))
    keyboard_layout.append(last_row)
    # --- FIX: Added 'keyboards.' namespace ---
    keyboard_layout.append([KeyboardButton(_("keyboards.general.back_to_admin_panel"))])
    
    return ReplyKeyboardMarkup(keyboard_layout, resize_keyboard=True)

def get_notes_management_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.notes_management.daily_notes")), KeyboardButton(_("keyboards.notes_management.registered_subscriptions"))],
        [KeyboardButton(_("keyboards.notes_management.back_to_main_menu"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def get_financial_settings_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.financial_settings.payment_settings")), KeyboardButton(_("keyboards.financial_settings.sales_plan_management"))],
        [KeyboardButton(_("keyboards.financial_settings.back_to_settings"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# FILE: shared/keyboards.py

def get_broadcaster_menu_keyboard() -> ReplyKeyboardMarkup:
    """Creates the ReplyKeyboardMarkup for the new broadcaster module."""
    keyboard = [
        # Row 1: Forward All
        [KeyboardButton(_("keyboards.broadcaster_menu.send_forward_all"))],
        
        # Row 2: Custom Single | Custom All
        [
            KeyboardButton(_("keyboards.broadcaster_menu.send_custom_single")),
            KeyboardButton(_("keyboards.broadcaster_menu.send_custom_all"))
        ],
        
        # Row 3: Back to Main Menu
        [KeyboardButton(_("keyboards.general.back_to_main_menu"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


# =============================================================================
#  InlineKeyboardMarkup Section
# =============================================================================

def get_payment_methods_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.payment_methods.set_card_info"), callback_data="admin_set_card_info"),
            InlineKeyboardButton(_("keyboards.inline_keyboards.payment_methods.set_payment_gateway"), callback_data="coming_soon")
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.payment_methods.set_crypto"), callback_data="coming_soon")
        ],
        [InlineKeyboardButton(_("keyboards.inline_keyboards.payment_methods.back_to_financial_settings"), callback_data="back_to_financial_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_plan_management_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.plan_management.manage_unlimited"), callback_data="admin_manage_unlimited"),
            InlineKeyboardButton(_("keyboards.inline_keyboards.plan_management.manage_volumetric"), callback_data="admin_manage_volumetric")
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.plan_management.set_plan_names"), callback_data="admin_set_plan_names")
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.plan_management.back_to_financial_settings"), callback_data="back_to_financial_settings")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_to_management_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        # --- FIX: All keys now use the 'keyboards.' namespace ---
        [KeyboardButton(_("keyboards.helper_tools.back_to_management_menu"))],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def get_test_account_settings_keyboard() -> InlineKeyboardMarkup:
    bot_settings = await crud_bot_setting.load_bot_settings()
    is_enabled = bot_settings.get('is_test_account_enabled', False)
    
    # --- FIX: All keys now use the 'keyboards.' namespace ---
    toggle_text = _("keyboards.inline_keyboards.test_account_settings.disable") if is_enabled else _("keyboards.inline_keyboards.test_account_settings.enable")
    toggle_callback = "admin_test_acc_disable" if is_enabled else "admin_test_acc_enable"
    
    keyboard = [
        [
            InlineKeyboardButton(toggle_text, callback_data=toggle_callback)
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.test_account_settings.set_volume"), callback_data="admin_test_acc_set_gb"),
            InlineKeyboardButton(_("keyboards.inline_keyboards.test_account_settings.set_duration"), callback_data="admin_test_acc_set_hours")
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.test_account_settings.set_limit"), callback_data="admin_test_acc_set_limit")
        ],
        [
            InlineKeyboardButton(_("keyboards.inline_keyboards.test_account_settings.back_to_tools"), callback_data="admin_test_acc_back")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_connection_guide_keyboard(is_for_test_account_expired: bool = False) -> InlineKeyboardMarkup:
    """
    Creates an inline keyboard.
    If `is_for_test_account_expired` is True, it shows a "Buy Subscription" button.
    Otherwise, it shows a "Connection Guides" button.
    """
    if is_for_test_account_expired:
        button = InlineKeyboardButton(
            _("general.buy_subscription_button"), 
            callback_data="customer_shop"
        )
    else:
        button = InlineKeyboardButton(
            _("keyboards.inline_keyboards.general.connection_guide"), 
            callback_data="show_connection_guides"
        )
        
    keyboard = [[button]]
    return InlineKeyboardMarkup(keyboard)

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Creates a standard cancel/back keyboard for conversations."""
    keyboard = [
        # (✨ FIX) This key now correctly matches the handler's expectation.
        [KeyboardButton(_("keyboards.helper_tools.back_to_helper_tools"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# --- ✨ NEW FUNCTION ADDED HERE ✨ ---
def get_balance_management_keyboard() -> ReplyKeyboardMarkup:
    """
    Creates a dedicated ReplyKeyboard for the balance management conversation.
    This allows for a quick exit from the conversation.
    """
    keyboard = [
        [KeyboardButton(_("keyboards.financials.balance_management_back_button"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
# --- ✨ END OF NEW FUNCTION ✨ ---

# (✨ NEW FUNCTION FOR GIFT MANAGEMENT)
def get_gift_management_keyboard() -> InlineKeyboardMarkup:
    """
    Creates the inline keyboard for the gift management menu.
    """
    keyboard = [
        [
            InlineKeyboardButton(
                _("keyboards.inline_keyboards.gift_management.set_welcome_gift"), 
                callback_data="admin_gift_set_welcome"
            )
        ],
        [
            InlineKeyboardButton(
                _("keyboards.inline_keyboards.gift_management.send_universal_gift"), 
                callback_data="admin_gift_send_universal"
            )
        ],
        [
            InlineKeyboardButton(
                _("keyboards.inline_keyboards.gift_management.back_to_financial_settings"), 
                callback_data="back_to_financial_settings"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)



def get_message_builder_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Creates a ReplyKeyboard with a single button to cancel the message builder."""
    keyboard = [
        [KeyboardButton(_("keyboards.broadcaster_menu.cancel_and_back"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

def get_deeplink_targets_keyboard() -> InlineKeyboardMarkup:
    """Creates an InlineKeyboard with all available deeplink targets."""
    keyboard = [
        # Main Menu Targets
        [
            InlineKeyboardButton(_("keyboards.deeplink_targets.shop"), callback_data="customer_shop"),
            InlineKeyboardButton(_("keyboards.deeplink_targets.my_services"), callback_data="customer_my_services")
        ],
        # Shop Sub-targets
        [
            InlineKeyboardButton(_("keyboards.deeplink_targets.custom_plan"), callback_data="shop_custom_volume"),
            InlineKeyboardButton(_("keyboards.deeplink_targets.unlimited_plan"), callback_data="shop_unlimited_volume")
        ],
        # Other targets
        [
            InlineKeyboardButton(_("keyboards.deeplink_targets.guides"), callback_data="customer_guides"),
            InlineKeyboardButton(_("keyboards.deeplink_targets.test_account"), callback_data="customer_test_account")
        ],
        # Back button
        [
            InlineKeyboardButton(_("keyboards.broadcaster_menu.back_to_button_type"), callback_data="builder_back_to_btn_type")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

# --- END OF FILE shared/keyboards.py (REVISED AND COMPLETE) ---

# FILE: shared/keyboards.py (ADD THIS FUNCTION TO THE END)

from math import ceil

def build_paginated_keyboard(
    items: list,
    page: int,
    items_per_page: int,
    item_text_formatter: callable,
    item_callback_formatter: callable,
    page_callback_prefix: str,
    extra_buttons: list = None
) -> InlineKeyboardMarkup:
    """
    A generic function to build a paginated inline keyboard.

    Args:
        items (list): The full list of items to paginate.
        page (int): The current page number (1-based).
        items_per_page (int): Number of items to show per page.
        item_text_formatter (callable): A function that takes an item and returns the text for its button.
        item_callback_formatter (callable): A function that takes an item and returns the callback data for its button.
        page_callback_prefix (str): The prefix for page navigation callbacks (e.g., 'show_users_page_all').
        extra_buttons (list, optional): A list of extra InlineKeyboardButton rows to add at the end.

    Returns:
        InlineKeyboardMarkup: The generated paginated keyboard.
    """
    total_pages = ceil(len(items) / items_per_page)
    page = max(1, min(page, total_pages))  # Ensure page is within valid range
    start_index = (page - 1) * items_per_page
    page_items = items[start_index : start_index + items_per_page]
    
    keyboard = []
    
    # Create rows with 2 items each
    it = iter(page_items)
    for item1 in it:
        row = [InlineKeyboardButton(item_text_formatter(item1), callback_data=item_callback_formatter(item1))]
        try:
            item2 = next(it)
            row.append(InlineKeyboardButton(item_text_formatter(item2), callback_data=item_callback_formatter(item2)))
        except StopIteration:
            pass
        keyboard.append(row)

    # Navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton(_("keyboards.buttons.pagination_prev"), callback_data=f"{page_callback_prefix}_{page - 1}"))
    if total_pages > 1:
        nav_row.append(InlineKeyboardButton(_("keyboards.buttons.pagination_page", current=page, total=total_pages), callback_data="noop"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton(_("keyboards.buttons.pagination_next"), callback_data=f"{page_callback_prefix}_{page + 1}"))

    if nav_row:
        keyboard.append(nav_row)

    # Add any extra buttons provided
    if extra_buttons:
        for btn_row in extra_buttons:
            keyboard.append(btn_row)
            
    return InlineKeyboardMarkup(keyboard)

# --- START: Replace `get_panel_management_keyboard` in keyboards.py ---
async def get_panel_management_keyboard() -> ReplyKeyboardMarkup:
    """Dynamically builds a ReplyKeyboard with all panel names and control buttons."""
    # Local import to prevent circular dependency issues at startup
    from database.crud import panel_credential as crud_panel 
    
    all_panels = await crud_panel.get_all_panels()
    
    keyboard = []
    # Create buttons for each panel, arranged 2 per row
    it = iter(all_panels)
    for panel1 in it:
        row = [KeyboardButton(panel1.name)]
        try:
            panel2 = next(it)
            row.append(KeyboardButton(panel2.name))
        except StopIteration:
            pass
        keyboard.append(row)
        
    # Add the static control buttons at the end
    keyboard.append([KeyboardButton(_("keyboards.panel_management.add_panel"))])
    keyboard.append([KeyboardButton(_("keyboards.panel_management.back_to_settings"))])
    
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
# --- END: Replacement ---

# ADD THIS to the ReplyKeyboardMarkup section
def get_single_panel_management_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(_("keyboards.single_panel_management.connection_status")), KeyboardButton(_("keyboards.single_panel_management.delete_panel"))],
        [KeyboardButton(_("keyboards.single_panel_management.back_to_list"))]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
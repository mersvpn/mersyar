# FILE: modules/marzban/actions/helpers.py (NEW FILE)

import datetime
from typing import Tuple, Dict, Any
from core.panel_api.base import PanelAPI
from .constants import GB_IN_BYTES

async def add_days_to_user(api: PanelAPI, username: str, days_to_add: int) -> Tuple[bool, str]:
    """Extends a user's subscription using the provided API object."""
    current_data = await api.get_user_data(username)
    if not current_data:
        return False, f"User '{username}' not found."
        
    current_expire_ts = current_data.get('expire')
    now_ts = int(datetime.datetime.now().timestamp())
    start_ts = current_expire_ts if current_expire_ts and current_expire_ts > now_ts else now_ts
    
    start_date = datetime.datetime.fromtimestamp(start_ts)
    new_expire_date = start_date + datetime.timedelta(days=days_to_add)
    
    settings = {"expire": int(new_expire_date.timestamp())}
    return await api.modify_user(username, settings)

async def add_data_to_user(api: PanelAPI, username: str, data_gb: int) -> Tuple[bool, str]:
    """Adds data to a user's limit using the provided API object."""
    current_data = await api.get_user_data(username)
    if not current_data:
        return False, f"User '{username}' not found."
        
    current_limit_bytes = current_data.get('data_limit', 0)
    new_limit_bytes = current_limit_bytes + (data_gb * GB_IN_BYTES)
    
    settings = {"data_limit": new_limit_bytes}
    return await api.modify_user(username, settings)

async def renew_user_subscription(api: PanelAPI, username: str, days_to_add: int) -> Tuple[bool, str]:
    """Renews a user's subscription (resets traffic and adds days) using the API object."""
    current_data = await api.get_user_data(username)
    if not current_data:
        return False, f"User '{username}' not found."
        
    current_expire_ts = current_data.get('expire')
    now_ts = int(datetime.datetime.now().timestamp())
    start_ts = current_expire_ts if current_expire_ts and current_expire_ts > now_ts else now_ts
    
    start_date = datetime.datetime.fromtimestamp(start_ts)
    new_expire_date = start_date + datetime.timedelta(days=days_to_add)
    
    settings = {
        "expire": int(new_expire_date.timestamp()),
        "used_traffic": 0
    }
    return await api.modify_user(username, settings)

async def format_user_info_for_customer(api: PanelAPI, username: str) -> str:
    """Formats user data into a user-friendly message, using the API object."""
    from shared.translator import _
    
    user_data = await api.get_user_data(username)
    if not user_data:
        return _("marzban.marzban_display.user_not_found")

    used_traffic = user_data.get('used_traffic', 0)
    data_limit = user_data.get('data_limit', 0)
    used_gb = used_traffic / GB_IN_BYTES
    total_gb = data_limit / GB_IN_BYTES
    
    usage_text = f"{total_gb:.2f} GB" if data_limit != 0 else _('marzban.marzban_display.unlimited')

    expire_ts = user_data.get('expire')
    if not expire_ts or expire_ts == 0:
        expiry_text = _("marzban.marzban_display.unlimited")
    else:
        days_left = (datetime.datetime.fromtimestamp(expire_ts) - datetime.datetime.now()).days
        expiry_text = f"{days_left} روز" if days_left >= 0 else _("marzban.marzban_display.expired")
    
    sub_url = user_data.get('subscription_url', _('marzban.marzban_display.sub_link_not_found'))
    
    message = _("marzban.marzban_add_user.customer_message_title")
    message += _("marzban.marzban_add_user.customer_message_username", username=f"`{username}`")
    message += _("marzban.marzban_add_user.customer_message_datalimit", datalimit=usage_text)
    message += _("marzban.marzban_add_user.customer_message_duration", duration=expiry_text)
    message += _("marzban.marzban_add_user.customer_message_sub_link", url=sub_url)
    message += _("marzban.marzban_add_user.customer_message_guide")
    
    return message
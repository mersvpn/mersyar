# FILE: core/panel_api/marzban.py (NEW FILE)

import httpx
import logging
import asyncio
from typing import Tuple, Dict, Any, Optional, Union, List

from .base import PanelAPI

LOGGER = logging.getLogger(__name__)

# This client is now specific to Marzban API calls
_client = httpx.AsyncClient(timeout=20.0, http2=True)

class MarzbanPanel(PanelAPI):
    """Implementation of the PanelAPI interface for Marzban panels."""

    async def _get_token(self) -> Optional[str]:
        """Gets an authentication token from the Marzban API."""
        url = f"{self.api_url}/api/admin/token"
        payload = {'username': self.username, 'password': self.password}
        
        for attempt in range(3):
            try:
                response = await _client.post(url, data=payload)
                response.raise_for_status()
                return response.json().get("access_token")
            except (httpx.RequestError, httpx.HTTPStatusError) as e:
                LOGGER.warning(f"Attempt {attempt + 1}/3 to get Marzban token for {self.api_url} failed: {e}.")
                await asyncio.sleep(1)
        return None

    async def _api_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Performs a generic API request to the Marzban panel."""
        token = await self._get_token()
        if not token:
            return {"error": "Authentication failed"}
        
        url = f"{self.api_url}{endpoint}"
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop('headers', {})}

        for attempt in range(3):
            try:
                response = await _client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {"success": True}
            except httpx.HTTPStatusError as e:
                if 500 <= e.response.status_code < 600:
                    await asyncio.sleep(attempt + 1)
                    continue
                error_detail = e.response.json().get("detail", "Client error")
                return {"error": error_detail, "status_code": e.response.status_code}
            except httpx.RequestError:
                await asyncio.sleep(attempt + 1)
        
        return {"error": "Network error or persistent server issue"}

    async def get_all_users(self) -> Optional[List[Dict[str, Any]]]:
        response = await self._api_request("GET", "/api/users", timeout=40.0)
        return response.get("users") if "error" not in response else None

    async def get_user_data(self, username: str) -> Optional[Dict[str, Any]]:
        if not username: return None
        response = await self._api_request("GET", f"/api/user/{username}")
        return response if "error" not in response else None

    async def create_user(self, payload: dict) -> Tuple[bool, Any]:
        response = await self._api_request("POST", "/api/user", json=payload)
        if "error" not in response:
            return True, response
        return False, response.get("error", "Unknown error")

    async def delete_user(self, username: str) -> Tuple[bool, str]:
        response = await self._api_request("DELETE", f"/api/user/{username}")
        if "error" not in response:
            return True, "User deleted successfully."
        return False, response.get("error", "Unknown error")

    async def modify_user(self, username: str, settings: dict) -> Tuple[bool, str]:
        current_data = await self.get_user_data(username)
        if not current_data:
            return False, f"User '{username}' not found."
        
        for key in ['online_at', 'created_at', 'subscription_url', 'usages']:
            current_data.pop(key, None)
        
        updated_payload = {**current_data, **settings}
        
        response = await self._api_request("PUT", f"/api/user/{username}", json=updated_payload)
        
        if "error" not in response:
            return True, "User updated successfully."
        return False, response.get("error", "Unknown error")
    
    async def reset_user_traffic(self, username: str) -> Tuple[bool, str]:
        response = await self._api_request("POST", f"/api/user/{username}/reset")
        if "error" not in response:
            return True, "Traffic reset successfully."
        return False, response.get("error", "Unknown error")

    async def close_marzban_client():
        """Closes the shared httpx client for Marzban."""
        if not _client.is_closed:
            await _client.aclose()
            LOGGER.info("Marzban HTTPX client has been closed.")

    # در انتهای کلاس MarzbanPanel در فایل core/panel_api/marzban.py

    async def revoke_subscription(self, username: str) -> Tuple[bool, Any]:
        """Revokes and regenerates the subscription link for a user."""
        response = await self._api_request("POST", f"/api/user/{username}/revoke_sub")
        if "error" not in response:
            return True, response
        return False, response.get("error", "Unknown error")
    
    # ADD THIS METHOD TO THE END OF THE MarzbanPanel CLASS
    async def revoke_subscription(self, username: str) -> Tuple[bool, Any]:
        """Revokes and regenerates the subscription link for a user."""
        response = await self._api_request("POST", f"/api/user/{username}/revoke_sub")
        if "error" not in response:
            return True, response
        return False, response.get("error", "Unknown error")
    
    # ADD THIS FUNCTION TO THE END OF core/panel_api/marzban.py

async def close_marzban_client():
    """Closes the shared httpx client for Marzban."""
    if not _client.is_closed:
        await _client.aclose()
        LOGGER.info("Marzban HTTPX client has been closed.")
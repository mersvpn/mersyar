# FILE: core/panel_api/base.py (NEW FILE)
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple

class PanelAPI(ABC):
    """
    An abstract base class (interface) for all panel API wrappers.
    Defines the standard methods that every panel implementation must have.
    """
    def __init__(self, credentials: Dict[str, Any]):
        self.credentials = credentials
        self.api_url = credentials['api_url']
        self.username = credentials['username']
        self.password = credentials['password']

    @abstractmethod
    async def get_all_users(self) -> Optional[List[Dict[str, Any]]]:
        pass

    @abstractmethod
    async def get_user_data(self, username: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def create_user(self, payload: dict) -> Tuple[bool, Any]:
        pass

    @abstractmethod
    async def delete_user(self, username: str) -> Tuple[bool, str]:
        pass

    @abstractmethod
    async def modify_user(self, username: str, settings: dict) -> Tuple[bool, str]:
        pass
    
    @abstractmethod
    async def reset_user_traffic(self, username: str) -> Tuple[bool, str]:
        pass

    @abstractmethod
    async def revoke_subscription(self, username: str) -> Tuple[bool, Any]:
        pass
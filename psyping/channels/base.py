from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional

class BaseChannel(ABC):
    @property
    @abstractmethod
    def channel_id(self) -> str:
        pass

    @abstractmethod
    async def deliver(self, log_id: str, text: str, category: str, settings: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Deliver message via this channel.
        Returns (success: bool, error_message: Optional[str])
        """
        pass

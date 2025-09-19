"""Tool provider interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...types.tools import AgentTool


class ToolProvider(ABC):
    """Interface for providing tools with lifecycle management.

    Provides a way to load a collection of tools and clean them up
    when done, without requiring context manager syntax.
    """

    @abstractmethod
    async def load_tools(self) -> list["AgentTool"]:
        """Load and return the tools in this provider.

        Returns:
            List of tools that are ready to use.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources used by the tools in this provider.

        Should be called when the tools are no longer needed.
        """
        pass

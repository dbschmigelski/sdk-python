"""Null implementation of conversation management."""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ...agent.agent import Agent

from ...types.exceptions import ContextWindowOverflowException, MaxTokensReachedException
from .conversation_manager import ConversationManager


class NullConversationManager(ConversationManager):
    """A no-op conversation manager that does not modify the conversation history.

    Useful for:

    - Testing scenarios where conversation management should be disabled
    - Cases where conversation history is managed externally
    - Situations where the full conversation history should be preserved
    """

    def apply_management(self, agent: "Agent", **kwargs: Any) -> None:
        """Does nothing to the conversation history.

        Args:
            agent: The agent whose conversation history will remain unmodified.
            **kwargs: Additional keyword arguments for future extensibility.
        """
        pass

    def reduce_context(self, agent: "Agent", e: Optional[Exception] = None, **kwargs: Any) -> None:
        """Does not reduce context and raises an exception.

        Args:
            agent: The agent whose conversation history will remain unmodified.
            e: The exception that triggered the context reduction, if any.
            **kwargs: Additional keyword arguments for future extensibility.

        Raises:
            e: If provided.
            ContextWindowOverflowException: If e is None.
        """
        if e:
            raise e
        else:
            raise ContextWindowOverflowException("Context window overflowed!")

    def handle_token_limit_reached(self, agent: "Agent", e: MaxTokensReachedException, **kwargs: Any) -> None:
        """Does not handle token limit recovery and raises the exception.

        Args:
            agent: The agent whose conversation state will remain unmodified.
            e: The MaxTokensReachedException that triggered the recovery.
            **kwargs: Additional keyword arguments for future extensibility.

        Raises:
            e: The provided exception.
        """
        raise e

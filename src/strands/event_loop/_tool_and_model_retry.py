"""Combined retry strategy for both model and tool execution failures.

This module provides a unified retry strategy that handles retries for both
model calls (throttling, transient errors) and tool calls (failures, timeouts).
"""

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from ..hooks.events import AfterInvocationEvent, AfterModelCallEvent, AfterToolCallEvent
from ..hooks.registry import HookProvider, HookRegistry
from ..types._events import EventLoopThrottleEvent
from ..types.exceptions import ModelThrottledException

logger = logging.getLogger(__name__)


class ToolAndModelRetryStrategy(HookProvider):
    """Unified retry strategy for model and tool execution failures.

    Handles retries for both model calls (on throttling) and tool calls (on failures)
    using exponential backoff. Model retries are enabled by default for backwards
    compatibility; tool retries are disabled by default (opt-in).

    Model Retry Behavior:
        Retries model calls when ModelThrottledException is raised. Delay doubles after
        each attempt: model_initial_delay, model_initial_delay*2, etc., capped at
        model_max_delay.

    Tool Retry Behavior:
        When tool_max_attempts > 0, retries tool calls on exceptions or error status
        results. Supports per-tool configuration and filtering via enabled/disabled lists.
        State is tracked per tool_use_id to support concurrent executions.

    Args:
        model_max_attempts: Total model call attempts before giving up. Defaults to 6.
        model_initial_delay: Base delay in seconds for model retries. Defaults to 4.0.
        model_max_delay: Upper bound in seconds for model retry backoff. Defaults to 240.0.
        tool_max_attempts: Total tool execution attempts before giving up. Defaults to 0
            (tool retries disabled). Set to > 0 to enable tool retries.
        tool_initial_delay: Base delay in seconds for tool retries. Defaults to 1.0.
        tool_max_delay: Upper bound in seconds for tool retry backoff. Defaults to 30.0.
        tool_should_retry: Optional predicate to determine if a tool error should trigger
            a retry. Receives the exception (or RuntimeError for error status results)
            and returns True to retry. If not provided, all tool errors trigger retries.
        tool_configs: Optional per-tool configuration overrides. Keys are tool names,
            values are dicts with optional keys: max_attempts, initial_delay, max_delay.
        tool_enabled_tools: Optional list of tool names to enable retries for. If provided,
            only these tools will be retried. Mutually exclusive with tool_disabled_tools.
        tool_disabled_tools: Optional list of tool names to disable retries for. If provided,
            these tools will not be retried. Mutually exclusive with tool_enabled_tools.
    """

    def __init__(
        self,
        *,
        # Model retry settings (enabled by default)
        model_max_attempts: int = 6,
        model_initial_delay: float = 4.0,
        model_max_delay: float = 240.0,
        # Tool retry settings (disabled by default - set tool_max_attempts > 0 to enable)
        tool_max_attempts: int = 0,
        tool_initial_delay: float = 1.0,
        tool_max_delay: float = 30.0,
        tool_should_retry: Callable[[Exception], bool] | None = None,
        tool_configs: dict[str, dict[str, Any]] | None = None,
        tool_enabled_tools: list[str] | None = None,
        tool_disabled_tools: list[str] | None = None,
    ):
        """Initialize the combined retry strategy.

        Args:
            model_max_attempts: Total model call attempts before giving up. Defaults to 6.
            model_initial_delay: Base delay in seconds for model retries. Defaults to 4.0.
            model_max_delay: Upper bound in seconds for model retry backoff. Defaults to 240.0.
            tool_max_attempts: Total tool execution attempts before giving up. Defaults to 0
                (tool retries disabled). Set to > 0 to enable tool retries.
            tool_initial_delay: Base delay in seconds for tool retries. Defaults to 1.0.
            tool_max_delay: Upper bound in seconds for tool retry backoff. Defaults to 30.0.
            tool_should_retry: Optional predicate to determine if a tool error should trigger
                a retry. Receives the exception and returns True to retry.
            tool_configs: Optional per-tool configuration overrides.
            tool_enabled_tools: Optional list of tool names to enable retries for.
            tool_disabled_tools: Optional list of tool names to disable retries for.

        Raises:
            ValueError: If both tool_enabled_tools and tool_disabled_tools are provided.
        """
        if tool_enabled_tools is not None and tool_disabled_tools is not None:
            raise ValueError("Cannot specify both tool_enabled_tools and tool_disabled_tools")

        # Model retry state
        self._model_max_attempts = model_max_attempts
        self._model_initial_delay = model_initial_delay
        self._model_max_delay = model_max_delay
        self._model_current_attempt = 0

        # Tool retry state
        self._tool_max_attempts = tool_max_attempts
        self._tool_initial_delay = tool_initial_delay
        self._tool_max_delay = tool_max_delay
        self._tool_should_retry = tool_should_retry
        self._tool_configs = tool_configs or {}
        self._tool_enabled_tools = set(tool_enabled_tools) if tool_enabled_tools else None
        self._tool_disabled_tools = set(tool_disabled_tools) if tool_disabled_tools else None
        self._tool_attempts: dict[str, int] = {}

        # For backwards compatibility with event streaming
        self._backwards_compatible_event_to_yield: EventLoopThrottleEvent | None = None

    def register_hooks(self, registry: HookRegistry, **kwargs: Any) -> None:
        """Register callbacks for model and tool retry events.

        Args:
            registry: The hook registry to register callbacks with.
            **kwargs: Additional keyword arguments for future extensibility.
        """
        registry.add_callback(AfterModelCallEvent, self._handle_after_model_call)
        registry.add_callback(AfterToolCallEvent, self._handle_after_tool_call)
        registry.add_callback(AfterInvocationEvent, self._handle_after_invocation)

    # -------------------------------------------------------------------------
    # Model Retry Logic
    # -------------------------------------------------------------------------

    def _calculate_model_delay(self, attempt: int) -> float:
        """Calculate retry delay for model calls using exponential backoff.

        Args:
            attempt: The attempt number (0-indexed).

        Returns:
            Delay in seconds for the given attempt.
        """
        delay: float = self._model_initial_delay * (2**attempt)
        return min(delay, self._model_max_delay)

    async def _handle_after_model_call(self, event: AfterModelCallEvent) -> None:
        """Handle model call completion and determine if retry is needed.

        Args:
            event: The AfterModelCallEvent containing call results or exception.
        """
        # If already retrying, skip processing
        if event.retry:
            return

        # On success, reset state
        if event.stop_response is not None:
            self._model_current_attempt = 0
            self._backwards_compatible_event_to_yield = None
            return

        # Only retry on ModelThrottledException
        if not isinstance(event.exception, ModelThrottledException):
            self._model_current_attempt = 0
            self._backwards_compatible_event_to_yield = None
            return

        # Check if we've exceeded max attempts
        if self._model_current_attempt >= self._model_max_attempts:
            logger.debug(
                "current_attempt=<%d>, max_attempts=<%d> | max model retry attempts reached",
                self._model_current_attempt,
                self._model_max_attempts,
            )
            return

        # Calculate delay and retry
        delay = self._calculate_model_delay(self._model_current_attempt)

        logger.debug(
            "retry_delay_seconds=<%s>, max_attempts=<%s>, current_attempt=<%s> "
            "| model throttled | delaying before next retry",
            delay,
            self._model_max_attempts,
            self._model_current_attempt,
        )

        await asyncio.sleep(delay)

        # Store backwards-compatible event for streaming (EventLoopThrottleEvent expects int)
        self._backwards_compatible_event_to_yield = EventLoopThrottleEvent(delay=int(delay))

        self._model_current_attempt += 1
        event.retry = True

    # -------------------------------------------------------------------------
    # Tool Retry Logic
    # -------------------------------------------------------------------------

    def _get_tool_config(self, tool_name: str) -> tuple[int, float, float]:
        """Get retry configuration for a specific tool.

        Args:
            tool_name: The name of the tool.

        Returns:
            Tuple of (max_attempts, initial_delay, max_delay) for the tool.
        """
        tool_config = self._tool_configs.get(tool_name, {})
        return (
            tool_config.get("max_attempts", self._tool_max_attempts),
            tool_config.get("initial_delay", self._tool_initial_delay),
            tool_config.get("max_delay", self._tool_max_delay),
        )

    def _is_tool_retry_enabled(self, tool_name: str) -> bool:
        """Check if retries are enabled for a specific tool.

        Args:
            tool_name: The name of the tool.

        Returns:
            True if retries are enabled for this tool, False otherwise.
        """
        # First check if tool retries are globally enabled
        if self._tool_max_attempts <= 0:
            # Check if this specific tool has retries configured
            tool_config = self._tool_configs.get(tool_name, {})
            if tool_config.get("max_attempts", 0) <= 0:
                return False

        # Then check enabled/disabled lists
        if self._tool_enabled_tools is not None:
            return tool_name in self._tool_enabled_tools
        if self._tool_disabled_tools is not None:
            return tool_name not in self._tool_disabled_tools
        return True

    def _calculate_tool_delay(self, attempt: int, initial_delay: float, max_delay: float) -> float:
        """Calculate retry delay for tool calls using exponential backoff.

        Args:
            attempt: The attempt number (0-indexed).
            initial_delay: The base delay in seconds.
            max_delay: The maximum delay in seconds.

        Returns:
            Delay in seconds for the given attempt.
        """
        delay: float = initial_delay * (2**attempt)
        return min(delay, max_delay)

    def _is_tool_error_result(self, event: AfterToolCallEvent) -> bool:
        """Check if the tool result indicates an error.

        Args:
            event: The AfterToolCallEvent to check.

        Returns:
            True if the event represents a tool failure, False otherwise.
        """
        if event.exception is not None:
            return True
        if event.result.get("status") == "error":
            return True
        return False

    def _get_tool_error_for_predicate(self, event: AfterToolCallEvent) -> Exception | None:
        """Get an exception object to pass to the should_retry predicate.

        Args:
            event: The AfterToolCallEvent to extract error from.

        Returns:
            An exception object if the event represents an error, None otherwise.
        """
        if event.exception is not None:
            return event.exception

        if event.result.get("status") == "error":
            content = event.result.get("content", [])
            error_text = ""
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    error_text = item["text"]
                    break
            return RuntimeError(error_text or "Tool returned error status")

        return None

    async def _handle_after_tool_call(self, event: AfterToolCallEvent) -> None:
        """Handle tool call completion and determine if retry is needed.

        Args:
            event: The AfterToolCallEvent containing call results or exception.
        """
        tool_use_id = str(event.tool_use.get("toolUseId", ""))
        tool_name = event.tool_use.get("name", "")

        # If already retrying, skip processing
        if event.retry:
            return

        # Check if retries are enabled for this tool
        if not self._is_tool_retry_enabled(tool_name):
            return

        # Get tool-specific configuration
        max_attempts, initial_delay, max_delay = self._get_tool_config(tool_name)

        # Get current attempt count
        current_attempt = self._tool_attempts.get(tool_use_id, 0)

        # If tool call succeeded, clean up state
        if not self._is_tool_error_result(event):
            if tool_use_id in self._tool_attempts:
                del self._tool_attempts[tool_use_id]
            return

        # Get exception for predicate check
        error = self._get_tool_error_for_predicate(event)

        # Check if error should trigger retry
        if self._tool_should_retry is not None and error is not None and not self._tool_should_retry(error):
            logger.debug(
                "tool_name=<%s>, tool_use_id=<%s> | should_retry predicate returned False",
                tool_name,
                tool_use_id,
            )
            return

        # Increment attempt counter
        current_attempt += 1
        self._tool_attempts[tool_use_id] = current_attempt

        # Check if we've exceeded max attempts
        if current_attempt >= max_attempts:
            logger.debug(
                "current_attempt=<%d>, max_attempts=<%d>, tool_name=<%s> | max tool retry attempts reached",
                current_attempt,
                max_attempts,
                tool_name,
            )
            return

        # Calculate delay and retry
        delay = self._calculate_tool_delay(current_attempt - 1, initial_delay, max_delay)

        logger.debug(
            "retry_delay_seconds=<%s>, max_attempts=<%s>, current_attempt=<%s>, tool_name=<%s> "
            "| tool error | delaying before next retry",
            delay,
            max_attempts,
            current_attempt,
            tool_name,
        )

        await asyncio.sleep(delay)
        event.retry = True

    # -------------------------------------------------------------------------
    # Common Logic
    # -------------------------------------------------------------------------

    def _reset_state(self) -> None:
        """Reset all retry state to initial values."""
        self._model_current_attempt = 0
        self._backwards_compatible_event_to_yield = None
        self._tool_attempts.clear()

    async def _handle_after_invocation(self, event: AfterInvocationEvent) -> None:
        """Reset retry state after invocation completes.

        Args:
            event: The AfterInvocationEvent signaling invocation completion.
        """
        self._reset_state()

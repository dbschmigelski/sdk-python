"""Unit tests for ToolAndModelRetryStrategy tool retry functionality."""

from unittest.mock import Mock

import pytest

from strands import ToolAndModelRetryStrategy
from strands.hooks import AfterInvocationEvent, AfterToolCallEvent, HookRegistry

# ToolAndModelRetryStrategy Initialization Tests


def test_tool_and_model_retry_strategy_init_with_defaults():
    """Test ToolAndModelRetryStrategy initialization with default parameters."""
    strategy = ToolAndModelRetryStrategy()
    # Model defaults
    assert strategy._model_max_attempts == 6
    assert strategy._model_initial_delay == 4.0
    assert strategy._model_max_delay == 240.0
    # Tool defaults (disabled)
    assert strategy._tool_max_attempts == 0
    assert strategy._tool_initial_delay == 1.0
    assert strategy._tool_max_delay == 30.0
    assert strategy._tool_should_retry is None
    assert strategy._tool_configs == {}
    assert strategy._tool_enabled_tools is None
    assert strategy._tool_disabled_tools is None
    assert strategy._tool_attempts == {}


def test_tool_and_model_retry_strategy_init_with_custom_parameters():
    """Test ToolAndModelRetryStrategy initialization with custom parameters."""

    def should_retry(e: Exception) -> bool:
        return isinstance(e, TimeoutError)

    strategy = ToolAndModelRetryStrategy(
        model_max_attempts=3,
        model_initial_delay=2.0,
        model_max_delay=60.0,
        tool_max_attempts=5,
        tool_initial_delay=1.5,
        tool_max_delay=45.0,
        tool_should_retry=should_retry,
        tool_configs={"my_tool": {"max_attempts": 10}},
        tool_enabled_tools=["tool1", "tool2"],
    )
    # Model settings
    assert strategy._model_max_attempts == 3
    assert strategy._model_initial_delay == 2.0
    assert strategy._model_max_delay == 60.0
    # Tool settings
    assert strategy._tool_max_attempts == 5
    assert strategy._tool_initial_delay == 1.5
    assert strategy._tool_max_delay == 45.0
    assert strategy._tool_should_retry is should_retry
    assert strategy._tool_configs == {"my_tool": {"max_attempts": 10}}
    assert strategy._tool_enabled_tools == {"tool1", "tool2"}
    assert strategy._tool_disabled_tools is None


def test_tool_and_model_retry_strategy_init_with_disabled_tools():
    """Test ToolAndModelRetryStrategy initialization with tool_disabled_tools."""
    strategy = ToolAndModelRetryStrategy(tool_disabled_tools=["tool1", "tool2"])
    assert strategy._tool_enabled_tools is None
    assert strategy._tool_disabled_tools == {"tool1", "tool2"}


def test_tool_and_model_retry_strategy_init_raises_on_both_enabled_and_disabled():
    """Test that ToolAndModelRetryStrategy raises error when both enabled and disabled tools are specified."""
    with pytest.raises(ValueError, match="Cannot specify both tool_enabled_tools and tool_disabled_tools"):
        ToolAndModelRetryStrategy(tool_enabled_tools=["tool1"], tool_disabled_tools=["tool2"])


# Tool Exponential Backoff Tests


def test_tool_retry_calculate_delay_with_different_attempts():
    """Test _calculate_tool_delay returns correct exponential backoff for different attempt numbers."""
    strategy = ToolAndModelRetryStrategy()

    # Test exponential backoff: initial_delay * (2^attempt)
    assert strategy._calculate_tool_delay(0, 1.0, 16.0) == 1.0  # 1 * 2^0 = 1
    assert strategy._calculate_tool_delay(1, 1.0, 16.0) == 2.0  # 1 * 2^1 = 2
    assert strategy._calculate_tool_delay(2, 1.0, 16.0) == 4.0  # 1 * 2^2 = 4
    assert strategy._calculate_tool_delay(3, 1.0, 16.0) == 8.0  # 1 * 2^3 = 8
    assert strategy._calculate_tool_delay(4, 1.0, 16.0) == 16.0  # 1 * 2^4 = 16 (at max)
    assert strategy._calculate_tool_delay(5, 1.0, 16.0) == 16.0  # 1 * 2^5 = 32, capped at 16


def test_tool_retry_calculate_delay_respects_max_delay():
    """Test _calculate_tool_delay respects max_delay cap."""
    strategy = ToolAndModelRetryStrategy()

    assert strategy._calculate_tool_delay(0, 5.0, 25.0) == 5.0  # 5 * 2^0 = 5
    assert strategy._calculate_tool_delay(1, 5.0, 25.0) == 10.0  # 5 * 2^1 = 10
    assert strategy._calculate_tool_delay(2, 5.0, 25.0) == 20.0  # 5 * 2^2 = 20
    assert strategy._calculate_tool_delay(3, 5.0, 25.0) == 25.0  # 5 * 2^3 = 40, capped at 25


# Tool Configuration Tests


def test_tool_retry_get_tool_config_defaults():
    """Test _get_tool_config returns defaults for unconfigured tool."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_initial_delay=1.0, tool_max_delay=30.0)

    max_attempts, initial_delay, max_delay = strategy._get_tool_config("unconfigured_tool")
    assert max_attempts == 3
    assert initial_delay == 1.0
    assert max_delay == 30.0


def test_tool_retry_get_tool_config_overrides():
    """Test _get_tool_config returns overrides for configured tool."""
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=3,
        tool_initial_delay=1.0,
        tool_max_delay=30.0,
        tool_configs={
            "my_tool": {"max_attempts": 5, "initial_delay": 2.0, "max_delay": 60.0},
            "partial_tool": {"max_attempts": 10},
        },
    )

    # Fully overridden tool
    max_attempts, initial_delay, max_delay = strategy._get_tool_config("my_tool")
    assert max_attempts == 5
    assert initial_delay == 2.0
    assert max_delay == 60.0

    # Partially overridden tool
    max_attempts, initial_delay, max_delay = strategy._get_tool_config("partial_tool")
    assert max_attempts == 10
    assert initial_delay == 1.0  # default
    assert max_delay == 30.0  # default


# Tool Enabled/Disabled Tests


def test_tool_retry_is_enabled_when_disabled_globally():
    """Test _is_tool_retry_enabled returns False when tool retries are disabled globally."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=0)

    assert strategy._is_tool_retry_enabled("any_tool") is False


def test_tool_retry_is_enabled_when_enabled_globally():
    """Test _is_tool_retry_enabled returns True when tool retries are enabled globally."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3)

    assert strategy._is_tool_retry_enabled("any_tool") is True
    assert strategy._is_tool_retry_enabled("another_tool") is True


def test_tool_retry_is_enabled_with_enabled_list():
    """Test _is_tool_retry_enabled with tool_enabled_tools filter."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_enabled_tools=["tool1", "tool2"])

    assert strategy._is_tool_retry_enabled("tool1") is True
    assert strategy._is_tool_retry_enabled("tool2") is True
    assert strategy._is_tool_retry_enabled("tool3") is False


def test_tool_retry_is_enabled_with_disabled_list():
    """Test _is_tool_retry_enabled with tool_disabled_tools filter."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_disabled_tools=["tool1", "tool2"])

    assert strategy._is_tool_retry_enabled("tool1") is False
    assert strategy._is_tool_retry_enabled("tool2") is False
    assert strategy._is_tool_retry_enabled("tool3") is True


def test_tool_retry_is_enabled_via_per_tool_config():
    """Test _is_tool_retry_enabled when globally disabled but per-tool config enables it."""
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=0,  # Globally disabled
        tool_configs={"special_tool": {"max_attempts": 5}},  # But this tool has retries
    )

    assert strategy._is_tool_retry_enabled("special_tool") is True
    assert strategy._is_tool_retry_enabled("other_tool") is False


# Hook Registration Tests


def test_tool_and_model_retry_strategy_register_hooks():
    """Test that ToolAndModelRetryStrategy registers all required callbacks."""
    strategy = ToolAndModelRetryStrategy()
    registry = HookRegistry()

    strategy.register_hooks(registry)

    # Verify AfterToolCallEvent callback was registered
    assert AfterToolCallEvent in registry._registered_callbacks
    assert len(registry._registered_callbacks[AfterToolCallEvent]) == 1

    # Verify AfterInvocationEvent callback was registered
    assert AfterInvocationEvent in registry._registered_callbacks
    assert len(registry._registered_callbacks[AfterInvocationEvent]) == 1


# Tool Retry Behavior Tests


@pytest.mark.asyncio
async def test_tool_retry_on_exception_first_attempt(mock_sleep):
    """Test retry behavior on first tool exception."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_initial_delay=1.0, tool_max_delay=30.0)
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )

    await strategy._handle_after_tool_call(event)

    # Should set retry to True
    assert event.retry is True
    # Should sleep for initial_delay (attempt 0: 1 * 2^0 = 1)
    assert mock_sleep.sleep_calls == [1.0]
    # Should increment attempt
    assert strategy._tool_attempts["test-id"] == 1


@pytest.mark.asyncio
async def test_tool_retry_exponential_backoff(mock_sleep):
    """Test exponential backoff calculation for tool retries."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=5, tool_initial_delay=1.0, tool_max_delay=8.0)
    mock_agent = Mock()

    # Simulate multiple retries
    for _ in range(4):
        event = AfterToolCallEvent(
            agent=mock_agent,
            selected_tool=Mock(),
            tool_use={"toolUseId": "test-id", "name": "test_tool"},
            invocation_state={},
            result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
            exception=Exception("Test error"),
        )
        await strategy._handle_after_tool_call(event)
        assert event.retry is True

    # Verify exponential backoff with max_delay cap
    # attempt 1: 1*2^0=1, attempt 2: 1*2^1=2, attempt 3: 1*2^2=4, attempt 4: 1*2^3=8 (capped)
    assert mock_sleep.sleep_calls == [1.0, 2.0, 4.0, 8.0]


@pytest.mark.asyncio
async def test_tool_retry_no_retry_after_max_attempts(mock_sleep):
    """Test that retry is not set after reaching max_attempts."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=2, tool_initial_delay=1.0, tool_max_delay=30.0)
    mock_agent = Mock()

    # First attempt
    event1 = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )
    await strategy._handle_after_tool_call(event1)
    assert event1.retry is True
    assert strategy._tool_attempts["test-id"] == 1

    # Second attempt (at max_attempts)
    event2 = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )
    await strategy._handle_after_tool_call(event2)
    # Should NOT retry after reaching max_attempts
    assert event2.retry is False
    assert strategy._tool_attempts["test-id"] == 2


@pytest.mark.asyncio
async def test_tool_retry_no_retry_on_success():
    """Test that retry is not set when tool call succeeds."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3)
    mock_agent = Mock()

    # First, simulate a failure to populate attempts
    strategy._tool_attempts["test-id"] = 1

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "success", "content": [{"text": "Success"}]},
        exception=None,
    )

    await strategy._handle_after_tool_call(event)

    # Should not retry on success
    assert event.retry is False
    # Should clean up attempts for this tool_use_id
    assert "test-id" not in strategy._tool_attempts


@pytest.mark.asyncio
async def test_tool_retry_on_error_status(mock_sleep):
    """Test retry behavior when tool returns error status (no exception)."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_initial_delay=1.0, tool_max_delay=30.0)
    mock_agent = Mock()

    # Tool returned error status without raising an exception
    # (common with @tool decorator)
    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error: Something failed"}]},
        exception=None,  # No exception - error is in result status
    )

    await strategy._handle_after_tool_call(event)

    # Should set retry to True
    assert event.retry is True
    # Should sleep for initial_delay
    assert mock_sleep.sleep_calls == [1.0]
    # Should increment attempt
    assert strategy._tool_attempts["test-id"] == 1


@pytest.mark.asyncio
async def test_tool_retry_no_retry_when_predicate_returns_false():
    """Test that retry is not set when should_retry predicate returns False."""

    def only_timeout_errors(e: Exception) -> bool:
        return isinstance(e, TimeoutError)

    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_should_retry=only_timeout_errors)
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=ValueError("Not a timeout"),
    )

    await strategy._handle_after_tool_call(event)

    # Should not retry because predicate returns False
    assert event.retry is False
    assert "test-id" not in strategy._tool_attempts


@pytest.mark.asyncio
async def test_tool_retry_when_predicate_returns_true(mock_sleep):
    """Test that retry is set when should_retry predicate returns True."""

    def only_timeout_errors(e: Exception) -> bool:
        return isinstance(e, TimeoutError)

    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_should_retry=only_timeout_errors)
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=TimeoutError("Timeout"),
    )

    await strategy._handle_after_tool_call(event)

    # Should retry because predicate returns True
    assert event.retry is True
    assert strategy._tool_attempts["test-id"] == 1


@pytest.mark.asyncio
async def test_tool_retry_no_retry_for_disabled_tool():
    """Test that retry is not set for disabled tools."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_disabled_tools=["disabled_tool"])
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "disabled_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )

    await strategy._handle_after_tool_call(event)

    # Should not retry for disabled tool
    assert event.retry is False


@pytest.mark.asyncio
async def test_tool_retry_for_enabled_tool(mock_sleep):
    """Test that retry is set for enabled tools."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_enabled_tools=["enabled_tool"])
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "enabled_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )

    await strategy._handle_after_tool_call(event)

    # Should retry for enabled tool
    assert event.retry is True


@pytest.mark.asyncio
async def test_tool_retry_no_retry_for_non_enabled_tool():
    """Test that retry is not set for tools not in enabled list."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_enabled_tools=["other_tool"])
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "not_enabled"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )

    await strategy._handle_after_tool_call(event)

    # Should not retry for non-enabled tool
    assert event.retry is False


@pytest.mark.asyncio
async def test_tool_retry_per_tool_config(mock_sleep):
    """Test per-tool configuration overrides."""
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=2,
        tool_initial_delay=1.0,
        tool_configs={"special_tool": {"max_attempts": 5, "initial_delay": 2.0}},
    )
    mock_agent = Mock()

    # Test with special_tool that has custom config
    for _ in range(4):
        event = AfterToolCallEvent(
            agent=mock_agent,
            selected_tool=Mock(),
            tool_use={"toolUseId": "special-id", "name": "special_tool"},
            invocation_state={},
            result={"toolUseId": "special-id", "status": "error", "content": [{"text": "Error"}]},
            exception=Exception("Test error"),
        )
        await strategy._handle_after_tool_call(event)
        assert event.retry is True

    # Should use special_tool config (initial_delay=2.0)
    # attempt 1: 2*2^0=2, attempt 2: 2*2^1=4, attempt 3: 2*2^2=8, attempt 4: 2*2^3=16
    assert mock_sleep.sleep_calls == [2.0, 4.0, 8.0, 16.0]
    assert strategy._tool_attempts["special-id"] == 4


@pytest.mark.asyncio
async def test_tool_retry_skips_if_already_retrying():
    """Test that strategy skips processing if event.retry is already True."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3)
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )
    # Simulate another hook already set retry to True
    event.retry = True

    await strategy._handle_after_tool_call(event)

    # Should not modify state since another hook already triggered retry
    assert "test-id" not in strategy._tool_attempts
    assert event.retry is True


@pytest.mark.asyncio
async def test_tool_retry_reset_on_after_invocation():
    """Test that strategy resets state on AfterInvocationEvent."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3)
    mock_agent = Mock()

    # Simulate some retry attempts
    strategy._tool_attempts = {"id1": 2, "id2": 3}
    strategy._model_current_attempt = 2

    event = AfterInvocationEvent(agent=mock_agent, result=Mock())
    await strategy._handle_after_invocation(event)

    # Should reset to initial state
    assert strategy._tool_attempts == {}
    assert strategy._model_current_attempt == 0


@pytest.mark.asyncio
async def test_tool_retry_concurrent_tool_tracking(mock_sleep):
    """Test that strategy tracks attempts per tool_use_id for concurrent executions."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3, tool_initial_delay=1.0)
    mock_agent = Mock()

    # First tool call starts retrying
    event1 = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "id-1", "name": "tool1"},
        invocation_state={},
        result={"toolUseId": "id-1", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Error 1"),
    )
    await strategy._handle_after_tool_call(event1)
    assert event1.retry is True
    assert strategy._tool_attempts["id-1"] == 1

    # Second tool call (different id) starts retrying
    event2 = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "id-2", "name": "tool2"},
        invocation_state={},
        result={"toolUseId": "id-2", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Error 2"),
    )
    await strategy._handle_after_tool_call(event2)
    assert event2.retry is True
    assert strategy._tool_attempts["id-2"] == 1

    # Both tracked independently
    assert strategy._tool_attempts["id-1"] == 1
    assert strategy._tool_attempts["id-2"] == 1

    # First tool succeeds
    event1_success = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "id-1", "name": "tool1"},
        invocation_state={},
        result={"toolUseId": "id-1", "status": "success", "content": [{"text": "Success"}]},
        exception=None,
    )
    await strategy._handle_after_tool_call(event1_success)

    # id-1 should be cleaned up, id-2 should remain
    assert "id-1" not in strategy._tool_attempts
    assert strategy._tool_attempts["id-2"] == 1


@pytest.mark.asyncio
async def test_tool_retry_no_retry_when_globally_disabled():
    """Test that tool retries don't happen when tool_max_attempts is 0."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=0)  # Disabled
    mock_agent = Mock()

    event = AfterToolCallEvent(
        agent=mock_agent,
        selected_tool=Mock(),
        tool_use={"toolUseId": "test-id", "name": "test_tool"},
        invocation_state={},
        result={"toolUseId": "test-id", "status": "error", "content": [{"text": "Error"}]},
        exception=Exception("Test error"),
    )

    await strategy._handle_after_tool_call(event)

    # Should not retry when globally disabled
    assert event.retry is False

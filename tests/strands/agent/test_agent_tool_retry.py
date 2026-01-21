"""Integration tests for Agent tool retry using ToolAndModelRetryStrategy."""

import pytest

from strands import Agent, ToolAndModelRetryStrategy, tool
from strands.hooks import AfterToolCallEvent
from tests.fixtures.mocked_model_provider import MockedModelProvider

# Agent ToolAndModelRetryStrategy Initialization Tests


def test_agent_with_default_retry_strategy_no_tool_retries():
    """Test that Agent uses default ModelRetryStrategy (no tool retries)."""
    agent = Agent()

    # Should have a retry_strategy with model retry defaults
    assert agent._retry_strategy is not None
    assert agent._retry_strategy._max_attempts == 6


def test_agent_with_tool_and_model_retry_strategy():
    """Test Agent initialization with ToolAndModelRetryStrategy."""
    strategy = ToolAndModelRetryStrategy(
        model_max_attempts=3,
        tool_max_attempts=5,
        tool_initial_delay=2.0,
    )
    agent = Agent(retry_strategy=strategy)

    assert agent._retry_strategy is strategy
    assert agent._retry_strategy._model_max_attempts == 3
    assert agent._retry_strategy._tool_max_attempts == 5
    assert agent._retry_strategy._tool_initial_delay == 2.0


def test_agent_rejects_invalid_retry_strategy_type():
    """Test that Agent raises ValueError for invalid retry_strategy type."""

    class FakeRetryStrategy:
        pass

    with pytest.raises(
        ValueError, match="retry_strategy must be an instance of ModelRetryStrategy or ToolAndModelRetryStrategy"
    ):
        Agent(retry_strategy=FakeRetryStrategy())


def test_agent_rejects_subclass_of_tool_and_model_retry_strategy():
    """Test that Agent rejects subclasses of ToolAndModelRetryStrategy (strict type check)."""

    class CustomRetryStrategy(ToolAndModelRetryStrategy):
        pass

    with pytest.raises(
        ValueError, match="retry_strategy must be an instance of ModelRetryStrategy or ToolAndModelRetryStrategy"
    ):
        Agent(retry_strategy=CustomRetryStrategy())


def test_tool_and_model_retry_strategy_registered_as_hook():
    """Test that ToolAndModelRetryStrategy is registered with the hook system."""
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=3)
    agent = Agent(retry_strategy=strategy)

    # Verify retry strategy callback is registered for AfterToolCallEvent
    callbacks = list(
        agent.hooks.get_callbacks_for(
            AfterToolCallEvent(
                agent=agent,
                selected_tool=None,
                tool_use={"toolUseId": "test", "name": "test"},
                invocation_state={},
                result={"toolUseId": "test", "status": "success", "content": []},
            )
        )
    )

    # Should have at least one callback (from tool retry strategy)
    assert len(callbacks) > 0

    # Verify one of the callbacks is from the retry strategy
    assert any(callback.__self__ is strategy if hasattr(callback, "__self__") else False for callback in callbacks)


# Agent Tool Retry Behavior Tests


@pytest.fixture
def failing_tool():
    """Create a tool that fails a configurable number of times before succeeding."""
    call_count = [0]
    fail_times = [2]  # Default: fail twice, then succeed

    @tool(name="failing_tool")
    def _failing_tool(message: str) -> str:
        """A tool that fails a few times before succeeding."""
        call_count[0] += 1
        if call_count[0] <= fail_times[0]:
            raise RuntimeError(f"Simulated failure {call_count[0]}")
        return f"Success on attempt {call_count[0]}: {message}"

    _failing_tool.call_count = call_count
    _failing_tool.fail_times = fail_times
    return _failing_tool


@pytest.mark.asyncio
async def test_agent_retries_tool_on_failure(mock_sleep, failing_tool):
    """Test that Agent retries tool calls when tool retries are enabled."""
    # Mock model that calls the failing tool
    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "test-tool-id", "name": "failing_tool", "input": {"message": "hello"}}}
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    strategy = ToolAndModelRetryStrategy(tool_max_attempts=5, tool_initial_delay=1.0, tool_max_delay=30.0)
    agent = Agent(model=model, tools=[failing_tool], retry_strategy=strategy)

    await agent.invoke_async("call the tool")

    # Tool should have been called 3 times (2 failures + 1 success)
    assert failing_tool.call_count[0] == 3

    # Should have slept twice (for two retries)
    assert len(mock_sleep.sleep_calls) == 2
    # First retry: 1 second (1 * 2^0)
    assert mock_sleep.sleep_calls[0] == 1.0
    # Second retry: 2 seconds (1 * 2^1)
    assert mock_sleep.sleep_calls[1] == 2.0


@pytest.mark.asyncio
async def test_agent_respects_tool_max_attempts(mock_sleep, failing_tool):
    """Test that Agent respects max_attempts in tool retry strategy."""
    failing_tool.fail_times[0] = 10  # Always fail

    # Mock model that calls the failing tool
    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "test-tool-id", "name": "failing_tool", "input": {"message": "hello"}}}
                ],
            },
            {"role": "assistant", "content": [{"text": "Tool failed"}]},
        ]
    )

    # Use strategy with max 2 tool attempts
    strategy = ToolAndModelRetryStrategy(tool_max_attempts=2, tool_initial_delay=1.0, tool_max_delay=30.0)
    agent = Agent(model=model, tools=[failing_tool], retry_strategy=strategy)

    # This should NOT raise - the agent handles tool errors gracefully
    await agent.invoke_async("call the tool")

    # Tool should have been called max_attempts times
    assert failing_tool.call_count[0] == 2

    # Should have slept once (max_attempts - 1 retries)
    assert len(mock_sleep.sleep_calls) == 1


@pytest.mark.asyncio
async def test_agent_tool_retry_with_should_retry_predicate(mock_sleep):
    """Test that tool retry respects should_retry predicate."""
    call_count = [0]

    @tool(name="timeout_tool")
    def timeout_tool(message: str) -> str:
        """A tool that times out."""
        call_count[0] += 1
        if call_count[0] <= 2:
            raise TimeoutError("Connection timeout")
        return f"Success: {message}"

    # For @tool decorated functions, exceptions are caught and converted to error results.
    # The predicate receives a RuntimeError with the error message, not the original exception type.
    # Check for "timeout" in the error message to simulate matching on error type.
    def should_retry(e: Exception) -> bool:
        return "timeout" in str(e).lower()

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "test-tool-id", "name": "timeout_tool", "input": {"message": "hello"}}}
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    strategy = ToolAndModelRetryStrategy(tool_max_attempts=5, tool_initial_delay=1.0, tool_should_retry=should_retry)
    agent = Agent(model=model, tools=[timeout_tool], retry_strategy=strategy)

    await agent.invoke_async("call the tool")

    # Tool should have been retried
    assert call_count[0] == 3
    assert len(mock_sleep.sleep_calls) == 2


@pytest.mark.asyncio
async def test_agent_tool_retry_predicate_rejects_non_matching_errors(mock_sleep):
    """Test that tool retry does not retry when predicate returns False."""
    call_count = [0]

    @tool(name="value_error_tool")
    def value_error_tool(message: str) -> str:
        """A tool that raises ValueError."""
        call_count[0] += 1
        raise ValueError("Invalid value")

    # For @tool decorated functions, exceptions are caught and converted to error results.
    # Only retry if "timeout" is in the error message (not "invalid value")
    def should_retry(e: Exception) -> bool:
        return "timeout" in str(e).lower()

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {
                        "toolUse": {
                            "toolUseId": "test-tool-id",
                            "name": "value_error_tool",
                            "input": {"message": "hello"},
                        }
                    }
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    strategy = ToolAndModelRetryStrategy(tool_max_attempts=5, tool_initial_delay=1.0, tool_should_retry=should_retry)
    agent = Agent(model=model, tools=[value_error_tool], retry_strategy=strategy)

    await agent.invoke_async("call the tool")

    # Tool should NOT have been retried (predicate returns False for ValueError)
    assert call_count[0] == 1
    assert len(mock_sleep.sleep_calls) == 0


@pytest.mark.asyncio
async def test_agent_tool_retry_with_enabled_tools(mock_sleep):
    """Test tool retry with tool_enabled_tools filter."""
    enabled_calls = [0]
    disabled_calls = [0]

    @tool(name="enabled_tool")
    def enabled_tool(message: str) -> str:
        """An enabled tool."""
        enabled_calls[0] += 1
        if enabled_calls[0] <= 1:
            raise RuntimeError("Fail once")
        return "Success"

    @tool(name="disabled_tool")
    def disabled_tool(message: str) -> str:
        """A disabled tool."""
        disabled_calls[0] += 1
        raise RuntimeError("Always fail")

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "id-1", "name": "enabled_tool", "input": {"message": "test"}}},
                    {"toolUse": {"toolUseId": "id-2", "name": "disabled_tool", "input": {"message": "test"}}},
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    # Only retry enabled_tool
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5, tool_initial_delay=1.0, tool_enabled_tools=["enabled_tool"]
    )
    agent = Agent(model=model, tools=[enabled_tool, disabled_tool], retry_strategy=strategy)

    await agent.invoke_async("call both tools")

    # enabled_tool should have been retried (called twice)
    assert enabled_calls[0] == 2
    # disabled_tool should NOT have been retried (called once)
    assert disabled_calls[0] == 1
    # Only one sleep (for enabled_tool retry)
    assert len(mock_sleep.sleep_calls) == 1


@pytest.mark.asyncio
async def test_agent_tool_retry_with_disabled_tools(mock_sleep):
    """Test tool retry with tool_disabled_tools filter."""
    normal_calls = [0]
    disabled_calls = [0]

    @tool(name="normal_tool")
    def normal_tool(message: str) -> str:
        """A normal tool."""
        normal_calls[0] += 1
        if normal_calls[0] <= 1:
            raise RuntimeError("Fail once")
        return "Success"

    @tool(name="no_retry_tool")
    def no_retry_tool(message: str) -> str:
        """A tool that should not be retried."""
        disabled_calls[0] += 1
        raise RuntimeError("Always fail")

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "id-1", "name": "normal_tool", "input": {"message": "test"}}},
                    {"toolUse": {"toolUseId": "id-2", "name": "no_retry_tool", "input": {"message": "test"}}},
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    # Disable retry for no_retry_tool
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5, tool_initial_delay=1.0, tool_disabled_tools=["no_retry_tool"]
    )
    agent = Agent(model=model, tools=[normal_tool, no_retry_tool], retry_strategy=strategy)

    await agent.invoke_async("call both tools")

    # normal_tool should have been retried (called twice)
    assert normal_calls[0] == 2
    # no_retry_tool should NOT have been retried (called once)
    assert disabled_calls[0] == 1


@pytest.mark.asyncio
async def test_agent_tool_retry_with_per_tool_config(mock_sleep):
    """Test tool retry with per-tool configuration."""
    tool1_calls = [0]
    tool2_calls = [0]

    @tool(name="tool1")
    def tool1(message: str) -> str:
        """First tool."""
        tool1_calls[0] += 1
        if tool1_calls[0] <= 2:
            raise RuntimeError("Fail twice")
        return "Success"

    @tool(name="tool2")
    def tool2(message: str) -> str:
        """Second tool."""
        tool2_calls[0] += 1
        if tool2_calls[0] <= 3:
            raise RuntimeError("Fail three times")
        return "Success"

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "id-1", "name": "tool1", "input": {"message": "test"}}},
                ],
            },
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "id-2", "name": "tool2", "input": {"message": "test"}}},
                ],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    # Different configs for each tool
    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=2,  # Default: 2 attempts
        tool_initial_delay=1.0,
        tool_configs={
            "tool1": {"max_attempts": 5, "initial_delay": 0.5},  # tool1 gets more attempts
            "tool2": {"max_attempts": 5, "initial_delay": 2.0},  # tool2 also gets more, but slower
        },
    )
    agent = Agent(model=model, tools=[tool1, tool2], retry_strategy=strategy)

    await agent.invoke_async("call tools")

    # tool1 should succeed after 3 calls (2 failures + 1 success)
    assert tool1_calls[0] == 3
    # tool2 should succeed after 4 calls (3 failures + 1 success)
    assert tool2_calls[0] == 4

    # Check sleep delays: tool1 uses initial_delay=0.5, tool2 uses initial_delay=2.0
    # tool1: 0.5, 1.0 (2 retries)
    # tool2: 2.0, 4.0, 8.0 (3 retries)
    assert mock_sleep.sleep_calls == [0.5, 1.0, 2.0, 4.0, 8.0]


@pytest.mark.asyncio
async def test_agent_without_tool_retry_does_not_retry(mock_sleep, failing_tool):
    """Test that Agent without tool retries enabled does not retry tool calls."""
    # Mock model that calls the failing tool
    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [
                    {"toolUse": {"toolUseId": "test-tool-id", "name": "failing_tool", "input": {"message": "hello"}}}
                ],
            },
            {"role": "assistant", "content": [{"text": "Tool failed"}]},
        ]
    )

    # Default strategy has tool_max_attempts=0 (disabled)
    agent = Agent(model=model, tools=[failing_tool])

    await agent.invoke_async("call the tool")

    # Tool should have been called only once (no retry)
    assert failing_tool.call_count[0] == 1

    # Should not have slept for tool retries (may have slept for other reasons)
    # We just verify tool was called once


@pytest.mark.asyncio
async def test_agent_tool_and_model_retry_both_work(mock_sleep):
    """Test that both model and tool retries work together."""
    tool_calls = [0]

    @tool(name="flaky_tool")
    def flaky_tool(message: str) -> str:
        """A flaky tool."""
        tool_calls[0] += 1
        if tool_calls[0] <= 1:
            raise RuntimeError("Fail once")
        return "Success"

    model = MockedModelProvider(
        [
            {
                "role": "assistant",
                "content": [{"toolUse": {"toolUseId": "test-id", "name": "flaky_tool", "input": {"message": "test"}}}],
            },
            {"role": "assistant", "content": [{"text": "Done"}]},
        ]
    )

    # Enable both model and tool retries
    strategy = ToolAndModelRetryStrategy(
        model_max_attempts=3,
        model_initial_delay=2.0,
        tool_max_attempts=3,
        tool_initial_delay=1.0,
    )
    agent = Agent(model=model, tools=[flaky_tool], retry_strategy=strategy)

    await agent.invoke_async("call the tool")

    # Tool should have been retried
    assert tool_calls[0] == 2
    # Should have slept for tool retry
    assert 1.0 in mock_sleep.sleep_calls

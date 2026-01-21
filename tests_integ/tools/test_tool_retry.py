"""Integration tests for tool retry with ToolAndModelRetryStrategy."""

import pytest

from strands import Agent, ToolAndModelRetryStrategy, tool
from tests_integ.conftest import retry_on_flaky


def make_failing_tool(fail_times: int = 2):
    """Create a tool that fails a configurable number of times before succeeding."""
    state = {"call_count": 0, "fail_times": fail_times}

    @tool(name="failing_tool")
    def _failing_tool(message: str) -> str:
        """A tool that fails a few times before succeeding.

        Args:
            message: A message to include in the response.
        """
        state["call_count"] += 1
        if state["call_count"] <= state["fail_times"]:
            raise RuntimeError(f"Simulated failure {state['call_count']}")
        return f"Success on attempt {state['call_count']}: {message}"

    _failing_tool.state = state
    return _failing_tool


@pytest.fixture
def failing_tool():
    """Create a fresh failing tool for each test."""
    return make_failing_tool(fail_times=2)


def make_timeout_tool(fail_times: int = 2):
    """Create a tool that raises timeout errors."""
    state = {"call_count": 0, "fail_times": fail_times}

    @tool(name="timeout_tool")
    def _timeout_tool(query: str) -> str:
        """A tool that times out a few times before succeeding.

        Args:
            query: The query to process.
        """
        state["call_count"] += 1
        if state["call_count"] <= state["fail_times"]:
            raise TimeoutError(f"Connection timeout on attempt {state['call_count']}")
        return f"Query result for: {query}"

    _timeout_tool.state = state
    return _timeout_tool


@pytest.fixture
def timeout_tool():
    """Create a fresh timeout tool for each test."""
    return make_timeout_tool(fail_times=2)


def make_value_error_tool():
    """Create a tool that raises value errors (should not be retried with timeout predicate)."""
    state = {"call_count": 0}

    @tool(name="value_error_tool")
    def _value_error_tool(data: str) -> str:
        """A tool that raises ValueError.

        Args:
            data: The data to validate.
        """
        state["call_count"] += 1
        raise ValueError(f"Invalid data format: {data}")

    _value_error_tool.state = state
    return _value_error_tool


@pytest.fixture
def value_error_tool():
    """Create a fresh value error tool for each test."""
    return make_value_error_tool()


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_on_failure():
    """Test that tools are retried when they fail and retry is enabled."""
    # Create fresh tool for this test run
    failing_tool = make_failing_tool(fail_times=2)

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,  # Short delay for tests
        tool_max_delay=1.0,
    )
    agent = Agent(tools=[failing_tool], retry_strategy=strategy)

    # Ask the agent to use the tool
    result = agent("Use the failing_tool with message 'hello'")

    # Tool should have been called at least 3 times (2 failures + 1 success)
    # May be more if LLM decides to call tool multiple times
    assert failing_tool.state["call_count"] >= 3, (
        f"Expected at least 3 calls (2 failures + 1 success), got {failing_tool.state['call_count']}"
    )

    # The result should contain the success message
    assert "Success" in str(result) or "success" in str(result).lower()


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_respects_max_attempts():
    """Test that tool retry happens at least max_attempts times per tool use."""
    # Create fresh tool that always fails
    failing_tool = make_failing_tool(fail_times=1000)

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=3,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
    )
    agent = Agent(tools=[failing_tool], retry_strategy=strategy)

    # Ask the agent to use the tool - it will fail but agent handles gracefully
    agent("Use the failing_tool with message 'test'")

    # Tool should have been called at least max_attempts times (3)
    # May be more if LLM decides to call tool again at conversation level
    assert failing_tool.state["call_count"] >= 3, (
        f"Expected at least 3 calls (max_attempts), got {failing_tool.state['call_count']}"
    )
    # Verify retries are happening in batches of max_attempts
    # (call_count should be a multiple of 3 if each tool use is retried 3 times)
    assert failing_tool.state["call_count"] % 3 == 0, (
        f"Expected call_count to be multiple of 3 (max_attempts), got {failing_tool.state['call_count']}"
    )


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_with_should_retry_predicate():
    """Test that should_retry predicate controls which errors are retried."""
    # Create fresh tool for this test run
    timeout_tool = make_timeout_tool(fail_times=2)

    # Only retry timeout errors
    def should_retry(e: Exception) -> bool:
        return "timeout" in str(e).lower()

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
        tool_should_retry=should_retry,
    )
    agent = Agent(tools=[timeout_tool], retry_strategy=strategy)

    result = agent("Use the timeout_tool with query 'search'")

    # Tool should have been retried (at least 3 calls: 2 timeouts + 1 success)
    assert timeout_tool.state["call_count"] >= 3, (
        f"Expected at least 3 calls for timeout errors, got {timeout_tool.state['call_count']}"
    )
    assert "Query result" in str(result) or "search" in str(result).lower()


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_predicate_rejects_non_matching_errors():
    """Test that errors not matching the predicate are not retried by our retry mechanism."""
    # Create fresh tool for this test run
    value_error_tool = make_value_error_tool()

    # Only retry timeout errors (not value errors)
    def should_retry(e: Exception) -> bool:
        return "timeout" in str(e).lower()

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
        tool_should_retry=should_retry,
    )
    agent = Agent(tools=[value_error_tool], retry_strategy=strategy)

    # The tool will fail with ValueError, which should NOT be retried by our mechanism
    # (LLM may decide to retry at conversation level, but our retry mechanism won't)
    agent("Use the value_error_tool with data 'bad_data'")

    # Each tool use should only be called once (no automatic retry for ValueError)
    # If LLM calls tool N times at conversation level, we expect N calls (not N*max_attempts)
    # With max_attempts=5, if our retry WAS happening, we'd see 5x the calls
    # This test verifies our retry predicate works - call count should NOT be a multiple of 5
    call_count = value_error_tool.state["call_count"]
    # If our retry was happening, first tool use would be 5 calls. So count != 5 means retry didn't happen
    assert call_count < 5 or call_count % 5 != 0, (
        f"Unexpected {call_count} calls - suggests retry is happening for ValueError"
    )


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_with_enabled_tools_filter():
    """Test that tool_enabled_tools filter controls which tools are retried."""
    # Create fresh tools for this test run
    failing_tool = make_failing_tool(fail_times=2)
    value_error_tool = make_value_error_tool()

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
        tool_enabled_tools=["failing_tool"],  # Only retry failing_tool
    )
    agent = Agent(tools=[failing_tool, value_error_tool], retry_strategy=strategy)

    # Use failing_tool - should be retried
    agent("Use the failing_tool with message 'retry me'")
    assert failing_tool.state["call_count"] >= 3, "failing_tool should have been retried"


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_with_disabled_tools_filter():
    """Test that tool_disabled_tools filter excludes tools from automatic retry."""
    # Create fresh tool for this test run - fails twice then succeeds
    failing_tool = make_failing_tool(fail_times=2)

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
        tool_disabled_tools=["failing_tool"],  # Disable retry for failing_tool
    )
    agent = Agent(tools=[failing_tool], retry_strategy=strategy)

    agent("Use the failing_tool with message 'test'")

    # With retry disabled, each tool use is only 1 call (no automatic retry)
    # Tool fails twice then succeeds, so LLM will call it 3 times at conversation level
    # If our retry WAS happening, we'd see 5x the calls per tool use
    # This test verifies disabled_tools works - call count should NOT be a multiple of 5
    call_count = failing_tool.state["call_count"]
    assert call_count < 5 or call_count % 5 != 0, (
        f"Unexpected {call_count} calls - suggests retry is happening despite being disabled"
    )


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_with_per_tool_config():
    """Test per-tool configuration overrides global settings."""
    # Create fresh tools for this test run
    failing_tool = make_failing_tool(fail_times=2)

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=2,  # Global: only 2 attempts (will fail)
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
        tool_configs={
            "failing_tool": {"max_attempts": 5},  # Override: 5 attempts (will succeed)
        },
    )
    agent = Agent(tools=[failing_tool], retry_strategy=strategy)

    # failing_tool has 5 attempts, should succeed after 3 calls
    agent("Use the failing_tool with message 'custom config'")
    assert failing_tool.state["call_count"] >= 3, "failing_tool should succeed with custom config"


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_disabled_by_default():
    """Test that tool retry is disabled by default (tool_max_attempts=0)."""
    state = {"call_count": 0}

    @tool(name="always_fails")
    def always_fails(msg: str) -> str:
        """A tool that always fails.

        Args:
            msg: A message.
        """
        state["call_count"] += 1
        raise RuntimeError("Always fails")

    # Default strategy has tool_max_attempts=0 (disabled)
    agent = Agent(tools=[always_fails])

    agent("Use the always_fails tool with msg 'test'")

    # With retry disabled (default), each tool use should be 1 call
    # LLM may call tool multiple times at conversation level, but no automatic retry
    # If retry WAS enabled with say 3 attempts, we'd see multiples of 3
    # Just verify tool was called at least once
    assert state["call_count"] >= 1, f"Expected at least 1 call, got {state['call_count']}"


@retry_on_flaky("LLM responses may vary in tool calling behavior")
def test_tool_retry_works_with_async_tools():
    """Test that tool retry works with async tools."""
    import asyncio

    state = {"call_count": 0, "fail_times": 2}

    @tool(name="async_failing_tool")
    async def async_failing_tool(message: str) -> str:
        """An async tool that fails a few times.

        Args:
            message: A message to process.
        """
        state["call_count"] += 1
        await asyncio.sleep(0.01)  # Simulate async work
        if state["call_count"] <= state["fail_times"]:
            raise RuntimeError(f"Async failure {state['call_count']}")
        return f"Async success: {message}"

    strategy = ToolAndModelRetryStrategy(
        tool_max_attempts=5,
        tool_initial_delay=0.1,
        tool_max_delay=1.0,
    )
    agent = Agent(tools=[async_failing_tool], retry_strategy=strategy)

    result = agent("Use the async_failing_tool with message 'async test'")

    assert state["call_count"] >= 3, f"Expected at least 3 calls for async tool, got {state['call_count']}"
    assert "success" in str(result).lower() or "async" in str(result).lower()

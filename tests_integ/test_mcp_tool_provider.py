"""Integration tests for MCPToolProvider with real MCP server."""

import logging
import re
from unittest.mock import patch

import pytest
from mcp import StdioServerParameters, stdio_client

from strands import Agent
from strands.experimental.tools.mcp import MCPToolProvider, ToolFilters
from strands.tools.mcp import MCPClient
from strands.types.exceptions import ToolProviderException

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger(__name__)


def test_mcp_tool_provider_filters():
    """Test MCPToolProvider with various filter combinations."""
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    # Test string filter, regex filter, callable filter, max_tools, and disambiguator
    def short_names_only(tool) -> bool:
        return len(tool.tool_name) <= 20  # Allow most tools

    filters: ToolFilters = {
        "allowed": ["echo", re.compile(r"echo_with_.*"), short_names_only],
        "rejected": ["echo_with_delay"],
        "max_tools": 2,
    }

    provider = MCPToolProvider(client=stdio_mcp_client, tool_filters=filters, disambiguator="test")
    agent = Agent(tools=[provider])
    tool_names = agent.tool_names

    # Should have 2 tools max, with test_ prefix, no delay tool
    assert len(tool_names) == 2
    assert "echo_with_delay" not in [name.replace("test_", "") for name in tool_names]
    assert all(name.startswith("test_") for name in tool_names)

    agent.cleanup()


def test_mcp_tool_provider_execution():
    """Test that MCPToolProvider works with agent execution."""
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    filters: ToolFilters = {"allowed": ["echo"]}
    provider = MCPToolProvider(client=stdio_mcp_client, tool_filters=filters, disambiguator="filtered")
    agent = Agent(
        tools=[provider],
    )

    # Verify the filtered tool exists
    assert "filtered_echo" in agent.tool_names

    # # Test direct tool call to verify it works (use correct parameter name from echo server)
    tool_result = agent.tool.filtered_echo(to_echo="Hello World")
    assert "Hello World" in str(tool_result)

    # # Test agent execution using the tool
    result = agent("Use the filtered_echo tool to echo whats inside the tags <>Integration Test</>")
    assert "Integration Test" in str(result)

    assert agent.event_loop_metrics.tool_metrics["filtered_echo"].call_count == 1
    assert agent.event_loop_metrics.tool_metrics["filtered_echo"].success_count == 1

    agent.cleanup()


def test_mcp_tool_provider_cleanup_with_spy():
    """Test MCPToolProvider cleanup using spy pattern."""
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    # Create spy to track client.stop calls
    original_stop = stdio_mcp_client.stop
    stop_calls = []

    def spy_stop(*args, **kwargs):
        stop_calls.append((args, kwargs))
        return original_stop(*args, **kwargs)

    stdio_mcp_client.stop = spy_stop

    # Test explicit cleanup
    provider = MCPToolProvider(client=stdio_mcp_client)
    agent = Agent(tools=[provider])
    assert len(agent.tool_names) > 0
    assert provider._started

    # Cleanup and verify spy recorded the call
    agent.cleanup()
    assert not provider._started
    assert provider._tools is None
    assert len(stop_calls) == 1  # Verify stop was called exactly once


@patch("strands.tools.mcp.mcp_client.MCPClient.stop")
def test_mcp_tool_provider_cleanup_with_mock(mock_stop):
    """Test MCPToolProvider cleanup using mock."""
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    provider = MCPToolProvider(client=stdio_mcp_client)
    agent = Agent(tools=[provider])
    assert len(agent.tool_names) > 0
    assert provider._started

    # Cleanup
    agent.cleanup()

    # Verify mock was called
    mock_stop.assert_called_once_with(None, None, None)
    assert not provider._started
    assert provider._tools is None


def test_mcp_tool_provider_reuse():
    """Test that a single MCPToolProvider can be used across multiple agents."""
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    filters: ToolFilters = {"allowed": ["echo"]}
    provider = MCPToolProvider(client=stdio_mcp_client, tool_filters=filters, disambiguator="shared")

    # Create first agent with the provider
    agent1 = Agent(tools=[provider])
    assert "shared_echo" in agent1.tool_names

    # Test first agent (use correct parameter name from echo server)
    result1 = agent1.tool.shared_echo(to_echo="Agent 1")
    assert "Agent 1" in str(result1)

    # Create second agent with the same provider
    agent2 = Agent(tools=[provider])
    assert "shared_echo" in agent2.tool_names

    # Test second agent (use correct parameter name from echo server)
    result2 = agent2.tool.shared_echo(to_echo="Agent 2")
    assert "Agent 2" in str(result2)

    # Both agents should have the same tool count
    assert len(agent1.tool_names) == len(agent2.tool_names)
    assert agent1.tool_names == agent2.tool_names

    agent1.cleanup()
    agent2.cleanup()


def test_mcp_tool_provider_multiple_servers():
    """Test MCPToolProvider with multiple MCP servers simultaneously."""
    # Create two separate MCP clients
    client1 = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )
    client2 = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="python", args=["tests_integ/echo_server.py"]))
    )

    # Create providers with different disambiguators
    provider1 = MCPToolProvider(client=client1, tool_filters={"allowed": ["echo"]}, disambiguator="server1")
    # Use correct tool name from echo_server.py
    provider2 = MCPToolProvider(
        client=client2, tool_filters={"allowed": ["echo_with_structured_content"]}, disambiguator="server2"
    )

    # Create agent with both providers
    agent = Agent(tools=[provider1, provider2])

    # Should have tools from both servers with different prefixes
    assert "server1_echo" in agent.tool_names
    assert "server2_echo_with_structured_content" in agent.tool_names
    assert len(agent.tool_names) == 2

    # Test tools from both servers work
    result1 = agent.tool.server1_echo(to_echo="From Server 1")
    assert "From Server 1" in str(result1)

    result2 = agent.tool.server2_echo_with_structured_content(to_echo="From Server 2")
    assert "From Server 2" in str(result2)

    agent.cleanup()


def test_mcp_tool_provider_server_startup_failure():
    """Test that MCPToolProvider handles server startup failure gracefully without hanging."""
    # Create client with invalid command that will fail to start
    failing_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="nonexistent_command", args=["--invalid"])),
        startup_timeout=2,  # Short timeout to avoid hanging
    )

    provider = MCPToolProvider(client=failing_client)

    # Should raise ToolProviderException when trying to load tools
    with pytest.raises(ToolProviderException, match="Failed to start MCP client"):
        Agent(tools=[provider])


def test_mcp_tool_provider_server_connection_timeout():
    """Test that MCPToolProvider times out gracefully when server hangs during startup."""
    # Create client that will hang during connection
    hanging_client = MCPClient(
        lambda: stdio_client(StdioServerParameters(command="sleep", args=["10"])),  # Sleep for 10 seconds
        startup_timeout=1,  # 1 second timeout
    )

    provider = MCPToolProvider(client=hanging_client)

    # Should raise ToolProviderException due to timeout
    with pytest.raises(ToolProviderException, match="Failed to start MCP client"):
        Agent(tools=[provider])

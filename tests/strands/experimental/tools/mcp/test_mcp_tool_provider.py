"""Unit tests for MCPToolProvider."""

import asyncio
import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from strands.experimental.tools.mcp import MCPToolProvider, ToolFilters
from strands.tools.mcp import MCPClient
from strands.tools.mcp.mcp_agent_tool import MCPAgentTool
from strands.types import PaginatedList
from strands.types.exceptions import ToolProviderException


@pytest.fixture
def mock_mcp_client():
    """Create a mock MCP client."""
    client = MagicMock(spec=MCPClient)
    client.start = MagicMock()
    client.stop = MagicMock()
    client.list_tools_sync = MagicMock()
    return client


@pytest.fixture
def mock_mcp_tool():
    """Create a mock MCP tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    return tool


@pytest.fixture
def mock_agent_tool(mock_mcp_tool, mock_mcp_client):
    """Create a mock MCPAgentTool."""
    agent_tool = MagicMock(spec=MCPAgentTool)
    agent_tool.tool_name = "test_tool"
    agent_tool.mcp_tool = mock_mcp_tool
    agent_tool.mcp_client = mock_mcp_client
    return agent_tool


class TestMCPToolProviderInit:
    """Test MCPToolProvider initialization."""

    def test_init_with_client_only(self, mock_mcp_client):
        """Test initialization with only client."""
        provider = MCPToolProvider(client=mock_mcp_client)

        assert provider._client is mock_mcp_client
        assert provider._tool_filters is None
        assert provider._disambiguator is None
        assert provider._tools is None
        assert provider._started is False

    def test_init_with_all_parameters(self, mock_mcp_client):
        """Test initialization with all parameters."""
        filters = {"allowed": ["tool1"], "max_tools": 5}
        disambiguator = "test_prefix"

        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters, disambiguator=disambiguator)

        assert provider._client is mock_mcp_client
        assert provider._tool_filters == filters
        assert provider._disambiguator == disambiguator
        assert provider._tools is None
        assert provider._started is False


class TestMCPToolProviderLoadTools:
    """Test MCPToolProvider load_tools method."""

    @pytest.mark.asyncio
    async def test_load_tools_starts_client_when_not_started(self, mock_mcp_client, mock_agent_tool):
        """Test that load_tools starts the client when not already started."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([mock_agent_tool])

        provider = MCPToolProvider(client=mock_mcp_client)

        tools = await provider.load_tools()

        mock_mcp_client.start.assert_called_once()
        assert provider._started is True
        assert len(tools) == 1
        assert tools[0] is mock_agent_tool

    @pytest.mark.asyncio
    async def test_load_tools_does_not_start_client_when_already_started(self, mock_mcp_client, mock_agent_tool):
        """Test that load_tools does not start client when already started."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([mock_agent_tool])

        provider = MCPToolProvider(client=mock_mcp_client)
        provider._started = True

        tools = await provider.load_tools()

        mock_mcp_client.start.assert_not_called()
        assert len(tools) == 1

    @pytest.mark.asyncio
    async def test_load_tools_raises_exception_on_client_start_failure(self, mock_mcp_client):
        """Test that load_tools raises ToolProviderException when client start fails."""
        mock_mcp_client.start.side_effect = Exception("Client start failed")

        provider = MCPToolProvider(client=mock_mcp_client)

        with pytest.raises(ToolProviderException, match="Failed to start MCP client: Client start failed"):
            await provider.load_tools()

    @pytest.mark.asyncio
    async def test_load_tools_caches_tools(self, mock_mcp_client, mock_agent_tool):
        """Test that load_tools caches tools and doesn't reload them."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([mock_agent_tool])

        provider = MCPToolProvider(client=mock_mcp_client)

        # First call
        tools1 = await provider.load_tools()
        # Second call
        tools2 = await provider.load_tools()

        # Client should only be called once
        mock_mcp_client.list_tools_sync.assert_called_once()
        assert tools1 is tools2

    @pytest.mark.asyncio
    async def test_load_tools_handles_pagination(self, mock_mcp_client, mock_agent_tool):
        """Test that load_tools handles pagination correctly."""
        tool1 = MagicMock(spec=MCPAgentTool)
        tool1.tool_name = "tool1"
        tool2 = MagicMock(spec=MCPAgentTool)
        tool2.tool_name = "tool2"

        # Mock pagination: first page returns tool1 with next token, second page returns tool2 with no token
        mock_mcp_client.list_tools_sync.side_effect = [
            PaginatedList([tool1], token="page2"),
            PaginatedList([tool2], token=None),
        ]

        provider = MCPToolProvider(client=mock_mcp_client)

        tools = await provider.load_tools()

        # Should have called list_tools_sync twice
        assert mock_mcp_client.list_tools_sync.call_count == 2
        # First call with no token, second call with "page2" token
        mock_mcp_client.list_tools_sync.assert_any_call(None)
        mock_mcp_client.list_tools_sync.assert_any_call("page2")

        assert len(tools) == 2
        assert tools[0] is tool1
        assert tools[1] is tool2


class TestMCPToolProviderFiltering:
    """Test MCPToolProvider filtering functionality."""

    def create_mock_tool(self, name: str) -> MagicMock:
        """Helper to create mock tools with specific names."""
        tool = MagicMock(spec=MCPAgentTool)
        tool.tool_name = name
        tool.mcp_tool = MagicMock()
        tool.mcp_tool.name = name
        return tool

    @pytest.mark.asyncio
    async def test_allowed_filter_string_match(self, mock_mcp_client):
        """Test allowed filter with string matching."""
        tool1 = self.create_mock_tool("allowed_tool")
        tool2 = self.create_mock_tool("rejected_tool")

        mock_mcp_client.list_tools_sync.return_value = PaginatedList([tool1, tool2])

        filters: ToolFilters = {"allowed": ["allowed_tool"]}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0].tool_name == "allowed_tool"

    @pytest.mark.asyncio
    async def test_allowed_filter_regex_match(self, mock_mcp_client):
        """Test allowed filter with regex matching."""
        tool1 = self.create_mock_tool("echo_tool")
        tool2 = self.create_mock_tool("other_tool")

        mock_mcp_client.list_tools_sync.return_value = PaginatedList([tool1, tool2])

        filters: ToolFilters = {"allowed": [re.compile(r"echo_.*")]}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0].tool_name == "echo_tool"

    @pytest.mark.asyncio
    async def test_allowed_filter_callable_match(self, mock_mcp_client):
        """Test allowed filter with callable matching."""
        tool1 = self.create_mock_tool("short")
        tool2 = self.create_mock_tool("very_long_tool_name")

        mock_mcp_client.list_tools_sync.return_value = PaginatedList([tool1, tool2])

        def short_names_only(tool) -> bool:
            return len(tool.tool_name) <= 10

        filters: ToolFilters = {"allowed": [short_names_only]}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0].tool_name == "short"

    @pytest.mark.asyncio
    async def test_rejected_filter(self, mock_mcp_client):
        """Test rejected filter functionality."""
        tool1 = self.create_mock_tool("good_tool")
        tool2 = self.create_mock_tool("bad_tool")

        mock_mcp_client.list_tools_sync.return_value = PaginatedList([tool1, tool2])

        filters: ToolFilters = {"rejected": ["bad_tool"]}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0].tool_name == "good_tool"

    @pytest.mark.asyncio
    async def test_max_tools_filter(self, mock_mcp_client):
        """Test max_tools filter functionality."""
        tools_list = [self.create_mock_tool(f"tool_{i}") for i in range(5)]

        mock_mcp_client.list_tools_sync.return_value = PaginatedList(tools_list)

        filters: ToolFilters = {"max_tools": 3}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 3
        assert all(tool.tool_name.startswith("tool_") for tool in tools)

    @pytest.mark.asyncio
    async def test_combined_filters(self, mock_mcp_client):
        """Test combination of multiple filters."""
        tools_list = [
            self.create_mock_tool("echo_good"),
            self.create_mock_tool("echo_bad"),
            self.create_mock_tool("other_good"),
            self.create_mock_tool("echo_another"),
        ]

        mock_mcp_client.list_tools_sync.return_value = PaginatedList(tools_list)

        filters: ToolFilters = {"allowed": [re.compile(r"echo_.*")], "rejected": ["echo_bad"], "max_tools": 1}
        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=filters)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0].tool_name in ["echo_good", "echo_another"]


class TestMCPToolProviderDisambiguation:
    """Test MCPToolProvider disambiguation functionality."""

    @pytest.mark.asyncio
    async def test_disambiguator_renames_tools(self, mock_mcp_client):
        """Test that disambiguator properly renames tools."""
        original_tool = MagicMock(spec=MCPAgentTool)
        original_tool.tool_name = "original_name"
        original_tool.mcp_tool = MagicMock()
        original_tool.mcp_tool.name = "original_name"
        original_tool.mcp_client = mock_mcp_client

        mock_mcp_client.list_tools_sync.return_value = PaginatedList([original_tool])

        with patch("strands.experimental.tools.mcp.mcp_tool_provider.MCPAgentTool") as mock_agent_tool_class:
            new_tool = MagicMock(spec=MCPAgentTool)
            new_tool.tool_name = "prefix_original_name"
            mock_agent_tool_class.return_value = new_tool

            provider = MCPToolProvider(client=mock_mcp_client, disambiguator="prefix")

            tools = await provider.load_tools()

            # Should create new MCPAgentTool with prefixed name
            mock_agent_tool_class.assert_called_once_with(
                original_tool.mcp_tool, original_tool.mcp_client, agent_tool_name="prefix_original_name"
            )

            assert len(tools) == 1
            assert tools[0] is new_tool


class TestMCPToolProviderCleanup:
    """Test MCPToolProvider cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_stops_client_when_started(self, mock_mcp_client):
        """Test that cleanup stops the client when started."""
        provider = MCPToolProvider(client=mock_mcp_client)
        provider._started = True
        provider._tools = [MagicMock()]

        await provider.cleanup()

        mock_mcp_client.stop.assert_called_once_with(None, None, None)
        assert provider._started is False
        assert provider._tools is None

    @pytest.mark.asyncio
    async def test_cleanup_does_nothing_when_not_started(self, mock_mcp_client):
        """Test that cleanup does nothing when not started."""
        provider = MCPToolProvider(client=mock_mcp_client)
        provider._started = False

        await provider.cleanup()

        mock_mcp_client.stop.assert_not_called()
        assert provider._started is False

    @pytest.mark.asyncio
    async def test_cleanup_raises_exception_on_client_stop_failure(self, mock_mcp_client):
        """Test that cleanup raises ToolProviderException when client stop fails."""
        mock_mcp_client.stop.side_effect = Exception("Client stop failed")

        provider = MCPToolProvider(client=mock_mcp_client)
        provider._started = True

        with pytest.raises(ToolProviderException, match="Failed to cleanup MCP client: Client stop failed"):
            await provider.cleanup()

        # Should still reset state in finally block
        assert provider._started is False
        assert provider._tools is None

    @pytest.mark.asyncio
    async def test_cleanup_resets_state_even_on_exception(self, mock_mcp_client):
        """Test that cleanup resets state even when exception occurs."""
        mock_mcp_client.stop.side_effect = Exception("Client stop failed")

        provider = MCPToolProvider(client=mock_mcp_client)
        provider._started = True
        provider._tools = [MagicMock()]

        with pytest.raises(ToolProviderException):
            await provider.cleanup()

        # State should be reset despite exception
        assert provider._started is False
        assert provider._tools is None


class TestMCPToolProviderMatchesPatterns:
    """Test MCPToolProvider _matches_patterns method."""

    def test_matches_patterns_string(self, mock_mcp_client):
        """Test pattern matching with string patterns."""
        provider = MCPToolProvider(client=mock_mcp_client)

        tool = MagicMock()
        tool.tool_name = "test_tool"

        # Should match exact string
        assert provider._matches_patterns(tool, ["test_tool"]) is True
        assert provider._matches_patterns(tool, ["other_tool"]) is False
        assert provider._matches_patterns(tool, ["test_tool", "other_tool"]) is True

    def test_matches_patterns_regex(self, mock_mcp_client):
        """Test pattern matching with regex patterns."""
        provider = MCPToolProvider(client=mock_mcp_client)

        tool = MagicMock()
        tool.tool_name = "echo_test"

        # Should match regex pattern
        assert provider._matches_patterns(tool, [re.compile(r"echo_.*")]) is True
        assert provider._matches_patterns(tool, [re.compile(r"other_.*")]) is False

    def test_matches_patterns_callable(self, mock_mcp_client):
        """Test pattern matching with callable patterns."""
        provider = MCPToolProvider(client=mock_mcp_client)

        tool = MagicMock()
        tool.tool_name = "short"

        def short_names(t):
            return len(t.tool_name) <= 10

        def long_names(t):
            return len(t.tool_name) > 10

        # Should match callable that returns True
        assert provider._matches_patterns(tool, [short_names]) is True
        assert provider._matches_patterns(tool, [long_names]) is False

    def test_matches_patterns_mixed(self, mock_mcp_client):
        """Test pattern matching with mixed pattern types."""
        provider = MCPToolProvider(client=mock_mcp_client)

        tool = MagicMock()
        tool.tool_name = "echo_test"

        def always_false(t):
            return False

        patterns = [
            "other_tool",  # String that doesn't match
            re.compile(r"other_.*"),  # Regex that doesn't match
            always_false,  # Callable that doesn't match
            re.compile(r"echo_.*"),  # Regex that matches
        ]

        # Should match because one pattern (the last regex) matches
        assert provider._matches_patterns(tool, patterns) is True


class TestMCPToolProviderEdgeCases:
    """Test MCPToolProvider edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_load_tools_with_empty_tool_list(self, mock_mcp_client):
        """Test load_tools with empty tool list from server."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([])

        provider = MCPToolProvider(client=mock_mcp_client)

        tools = await provider.load_tools()

        assert len(tools) == 0
        assert provider._started is True

    @pytest.mark.asyncio
    async def test_load_tools_with_no_filters(self, mock_mcp_client, mock_agent_tool):
        """Test load_tools with no filters applied."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([mock_agent_tool])

        provider = MCPToolProvider(client=mock_mcp_client, tool_filters=None)

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0] is mock_agent_tool

    @pytest.mark.asyncio
    async def test_load_tools_with_empty_filters(self, mock_mcp_client, mock_agent_tool):
        """Test load_tools with empty filters dict."""
        mock_mcp_client.list_tools_sync.return_value = PaginatedList([mock_agent_tool])

        provider = MCPToolProvider(client=mock_mcp_client, tool_filters={})

        tools = await provider.load_tools()

        assert len(tools) == 1
        assert tools[0] is mock_agent_tool

    def test_matches_patterns_with_empty_patterns(self, mock_mcp_client):
        """Test _matches_patterns with empty pattern list."""
        provider = MCPToolProvider(client=mock_mcp_client)

        tool = MagicMock()
        tool.tool_name = "test_tool"

        # Empty pattern list should return False
        assert provider._matches_patterns(tool, []) is False

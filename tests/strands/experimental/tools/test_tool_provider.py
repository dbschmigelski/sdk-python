"""Unit tests for ToolProvider base class."""

from abc import ABC
from unittest.mock import MagicMock

import pytest

from strands.experimental.tools.tool_provider import ToolProvider
from strands.types.tools import AgentTool


class ConcreteToolProvider(ToolProvider):
    """Concrete implementation of ToolProvider for testing."""

    def __init__(self, tools=None):
        self._tools = tools or []

    async def load_tools(self):
        return self._tools

    async def cleanup(self):
        pass


class TestToolProvider:
    """Test ToolProvider base class."""

    def test_tool_provider_is_abstract(self):
        """Test that ToolProvider is an abstract base class."""
        assert issubclass(ToolProvider, ABC)

        # Should not be able to instantiate directly
        with pytest.raises(TypeError):
            ToolProvider()

    @pytest.mark.asyncio
    async def test_concrete_implementation_works(self):
        """Test that concrete implementation can be instantiated and used."""
        mock_tool = MagicMock(spec=AgentTool)
        mock_tool.tool_name = "test_tool"

        provider = ConcreteToolProvider([mock_tool])

        tools = await provider.load_tools()
        assert len(tools) == 1
        assert tools[0] is mock_tool

        # Cleanup should not raise
        await provider.cleanup()

    @pytest.mark.asyncio
    async def test_empty_tools_list(self):
        """Test provider with empty tools list."""
        provider = ConcreteToolProvider([])

        tools = await provider.load_tools()
        assert len(tools) == 0

    def test_abstract_methods_must_be_implemented(self):
        """Test that abstract methods must be implemented in subclasses."""

        class IncompleteProvider(ToolProvider):
            # Missing load_tools and cleanup implementations
            pass

        with pytest.raises(TypeError):
            IncompleteProvider()

    def test_partial_implementation_fails(self):
        """Test that partial implementation of abstract methods fails."""

        class PartialProvider(ToolProvider):
            async def load_tools(self):
                return []

            # Missing cleanup implementation

        with pytest.raises(TypeError):
            PartialProvider()

"""Unit tests for exception types."""

import pytest

from strands.types.exceptions import (
    ContextWindowOverflowException,
    EventLoopException,
    MaxTokensReachedException,
    MCPClientInitializationError,
    ModelThrottledException,
    SessionException,
    ToolProviderException,
)


class TestEventLoopException:
    """Test EventLoopException."""

    def test_init_with_original_exception_only(self):
        """Test initialization with only original exception."""
        original = ValueError("Original error")
        exception = EventLoopException(original)

        assert exception.original_exception is original
        assert exception.request_state == {}
        assert str(exception) == "Original error"

    def test_init_with_request_state(self):
        """Test initialization with request state."""
        original = ValueError("Original error")
        state = {"key": "value", "count": 42}
        exception = EventLoopException(original, state)

        assert exception.original_exception is original
        assert exception.request_state == state
        assert str(exception) == "Original error"

    def test_init_with_none_request_state(self):
        """Test initialization with None request state."""
        original = ValueError("Original error")
        exception = EventLoopException(original, None)

        assert exception.original_exception is original
        assert exception.request_state == {}


class TestMaxTokensReachedException:
    """Test MaxTokensReachedException."""

    def test_init_with_message(self):
        """Test initialization with message."""
        message = "Maximum tokens reached"
        exception = MaxTokensReachedException(message)

        assert str(exception) == message

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = MaxTokensReachedException("test")
        assert isinstance(exception, Exception)


class TestContextWindowOverflowException:
    """Test ContextWindowOverflowException."""

    def test_init(self):
        """Test initialization."""
        exception = ContextWindowOverflowException("Context overflow")
        assert str(exception) == "Context overflow"

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = ContextWindowOverflowException("test")
        assert isinstance(exception, Exception)


class TestMCPClientInitializationError:
    """Test MCPClientInitializationError."""

    def test_init(self):
        """Test initialization."""
        exception = MCPClientInitializationError("MCP init failed")
        assert str(exception) == "MCP init failed"

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = MCPClientInitializationError("test")
        assert isinstance(exception, Exception)


class TestModelThrottledException:
    """Test ModelThrottledException."""

    def test_init_with_message(self):
        """Test initialization with message."""
        message = "Model throttled"
        exception = ModelThrottledException(message)

        assert exception.message == message
        assert str(exception) == message

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = ModelThrottledException("test")
        assert isinstance(exception, Exception)


class TestSessionException:
    """Test SessionException."""

    def test_init(self):
        """Test initialization."""
        exception = SessionException("Session failed")
        assert str(exception) == "Session failed"

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = SessionException("test")
        assert isinstance(exception, Exception)


class TestToolProviderException:
    """Test ToolProviderException."""

    def test_init(self):
        """Test initialization."""
        exception = ToolProviderException("Tool provider failed")
        assert str(exception) == "Tool provider failed"

    def test_inheritance(self):
        """Test that it inherits from Exception."""
        exception = ToolProviderException("test")
        assert isinstance(exception, Exception)

    def test_with_cause(self):
        """Test exception chaining with cause."""
        original = ValueError("Original error")
        try:
            raise ToolProviderException("Tool provider failed") from original
        except ToolProviderException as exception:
            assert str(exception) == "Tool provider failed"
            assert exception.__cause__ is original

#!/usr/bin/env python3
"""
Integration tests for function-based tools
"""

import pytest
from typing import Optional, Annotated
from pydantic import BaseModel, Field

from strands import Agent, tool


@tool
def word_counter(text: str) -> str:
    """
    Count words in text.

    Args:
        text: Text to analyze
    """
    count = len(text.split())
    return f"Word count: {count}"


@tool(name="count_chars", description="Count characters in text")
def count_chars(text: str, include_spaces: Optional[bool] = True) -> str:
    """
    Count characters in text.

    Args:
        text: Text to analyze
        include_spaces: Whether to include spaces in the count
    """
    if not include_spaces:
        text = text.replace(" ", "")
    return f"Character count: {len(text)}"


class Person(BaseModel):
    name: str
    age: int
    email: Optional[str] = None


@tool
def process_person(person: Person) -> dict:
    """
    Process a person object and return formatted information.
    
    This test verifies that issue #917 is resolved - parameters typed as 
    Pydantic models should actually BE Pydantic model instances at runtime.

    Args:
        person: A person object with name, age, and optional email
    """
    # This should work if issue #917 is resolved
    # person should be a Person instance, not a dict
    assert isinstance(person, Person), f"Expected Person instance, got {type(person)}"
    
    # These should work because person is a Person instance
    formatted_name = person.name.title()
    age_category = "adult" if person.age >= 18 else "minor"
    
    return {
        "formatted_name": formatted_name,
        "age_category": age_category,
        "has_email": person.email is not None,
        "person_type": type(person).__name__
    }


@tool
def validate_constraints(
    score: Annotated[int, Field(ge=0, le=100, description="Score between 0-100")],
    email: Annotated[str, Field(pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$", description="Valid email address")]
) -> str:
    """
    Test tool with Pydantic Field constraints to verify full validation support.
    
    Args:
        score: Score value with range constraints
        email: Email with pattern validation
    """
    return f"Valid score: {score}, email: {email}"


@pytest.mark.asyncio
async def test_direct_tool_access():
    """Test direct tool access through agent.tool interface."""
    agent = Agent(tools=[word_counter, count_chars])
    
    # Test word counter
    word_result = agent.tool.word_counter(text="Hello world, this is a test")
    assert "Word count: 6" in word_result["content"][0]["text"]
    
    # Test character counter with spaces
    char_result = agent.tool.count_chars(text="Hello world!", include_spaces=True)
    assert "Character count: 12" in char_result["content"][0]["text"]
    
    # Test character counter without spaces
    char_result_no_spaces = agent.tool.count_chars(text="Hello world!", include_spaces=False)
    assert "Character count: 11" in char_result_no_spaces["content"][0]["text"]


@pytest.mark.asyncio
async def test_pydantic_model_type_hints():
    """Test that Pydantic model parameters are actual model instances (issue #917)."""
    agent = Agent(tools=[process_person])
    
    # Test with valid person data
    result = agent.tool.process_person(person={
        "name": "alice smith",
        "age": 25,
        "email": "alice@example.com"
    })
    
    content = result["content"][0]["text"]
    
    # Verify the tool received a proper Person instance
    assert "Alice Smith" in content  # name.title() worked
    assert "adult" in content        # age logic worked
    assert "True" in content         # has_email logic worked
    assert "Person" in content       # type check worked


@pytest.mark.asyncio
async def test_pydantic_field_constraints():
    """Test that Pydantic Field constraints work properly."""
    agent = Agent(tools=[validate_constraints])
    
    # Test with valid inputs
    result = agent.tool.validate_constraints(
        score=85,
        email="test@example.com"
    )
    
    content = result["content"][0]["text"]
    assert "Valid score: 85" in content
    assert "email: test@example.com" in content


@pytest.mark.asyncio
async def test_pydantic_field_constraint_validation():
    """Test that Pydantic Field constraints properly validate inputs."""
    agent = Agent(tools=[validate_constraints])
    
    # Test with invalid score (out of range)
    result = agent.tool.validate_constraints(
        score=150,  # Invalid: > 100
        email="test@example.com"
    )
    
    # Should get validation error
    assert result["status"] == "error"
    assert "validation" in result["content"][0]["text"].lower()
    
    # Test with invalid email pattern
    result = agent.tool.validate_constraints(
        score=85,
        email="invalid-email"  # Invalid: doesn't match pattern
    )
    
    # Should get validation error
    assert result["status"] == "error"
    assert "validation" in result["content"][0]["text"].lower()


@pytest.mark.asyncio
async def test_natural_language_tool_usage():
    """Test tool usage through natural language interface."""
    agent = Agent(tools=[word_counter, count_chars])
    
    # Use through natural language
    result = agent("Count the words in this sentence: 'The quick brown fox jumps over the lazy dog'")
    
    # Verify tool usage through metrics
    assert len(result.metrics.tool_metrics) > 0, "At least one tool should have been called"
    
    # Check that word_counter was specifically called
    assert "word_counter" in result.metrics.tool_metrics, "word_counter tool should have been used"
    word_counter_metrics = result.metrics.tool_metrics["word_counter"]
    assert word_counter_metrics.call_count >= 1, "word_counter should have been called at least once"
    assert word_counter_metrics.success_count >= 1, "word_counter should have succeeded at least once"

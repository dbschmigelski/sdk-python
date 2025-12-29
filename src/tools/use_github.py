"""GitHub GraphQL API integration tool for Strands Agents.

This module provides a read-only interface to GitHub's v4 GraphQL API,
allowing you to execute GitHub GraphQL queries from your Strands Agent.
The tool handles authentication, parameter validation, response formatting,
and provides user-friendly error messages with schema recommendations.

Key Features:

1. Read-Only GitHub GraphQL Access:
   • Access to GitHub's GraphQL API (v4) for queries
   • Authentication via GITHUB_TOKEN environment variable
   • Rate limit awareness and error handling
   • Mutation operations are blocked for safety

2. Safety Features:
   • Blocks all mutative operations (mutations)
   • Parameter validation with helpful error messages
   • Error handling with detailed feedback
   • Query complexity analysis

3. Response Handling:
   • JSON formatting of responses
   • Error message extraction from GraphQL responses
   • Rate limit information display
   • Pretty printing of operation details

4. Usage Example:
   ```python
   from strands import Agent
   from tools.use_github import use_github

   agent = Agent(tools=[use_github])

   # Get repository information (query)
   result = agent.tool.use_github(
       query_type="query",
       query='''
       query($owner: String!, $name: String!) {
         repository(owner: $owner, name: $name) {
           name
           description
           stargazerCount
           forkCount
           issues(first: 10) {
             nodes {
               title
               state
             }
           }
         }
       }
       ''',
       variables={"owner": "octocat", "name": "Hello-World"},
       label="Get repository information",
   )
   ```

See the use_github function docstring for more details on parameters and usage.
"""

import json
import os
import logging
from typing import Any

import requests
from strands import tool

logger = logging.getLogger(__name__)

# GitHub GraphQL API endpoint
GITHUB_GRAPHQL_URL = "https://api.github.com/graphql"


# Common mutation keywords that indicate potentially destructive operations
MUTATIVE_KEYWORDS = [
    "create",
    "update",
    "delete",
    "add",
    "remove",
    "merge",
    "close",
    "reopen",
    "lock",
    "unlock",
    "pin",
    "unpin",
    "transfer",
    "archive",
    "unarchive",
    "enable",
    "disable",
    "accept",
    "decline",
    "dismiss",
    "submit",
    "request",
    "cancel",
    "convert",
]


def get_github_token() -> str | None:
    """Get GitHub token from environment variables.

    Returns:
        GitHub token string or None if not found
    """
    return os.getenv("GITHUB_TOKEN")


def is_mutation_query(query: str) -> bool:
    """Check if a GraphQL query is a mutation based on keywords and structure.

    Args:
        query: GraphQL query string

    Returns:
        True if the query appears to be a mutation
    """
    query_lower = query.lower().strip()

    # Check if query starts with "mutation"
    if query_lower.startswith("mutation"):
        return True

    # For queries that start with "query", they are read-only
    if query_lower.startswith("query"):
        return False

    # Check for mutative keywords only in root field names (not in nested fields or descriptions)
    # This is a more conservative approach - only flag as mutation if it's
    # clearly a mutation operation
    lines = query_lower.split("\n")
    for line in lines:
        line = line.strip()
        # Skip comments and empty lines
        if line.startswith("#") or not line:
            continue
        # Look for root-level mutation operations (not nested fields)
        if any(
            line.startswith(f"{keyword}(")
            or line.startswith(f"{keyword} ")
            or line == keyword
            for keyword in MUTATIVE_KEYWORDS
        ):
            return True

    return False


def execute_github_graphql(
    query: str, variables: dict[str, Any] | None = None, token: str | None = None
) -> dict[str, Any]:
    """Execute a GraphQL query against GitHub's API.

    Args:
        query: GraphQL query string
        variables: Optional variables for the query
        token: GitHub authentication token

    Returns:
        Dictionary containing the GraphQL response

    Raises:
        requests.RequestException: If the request fails
        ValueError: If authentication fails
    """
    if not token:
        raise ValueError(
            "GitHub token is required. Set GITHUB_TOKEN environment variable."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github.v4+json",
        "User-Agent": "Strands-Agent-GitHub-Tool/1.0",
    }

    payload = {"query": query, "variables": variables or {}}

    response = requests.post(
        GITHUB_GRAPHQL_URL, headers=headers, json=payload, timeout=30
    )

    response.raise_for_status()
    response_data: dict[str, Any] = response.json()
    return response_data


def format_github_response(response: dict[str, Any]) -> str:
    """Format GitHub GraphQL response for display.

    Args:
        response: GitHub GraphQL response dictionary

    Returns:
        Formatted string representation of the response
    """
    formatted_parts = []

    # Handle errors
    if "errors" in response:
        formatted_parts.append("Errors:")
        for error in response["errors"]:
            formatted_parts.append(f"  - {error.get('message', 'Unknown error')}")
            if "locations" in error:
                locations = error["locations"]
                formatted_parts.append(f"    Locations: {locations}")

    # Handle data
    if "data" in response:
        formatted_parts.append("Data:")
        formatted_parts.append(json.dumps(response["data"], indent=2))

    # Handle rate limit info
    if "extensions" in response and "cost" in response["extensions"]:
        cost_info = response["extensions"]["cost"]
        formatted_parts.append("Rate Limit Info:")
        formatted_parts.append(
            f"  - Query Cost: {cost_info.get('requestedQueryCost', 'N/A')}"
        )
        formatted_parts.append(f"  - Node Count: {cost_info.get('nodeCount', 'N/A')}")
        if "rateLimit" in cost_info:
            rate_limit = cost_info["rateLimit"]
            formatted_parts.append(
                f"  - Remaining: {rate_limit.get('remaining', 'N/A')}"
            )
            formatted_parts.append(f"  - Reset At: {rate_limit.get('resetAt', 'N/A')}")

    return "\n".join(formatted_parts)


@tool
def use_github(
    query_type: str,
    query: str,
    label: str,
    variables: dict[str, Any] | None = None,
    confirm_mutations: bool = True,
) -> dict[str, Any]:
    """Execute read-only GitHub GraphQL API queries with comprehensive error handling and validation.

    This tool provides read-only access to GitHub's GraphQL API (v4), allowing you to execute
    queries only. All mutation operations are blocked for safety.

    Args:
        query_type: Type of GraphQL operation (must be "query")
        query: The GraphQL query string
        label: Human-readable description of the GitHub operation
        variables: Optional dictionary of variables for the query
        confirm_mutations: Deprecated parameter (mutations are always blocked)

    Returns:
        Dict containing status and response content

    Example:
        # Query example
        use_github(
            query_type="query",
            query='''
            query($owner: String!, $name: String!) {
                repository(owner: $owner, name: $name) {
                    name
                    description
                    issues(first: 10) {
                        nodes {
                            title
                            state
                        }
                    }
                }
            }
            ''',
            variables={"owner": "octocat", "name": "Hello-World"},
            label="Get repository issues"
        )
    """
    # Set default for variables if None
    if variables is None:
        variables = {}

    # Validate query_type
    if query_type.lower() not in ["query", "mutation"]:
        return {
            "status": "error",
            "content": [
                {
                    "text": f"Invalid operation type '{query_type}'. Must be either 'query' or 'mutation'."
                }
            ],
        }

    # Block all mutative operations
    is_mutation = query_type.lower() == "mutation" or is_mutation_query(query)

    if is_mutation:
        return {
            "status": "error",
            "content": [{"text": "Mutation operations are disabled. This tool only supports read-only queries."}],
        }

    logger.debug(
        f"Invoking GitHub GraphQL: label={label}, query_type={query_type}, variables={variables}"
    )

    # Get GitHub token
    github_token = get_github_token()
    if not github_token:
        return {
            "status": "error",
            "content": [
                {
                    "text": "GitHub token not found. Please set the GITHUB_TOKEN environment variable.\n"
                    "You can create a token at: https://github.com/settings/tokens"
                }
            ],
        }

    try:
        # Execute the GraphQL query
        response = execute_github_graphql(query, variables, github_token)

        # Format the response
        formatted_response = format_github_response(response)

        # Check if there were GraphQL errors
        if "errors" in response:
            return {
                "status": "error",
                "content": [
                    {"text": "GraphQL query completed with errors:"},
                    {"text": formatted_response},
                ],
            }

        return {
            "status": "success",
            "content": [{"text": formatted_response}],
        }

    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 401:
            return {
                "status": "error",
                "content": [
                    {
                        "text": "Authentication failed. Please check your GITHUB_TOKEN.\n"
                        "Make sure the token has the required permissions for this operation."
                    }
                ],
            }
        elif http_err.response.status_code == 403:
            return {
                "status": "error",
                "content": [
                    {
                        "text": "Forbidden. Your token may not have sufficient permissions for this operation.\n"
                        f"HTTP Error: {http_err}"
                    }
                ],
            }
        else:
            return {
                "status": "error",
                "content": [{"text": f"HTTP Error: {http_err}"}],
            }

    except requests.exceptions.RequestException as req_err:
        return {
            "status": "error",
            "content": [{"text": f"Request Error: {req_err}"}],
        }

    except ValueError as val_err:
        return {
            "status": "error",
            "content": [{"text": f"Configuration Error: {val_err}"}],
        }

    except Exception as ex:
        logger.warning(f"GitHub GraphQL call threw exception: {type(ex).__name__}")
        return {
            "status": "error",
            "content": [{"text": f"GitHub GraphQL call threw exception: {ex!s}"}],
        }

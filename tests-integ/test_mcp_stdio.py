import logging
import threading
from typing import List, Literal
import platform

from mcp import StdioServerParameters, stdio_client

from strands import Agent
from strands.tools.mcp.mcp_client import MCPClient
from strands.tools.mcp.mcp_types import MCPTransport
from strands.types.content import Message
from strands.types.tools import ToolUse


logging.getLogger("strands").setLevel(logging.DEBUG)
logger = logging.getLogger(__name__)


def start_calculator_server(transport: Literal["sse", "streamable-http"], port=int):
    """
    Initialize and start an MCP calculator server for integration testing.

    This function creates a FastMCP server instance that provides a simple
    calculator tool for performing addition operations. The server uses
    Server-Sent Events (SSE) transport for communication, making it accessible
    over HTTP.
    """
    from mcp.server import FastMCP

    mcp = FastMCP("Calculator Server", port=port)

    @mcp.tool(description="Calculator tool which performs calculations")
    def calculator(x: int, y: int) -> int:
        return x + y

    @mcp.tool(description="Generates a custom image")
    def generate_custom_image() -> MCPImageContent:
        try:
            with open("tests-integ/test_image.png", "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read())
                return MCPImageContent(type="image", data=encoded_image, mimeType="image/png")
        except Exception as e:
            print("Error while generating custom image: {}".format(e))

    mcp.run(transport=transport)

def get_platform_args(base_args):
    """Convert base uvx args to platform-specific format"""
    if False and platform.system() == "Windows":
        package_name = base_args[0].split("@")[0]
        return ["--from"] + base_args + [f"{package_name}.exe"]
    return base_args

def test_mcp_client():
    """
    Test should yield output similar to the following
    {'role': 'user', 'content': [{'text': 'add 1 and 2, then echo the result back to me'}]}
    {'role': 'assistant', 'content': [{'text': "I'll help you add 1 and 2 and then echo the result back to you.\n\nFirst, I'll calculate 1 + 2:"}, {'toolUse': {'toolUseId': 'tooluse_17ptaKUxQB20ySZxwgiI_w', 'name': 'calculator', 'input': {'x': 1, 'y': 2}}}]}
    {'role': 'user', 'content': [{'toolResult': {'status': 'success', 'toolUseId': 'tooluse_17ptaKUxQB20ySZxwgiI_w', 'content': [{'text': '3'}]}}]}
    {'role': 'assistant', 'content': [{'text': "\n\nNow I'll echo the result back to you:"}, {'toolUse': {'toolUseId': 'tooluse_GlOc5SN8TE6ti8jVZJMBOg', 'name': 'echo', 'input': {'to_echo': '3'}}}]}
    {'role': 'user', 'content': [{'toolResult': {'status': 'success', 'toolUseId': 'tooluse_GlOc5SN8TE6ti8jVZJMBOg', 'content': [{'text': '3'}]}}]}
    {'role': 'assistant', 'content': [{'text': '\n\nThe result of adding 1 and 2 is 3.'}]}
    """  # noqa: E501

   
    print("STARTING STDIO")
    logger.info("STARTING STDIO_STDIO")
    stdio_mcp_client = MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="uvx",
                args=get_platform_args(["awslabs.aws-documentation-mcp-server@latest"])
            )
        )
    )
    with stdio_mcp_client:
        agent = Agent(tools=stdio_mcp_client.list_tools_sync())
        logger.debug(f"Tools {agent.tool_names}")
        print(f"Tools {agent.tool_names}")
    print("DONE")
    assert 1 == 2

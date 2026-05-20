from mcp.server.fastmcp import FastMCP

mcp = FastMCP("example-server")


@mcp.tool()
def example_tool(message: str, uppercase: bool = False) -> dict:
    """Echo the input message; uppercase it when the flag is set.

    Mirrors the contract in /tools/example-tool.json.
    """
    return {"echoed": message.upper() if uppercase else message}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

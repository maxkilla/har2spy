#!/usr/bin/env python3
"""
MCP Server for har2spy - Website Search API Capture Tool
"""

import subprocess
import sys
import json
import time
from pathlib import Path
from typing import Any, Dict, List

import asyncio
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool, ToolListResult, CallToolResult, ListToolsResult,
    ListResourcesResult, ReadResourceResult, TextContent,
)
from mcp.server.session_manager import ClientSession
from mcp.client.session import ClientSession as ClientSessionClass

# Create server instance
app = Server(
    name="har2spy",
    version="2.0.0",
    instructions="MCP server for har2spy - Website Search API Capture Tool",
)

# Handler functions
async def handle_list_tools():
    return ToolListResult(
        tools=[
            Tool(
                name="har2spy.scan",
                description="Scan website and capture HAR data",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "term": {"type": "string"},
                        "auto": {"type": "boolean"},
                        "wait": {"type": "integer", "default": 5},
                        "output": {"type": "string"},
                        "format": {"type": "string", "enum": ["python", "openapi", "curl", "all"]},
                    },
                    "required": ["url", "term"],
                },
            ),
            Tool(
                name="har2spy.analyze",
                description="Analyze HAR file",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "har_file": {"type": "string"},
                        "output": {"type": "string"},
                    },
                    "required": ["har_file"],
                },
            ),
            Tool(
                name="har2spy.generate",
                description="Generate API client from HAR",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "har_file": {"type": "string"},
                        "format": {"type": "string", "enum": ["python", "openapi", "curl"]},
                        "output": {"type": "string"},
                    },
                    "required": ["har_file"],
                },
            ),
            Tool(
                name="har2spy.db-discovery",
                description="Database schema discovery from HAR",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "har_file": {"type": "string"},
                    },
                    "required": ["har_file"],
                },
            ),
        ],
    )

async def handle_call_tool(name: str, arguments: dict) -> CallToolResult:
    """Execute a har2spy tool."""
    if name == "har2spy.scan":
        return await _handle_scan(arguments)
    elif name == "har2spy.analyze":
        return await _handle_analyze(arguments)
    elif name == "har2spy.generate":
        return await _handle_generate(arguments)
    elif name == "har2spy.db-discovery":
        return await _handle_db_discovery(arguments)
    else:
        return CallToolResult(
            content=[TextContent(type="text", text=f"Unknown tool: {name}")],
            isError=True,
        )

async def _handle_scan(args: dict) -> CallToolResult:
    """Execute scan."""
    try:
        from har2spy import scan_website
        result = await scan_website(
            url=args.get("url", ""),
            term=args.get("term", ""),
            auto=args.get("auto", False),
            wait=args.get("wait", 5),
            output=args.get("output"),
            fmt=args.get("format", "python"),
        )
        return CallToolResult(
            content=[TextContent(type="text", text=f"Scan completed: {result}")],
            isError=False,
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=str(e))],
            isError=True,
        )

async def _handle_analyze(args: dict) -> CallToolResult:
    """Execute analyze."""
    try:
        from har2spy import load_har, analyze_har
        analysis = analyze_har(load_har(args.get("har_file", "")))
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(analysis, indent=2))],
            isError=False,
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=str(e))],
            isError=True,
        )

async def _handle_generate(args: dict) -> CallToolResult:
    """Execute generate."""
    try:
        from har2spy import load_har, analyze_har, generate_python_client, generate_openapi_spec, generate_curl_commands
        fmt = args.get("format", "python")
        analysis = analyze_har(load_har(args.get("har_file", "")))

        if fmt == "python":
            code = generate_python_client(analysis, base_url=args.get("url", ""))
        elif fmt == "openapi":
            code = generate_openapi_spec(analysis)
        elif fmt == "curl":
            code = generate_curl_commands(analysis)
        else:
            code = generate_python_client(analysis, base_url=args.get("url", ""))

        return CallToolResult(
            content=[TextContent(type="text", text=code)],
            isError=False,
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=str(e))],
            isError=True,
        )

async def _handle_db_discovery(args: dict) -> CallToolResult:
    """Execute database discovery."""
    try:
        from db_discovery.schema_scanner import analyze_har_for_databases, print_discoveries
        discoveries = analyze_har_for_databases(args.get("har_file", ""))
        print_discoveries(discoveries)
        return CallToolResult(
            content=[TextContent(type="text", text="Database discovery completed")],
            isError=False,
        )
    except Exception as e:
        return CallToolResult(
            content=[TextContent(type="text", text=str(e))],
            isError=True,
        )

async def main():
    # This is a placeholder - we need to use the proper server run pattern
    pass

if __name__ == "__main__":
    main()

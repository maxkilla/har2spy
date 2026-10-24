#!/usr/bin/env python3
"""
MCP Server for har2spy
Website Search API Capture Tool as an MCP server
"""
import subprocess
import sys
import json
import os
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    ServerCapabilities,
    InitializeRequest,
    InitializeResult,
    Tool,
    ListToolsResult,
    ListResourcesResult,
    ReadResourceResult,
    CallToolResult,
)
from mcp.server.models import InitializationOptions

har2spy_path = Path(__file__).parent / "har2spy.py"
server = Server("har2spy", version="2.0.0")

async def list_tools():
    return [
        Tool(
            name="har2spy.scan",
            description="Scan website and capture HAR data",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "term": {"type": "string"},
                    "auto": {"type": "boolean"},
                    "wait": {"type": "integer"},
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
                "properties": {"har_file": {"type": "string"}},
                "required": ["har_file"],
            },
        ),
        Tool(
            name="har2spy.version",
            description="Show version info",
            inputSchema={},
        ),
    ]

async def list_resources():
    return [
        {
            "uri": "har2spy://capabilities",
            "name": "har2spy-capabilities",
            "description": "har2spy capabilities",
            "mimeType": "application/json",
        }
    ]

async def read_capabilities():
    return TextContent(type="text", text=json.dumps({"capabilities": ["har2spy.scan", "har2spy.analyze", "har2spy.generate", "har2spy.db-discovery"]}))

async def handle_call_tool(name: str, args: dict):
    if name == "har2spy.scan":
        url = args.get("url", "")
        term = args.get("term", "")
        auto = args.get("auto", False)
        wait = args.get("wait", 5)
        fmt = args.get("format", "python")
        outfile = args.get("output")
        with tempfile.TemporaryDirectory() as td:
            cmd = [sys.executable, str(har2spy_path), "scan", url, "--term", term]
            if auto:
                cmd.append("--auto")
            cmd += ["--wait", str(wait)]
            if outfile:
                cmd += ["--output", outfile]
            else:
                cmd += ["--output", f"{td}/scan.har.json"]
            cmd += ["--format", fmt]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
            files = [str(f.relative_to(td)) for f in Path(td).glob("**/*") if f.is_file()]
            return {"success": r.returncode == 0, "output": r.stdout, "error": r.stderr, "files": files}

    if name == "har2spy.analyze":
        hf = args.get("har_file", "")
        with tempfile.TemporaryDirectory() as td:
            cmd = [sys.executable, str(har2spy_path), "analyze", hf]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
            return {"success": r.returncode == 0, "output": r.stdout}

    if name == "har2spy.generate":
        hf = args.get("har_file", "")
        fmt = args.get("format", "python")
        with tempfile.TemporaryDirectory() as td:
            cmd = [sys.executable, str(har2spy_path), "generate", hf, "--format", fmt]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
            return {"success": r.returncode == 0, "output": r.stdout}

    if name == "har2spy.db-discovery":
        hf = args.get("har_file", "")
        with tempfile.TemporaryDirectory() as td:
            cmd = [sys.executable, str(har2spy_path), "db-discovery", hf]
            r = subprocess.run(cmd, capture_output=True, text=True, cwd=td)
            return {"success": r.returncode == 0, "output": r.stdout}

    if name == "har2spy.version":
        return {"version": "2.0.0", "description": "har2spy v2.0"}

    return {"error": f"Unknown tool {name}"}

async def main():
    from mcp.server.lowlevel import Server as LowLevelServer

    server = LowLevelServer("har2spy")

    async def handle_init(params):
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"list": None, "call": None},
                "resources": {"list": None, "read": None},
            },
            "serverInfo": {"name": "har2spy", "version": "2.0.0"},
        }

    async def handle_tools_list():
        return [
            {"name": "har2spy.scan", "description": "Scan", "inputSchema": {"type": "object"}},
            {"name": "har2spy.analyze", "description": "Analyze"},
            {"name": "har2spy.generate", "description": "Generate"},
            {"name": "har2spy.db-discovery", "description": "DB discovery"},
        ]

    async def handle_tools_call(name, params):
        return await handle_call_tool(name, params or {})

    async def handle_resources_list():
        return [{"uri": "har2spy://cap", "name": "cap", "description": "cap", "mimeType": "app/json"}]

    async def handle_read_resource(uri):
        return TextContent(type="text", text="har2spy capabilities")

    async def handle_list_prompts():
        return []

    async def handle_get_prompt(name, params):
        return None

    server.add_request_handler("initialize", dict, handle_init)
    server.add_request_handler("tools/list", dict, handle_tools_list)
    server.add_request_handler("tools/call", dict, handle_tools_call)
    server.add_request_handler("resources/list", dict, handle_resources_list)
    server.add_request_handler("resources/read", dict, handle_read_resource)

    await server.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

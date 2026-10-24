# har2spy MCP Skill

**Description**: Extend har2spy with Model Context Protocol (MCP) integration so any AI agent that supports MCP can invoke har2spy commands natively. This skill exposes har2spy as an MCP server with tools for website scanning, analysis, API client generation, and database discovery.

**Location**: `/var/minis/skills/mcp/SKILL.md`

---

## Overview

This skill provides a complete MCP wrapper for har2spy, enabling seamless integration with any MCP-enabled agent (Claude, OpenAI Assistants, custom agents). Har2spy's core functionality becomes available through standard MCP tool calls, allowing agents to scan websites, reverse-engineer APIs, generate clients, and discover database schemas directly from their tool ecosystem.

### MCP Server Configuration

```json
{
  "mcpServers": {
    "har2spy": {
      "command": "python3",
      "args": ["/path/to/mcp_server.py"],
      "env": {
        "PYTHONPATH": "/path/to/har2spy"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description | Input Parameters |
|------|-------------|------------------|
| `har2spy.scan` | Scan a website and capture HAR data | `url`, `term`, `auto`, `wait`, `format`, `output` |
| `har2spy.analyze` | Analyze a HAR file for API endpoints | `har_file`, `output` |
| `har2spy.generate` | Generate an API client from HAR data | `har_file`, `format`, `output` |
| `har2spy.db-discovery` | Discover database schemas from HAR data | `har_file` |
| `har2spy.version` | Display version information | — |

### Resources

- `har2spy://capabilities` — JSON containing har2spy capabilities list

## Usage Examples

### Python MCP Client Example

```python
from mcp import Client

client = Client()
result = client.call_tool("har2spy.scan", {
    "url": "https://duckduckgo.com",
    "term": "coffee maker",
    "auto": True,
    "wait": 5,
    "format": "python",
    "output": "/tmp/search.har.json"
})
```

### Claude Desktop Configuration

Add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "har2spy": {
      "command": "python3",
      "args": ["/path/to/mcp_server.py"]
    }
  }
}
```

Then in conversation, ask Claude to:
- "Use har2spy to analyze example.com and show me the API endpoints"
- "Generate an API client for the search functionality on example.com"
- "Discover the database schema from the HAR data captured for example.com"

## Generated Output Formats

| Format | Extension | Use Case |
|--------|-----------|----------|
| Python API client | `.py` | Direct integration with existing Python codebase |
| OpenAPI specification | `openapi.yaml` | Swagger/OpenAPI documentation generation |
| cURL command | `curl` | Quick manual testing or documentation |

## Dependencies

- Python 3.10+
- `mcp` package (`pip install mcp`)
- har2spy installed in `PYTHONPATH`

## Version Compatibility

This skill integrates with har2spy v2.0 and above, which supports:
- JavaScript-based network interception
- Performance API fallback for non-JS sites
- Database schema discovery
- Multi-format client generation
- Interactive wizard mode

---

*Built with ❤️ by the Minis AI assistant team.*

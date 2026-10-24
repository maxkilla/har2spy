# 🕵️‍♀️ har2spy - Reverse-engineer Website Search APIs from HAR Data

## Overview

**har2spy** is a powerful tool that captures network traffic (HAR format) from website search interactions and automatically generates Python API clients that can be used to programmatically call the discovered search APIs.

### Key Features
- ✅ **Network Capture**: Injects a JavaScript spy into any website to capture all network requests
- ✅ **HAR Export**: Generates valid HTTP Archive files with full request/response details
- ✅ **API Discovery**: Analyzes HAR data to identify API endpoints, query parameters, and request bodies
- ✅ **Client Generation**: Auto-generates clean, functional Python API clients with proper parameter handling
- ✅ **Fallback Support**: Uses Performance API as fallback when JS injection fails

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip3 install requests beautifulsoup4 lxml
```

### 2. Basic Usage
```bash
# Scan a website and capture HAR data
har2spy scan https://example.com/search --term "iPhone" --auto --wait 5 -o output.har.json

# Analyze a HAR file
har2spy analyze capture.har.json -o analysis.json

# Generate Python API client
har2spy generate capture.har.json --lang python -o client.py
```

## 📋 Example Workflow

1. **Scan a website**: 
   ```bash
   har2spy scan https://duckduckgo.com --term "coffee maker" --auto --wait 5 -o duck.har.json
   ```

2. **Analyze the results**:
   ```bash
   har2spy analyze duck.har.json -o duck_analysis.json
   ```

3. **Generate Python client**:
   ```bash
   har2spy generate duck.har.json --lang python -o duck_client.py
   ```

4. **Use the generated client**:
   ```python
   from duckduckgo_api_client import TLMWtClient
   client = TLMWtClient()
   result = client.t_l_m_wt(q="coffee maker")
   print(result)
   ```

## 🔍 How It Works

1. **Browser Interaction**: The tool navigates to your target URL
2. **Network Spy**: Injects a JS module that captures all network activity
3. **Data Collection**: Captures XHR/fetch requests and fallback Performance API data
4. **API Analysis**: Identifies endpoints, query parameters, and request patterns
5. **Client Generation**: Creates a Python class with methods for each API endpoint

## 📌 Important Notes

- **XHR/Fetch Capture**: Works best on pages where search involves XHR/fetch requests
- **Form Submissions**: For traditional form submissions, manual interaction is needed
- **Query Parameters**: The tool extracts all query parameters from URLs and form data
- **Response Analysis**: Automatically detects JSON responses for easy parsing
- **Client Customization**: The generated clients include error handling and default parameters

## 📂 File Structure

```
/var/minis/workspace/har2spy/
├── har2spy.py            # Main CLI tool
├── har2spy.js            # JavaScript spy module
├── output/             # Generated HAR files
├── output/analysis.json  # HAR analysis results
├── output/*.api_client.py  # Generated Python clients
└── examples/           # Example clients and test data
```

## 🛠️ Troubleshooting

- **No entries captured?** Try increasing wait time or using `--auto` to auto-detect search elements
- **No API endpoints found?** Try manual interaction to trigger searches
- **Permission errors?** Ensure you have write access to output directory
- **Large HAR files?** The tool handles large files efficiently with streaming

## 🛡️ Security & Privacy

- All network traffic is captured locally and never sent anywhere
- HAR files contain only the data visible in your browser's Network tab
- No sensitive data is automatically extracted or stored

## 💡 Pro Tips

- Use `--wait` to increase capture duration for complex pages
- Use `--user-agent` to match the target site's expected client
- For complex sites, manually trigger searches and use `--auto` for detection
- Combine with `minis-browser-use` for advanced browser control

## 🛠️ Available Commands

| Command | Description |
|---------|-------------|
| `har2spy scan <url> --term "query"` | Scan a website and capture HAR |
| `har2spy analyze <file.har.json>` | Analyze HAR file and show endpoints |
| `har2spy generate <file.har.json> --lang python` | Generate Python API client |
| `har2spy serve --port 8080` | Start local HAR viewer server |

## 📚 Example Client Usage

The generated Python client includes methods for each discovered endpoint:

```python
# Example: Generate client
har2spy generate capture.har.json --lang python -o client.py

# Then use it:
from client import ApiClient
client = ApiClient(BASE_URL="https://api.example.com")
result = client.search_api(q="test", page=1)
```

## 🧪 Test Data

Test data is available in `/var/minis/workspace/har2spy/examples/` including:
- `test_mock.har.json` - Sample HAR file for testing
- `test_mock.har.analysis.json` - Analysis results
- `test_mock.api_client.py` - Generated client from sample data
- `duckduckgo_api_client.py` - Real example from DuckDuckGo

## 🧪 Test the Tool

Run this to test the complete pipeline:
```bash
cd /var/minis/workspace/har2spy
python3 har2spy.py scan https://httpbin.org/html --term "test" --auto --wait 3 -o test.har.json
python3 har2spy.py analyze test.har.json -o test_analysis.json
python3 har2spy.py generate test.har.json --lang python -o test_client.py
```

## 📞 Support

For issues or feature requests, please open a discussion in the Minis app or contact the development team.

---

*Built with ❤️ by the Minis AI assistant team. Powered by Alpine Linux and iSH.*
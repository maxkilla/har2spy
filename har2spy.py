#!/usr/bin/env python3
"""
har2spy v2.0 - Website Search API Capture & Client Generator

Captures HAR data from website search interactions and generates API clients.
"""

import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import subprocess

# ════════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════════
BROWSER = "minis-browser-use"
SPY_JS_PATH = "/var/minis/workspace/har2spy/har2spy.js"
OUTPUT_DIR = "/var/minis/workspace/har2spy/output"


# ════════════════════════════════════════════════════════════════
# 1. Browser Control
# ════════════════════════════════════════════════════════════════

def browser_cmd(action, **kwargs):
    """Execute a browser action via minis-browser-use CLI."""
    parts = [BROWSER, action]
    for k, v in kwargs.items():
        flag = "--" + k.replace("_", "-")
        parts.extend([flag, str(v)])
    r = subprocess.run(parts, capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        print(f"  [stderr] {r.stderr[:200]}", file=sys.stderr)
    out = r.stdout.strip()
    # Strip trailing tab_id lines
    out = "\n".join([l for l in out.split("\n") if not l.strip().startswith("tab_id:")])
    return out

def browser_eval(script):
    """Execute JS in browser, return the text value from data."""
    raw = browser_cmd("execute_js", script=script)
    try:
        parsed = json.loads(raw)
        return parsed.get("data", {}).get("text", "")
    except json.JSONDecodeError:
        return raw


# ════════════════════════════════════════════════════════════════
# 2. Network Spy Injection
# ════════════════════════════════════════════════════════════════

def inject_spy():
    """Inject the har2spy JS network interceptor into the browser."""
    js_path = Path(SPY_JS_PATH)
    if not js_path.exists():
        print("[har2spy] ERROR: har2spy.js not found at", SPY_JS_PATH)
        return False
    spy_js = js_path.read_text()
    browser_cmd("execute_js", script=spy_js)
    time.sleep(0.5)
    verify = browser_eval("return typeof window.__har2spy_exportHAR === 'function' ? 'OK' : 'FAIL'")
    return verify.strip() == "OK"

def set_marker(name):
    browser_eval(f"window.__har2spy_marker('{name}');")

def export_har(only_xhr=False):
    """Export HAR data from the browser."""
    script = f"return window.__har2spy_exportHAR({{onlyXHR: {str(only_xhr).lower()}}});"
    raw = browser_eval(script)
    if not raw or raw == "null":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ════════════════════════════════════════════════════════════════
# 3. Search Detection & SPA Support
# ════════════════════════════════════════════════════════════════

def detect_search_elements():
    """Auto-detect search inputs and buttons on the page."""
    script = '''
    (function() {
        var inputs = Array.from(document.querySelectorAll(
            'input[type="text"], input[type="search"], input[name*="q"], ' +
            'input[name*="search"], input[role="search"]'
        ));
        var btns = Array.from(document.querySelectorAll(
            'button[type="submit"], input[type="submit"], .search-button, .searchsubmit'
        ));
        var results = {inputs: [], buttons: []};
        inputs.slice(0, 5).forEach(function(i, idx) {
            var sel = i.id ? "#" + i.id : 'input[name="' + i.name + '"]';
            results.inputs.push({idx: idx, selector: sel, placeholder: i.placeholder, name: i.name, id: i.id});
        });
        btns.slice(0, 5).forEach(function(b, idx) {
            results.buttons.push({idx: idx, selector: b.id ? "#" + b.id : ".class", text: b.textContent.trim().substring(0, 30)});
        });
        return JSON.stringify(results);
    })();
    '''
    raw = browser_eval(script)
    try:
        return json.loads(raw)
    except:
        return {"inputs": [], "buttons": []}

def perform_search(term, selector=None, submit_selector=None):
    """Perform a search via JavaScript - handles forms, URL params, SPA."""
    sel = selector or "input[name='q'], input[type='search'], input[role='search']"
    script = """
    (function() {
        var sel = %s;
        var term = %s;
        var input = document.querySelector(sel);
        if (!input) return 'no_input';
        input.value = term;
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        var form = input.closest('form');
        if (form) {
            form.submit();
            return 'form_submitted';
        }
        var params = new URLSearchParams(window.location.search);
        params.set('q', term);
        window.location.search = params.toString();
        return 'url_updated';
    })();
    """ % (json.dumps(sel), json.dumps(term))
    return browser_eval(script)


# ════════════════════════════════════════════════════════════════
# 4. HAR Parsing & Analysis
# ════════════════════════════════════════════════════════════════

def load_har(path):
    with open(path) as f:
        data = json.load(f)
    if "log" not in data:
        data = {"log": data}
    return data["log"]

def analyze_har(log_data):
    """Analyze HAR log, identify API endpoints, search params, auth, rate limits."""
    entries = log_data.get("entries", [])
    api_endpoints = []
    search_endpoints = []
    auth_endpoints = []
    xhr_endpoints = []
    headers_seen = {}
    rate_limit_info = {}

    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")
        method = req.get("method", "GET").upper()

        if not url or url.startswith("data:") or url.startswith("blob:"):
            continue

        parsed = urlparse(url)
        path = parsed.path
        query_params = parse_qs(parsed.query)

        # Extract headers
        headers = {}
        for h in req.get("headers", []):
            name = h["name"].lower()
            if name not in {"host", "content-length", "connection", "accept-encoding"}:
                headers[name] = h["value"]
                headers_seen[name] = h["value"]

        # Extract body
        body = req.get("postData", {}).get("text", "") if method == "POST" else ""

        # Response info
        resp = entry.get("response", {})
        status = resp.get("status", 0)
        content = resp.get("content", {})
        mime = content.get("mimeType", "")
        resp_text = content.get("text", "")

        # Is XHR/fetch? Check if marked as such or if content-type is JSON
        is_xhr = "json" in mime.lower()
        for req_header in req.get("headers", []):
            if req_header["name"].lower() in {"x-requested-with", "x-fetch", "fetch"}:
                is_xhr = True
                break

        if is_xhr:
            xhr_endpoints.append(url)

        # Check for auth
        auth_method = "none"
        for h in req.get("headers", []):
            if h["name"].lower() == "authorization":
                auth_method = "bearer" if h["value"].startswith("Bearer ") else "header"
                break
            if h["name"].lower() == "x-api-key":
                auth_method = "apikey"
                break

        ep = {
            "method": method,
            "url": url,
            "path": path,
            "query_params": {k: v[0] if v else "" for k, v in query_params.items()},
            "request_headers": headers,
            "request_body": body,
            "status": status,
            "response_type": mime,
            "response_snippet": resp_text[:500] if resp_text else "",
            "is_xhr": is_xhr,
            "auth_method": auth_method,
        }
        api_endpoints.append(ep)

        # Search detection
        if any(k in query_params for k in ["q", "query", "search", "term", "keyword"]):
            ep["search_term_param"] = "q" if "q" in query_params else list(query_params.keys())[0]
            search_endpoints.append(ep)

        # Auth detection
        if auth_method != "none":
            auth_endpoints.append(ep)

        # Rate limit detection from response headers
        for h in resp.get("headers", []):
            name = h["name"].lower()
            if "ratelimit" in name or "x-ratelimit" in name:
                rate_limit_info[name] = h["value"]
            if name == "retry-after":
                rate_limit_info["retry-after"] = h["value"]

    # Deduplicate
    seen = set()
    unique = []
    for ep in api_endpoints:
        key = (ep["method"], ep["path"])
        if key not in seen:
            seen.add(key)
            unique.append(ep)

    return {
        "total_entries": len(entries),
        "api_endpoints": unique,
        "search_endpoints": [ep for ep in search_endpoints if ep in unique],
        "auth_endpoints": auth_endpoints,
        "xhr_endpoints": list(set(xhr_endpoints)),
        "headers_seen": headers_seen,
        "rate_limiting": rate_limit_info if rate_limit_info else {"detected": False},
    }


# ════════════════════════════════════════════════════════════════
# 5. Client Generation
# ════════════════════════════════════════════════════════════════

def generate_python(analysis, base_url=""):
    """Generate a Python API client from analysis results."""
    endpoints = analysis.get("api_endpoints", [])
    if not endpoints:
        return "# No API endpoints found in HAR data\n"

    primary = endpoints[0]
    base = base_url or f"{urlparse(primary['url']).scheme}://{urlparse(primary['url']).netloc}"
    path = primary["path"] or "/"
    method = primary["method"].lower()
    query_params = primary["query_params"]
    headers = primary.get("request_headers", {})

    # Class name
    safe_path = path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_") or "api"
    class_name = safe_path.title().replace("_", "") + "Client"

    lines = [
        '"""',
        f'Auto-generated API client for {base}',
        f'Generated by har2spy at {time.strftime("%Y-%m-%d %H:%M:%S")}',
        '"""',
        '',
        'import requests',
        'import json',
        '',
        f'class {class_name}:',
        f'    BASE_URL = {repr(base)}',
        f'    DEFAULT_HEADERS = {json.dumps(headers, indent=4)}',
        '',
    ]

    # Build method signature
    params_str = ", ".join(
        f'{k}: str = {repr(v)}' for k, v in query_params.items()
    )

    lines.append(f'    def search(self, {params_str}) -> dict:')
    lines.append(f'        """Search/query the {base} API."""')
    lines.append(f'        url = self.BASE_URL + {repr(path)}')

    if query_params:
        qp = ", ".join(f'{repr(k)}: {k}' for k in query_params)
        lines.append(f'        params = {{{qp}}}')
    else:
        lines.append('        params = {}')

    # Body handling
    body = primary.get("request_body", "")
    if body:
        try:
            post_data = json.loads(body)
            lines.append(f'        data = {repr(post_data)}')
            lines.append(f'        resp = requests.{method}(url, params=params, data=json.dumps(data), headers=self.DEFAULT_HEADERS, timeout=30)')
        except:
            lines.append(f'        resp = requests.{method}(url, params=params, data={repr(body)}, headers=self.DEFAULT_HEADERS, timeout=30)')
    else:
        lines.append(f'        resp = requests.{method}(url, params=params, headers=self.DEFAULT_HEADERS, timeout=30)')

    lines.append('        try:')
    lines.append('            return resp.json()')
    lines.append('        except Exception:')
    lines.append('            return {"text": resp.text, "status": resp.status_code}')
    lines.append('')

    # get_raw method for full access
    lines.append('    def raw(self, endpoint="/", method="GET", **kwargs) -> requests.Response:')
    lines.append('        """Fetch any endpoint and return raw response."""')
    lines.append('        url = self.BASE_URL + endpoint')
    lines.append('        return requests.request(method, url, headers=self.DEFAULT_HEADERS, **kwargs)')
    lines.append('')

    # __main__ block
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append(f'    client = {class_name}()')
    example = ", ".join(f'{k}={repr(v)}' for k, v in query_params.items())
    lines.append(f'    result = client.search({example})')
    lines.append('    print(json.dumps(result, indent=2))')
    lines.append('')

    return "\n".join(lines)


def generate_openapi(analysis, base_url=""):
    """Generate OpenAPI 3.0 spec from HAR analysis."""
    endpoints = analysis.get("api_endpoints", [])
    if not endpoints:
        return "# No endpoints"

    primary = endpoints[0]
    base = base_url or f"{urlparse(primary['url']).scheme}://{urlparse(primary['url']).netloc}"

    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Auto-generated API",
            "version": "1.0.0",
            "description": f"Generated by har2spy from {len(endpoints)} endpoints"
        },
        "servers": [{"url": base}],
        "paths": {}
    }

    for ep in endpoints:
        path = ep["path"]
        method = ep["method"].lower()
        if path not in spec["paths"]:
            spec["paths"][path] = {}

        params = []
        for k, v in ep.get("query_params", {}).items():
            params.append({
                "name": k,
                "in": "query",
                "required": False,
                "schema": {"type": "string", "default": v}
            })

        spec["paths"][path][method] = {
            "summary": f"{ep['method']} {path}",
            "parameters": params,
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {"schema": {"type": "object"}}
                    }
                }
            }
        }

    return json.dumps(spec, indent=2)


def generate_curl(analysis):
    """Generate curl commands from analysis."""
    lines = ["# Auto-generated curl commands by har2spy", ""]
    for ep in analysis.get("api_endpoints", [])[:10]:
        req = ep.get("_raw", {})
        if not req:
            url = ep["url"]
            method = ep["method"]
        else:
            headers = req.get("headers", [])
            body = req.get("postData", {}).get("text", "")
        h_str = " ".join(
            f'-H "{h["name"]}: {h["value"]}"'
            for h in req.get("headers", [])
            if h["name"].lower() not in {"host", "content-length", "connection", "accept-encoding"}
        ) if req else ""
        if req:
            body = req.get("postData", {}).get("text", "")
            b_str = f' -d "{body}"' if body else ""
        else:
            b_str = ""
        lines.append(f"curl -{method.lower()} {h_str} {repr(url)}{b_str}")
    return "\n".join(lines)


FORMAT_FUNCS = {
    "python": ("Python client", generate_python),
    "openapi": ("OpenAPI spec", generate_openapi),
    "curl": ("curl commands", generate_curl),
}


# ════════════════════════════════════════════════════════════════
# 6. CLI Entry Points
# ════════════════════════════════════════════════════════════════

def cmd_scan(args):
    """Scan a website and capture HAR data."""
    print(f"[har2spy] 🚀 Starting scan")
    print(f"   URL: {args.url}")
    print(f"   Term: '{args.term}'")
    print(f"   Auto-detect: {args.auto}, Wait: {args.wait}s")

    # Navigate
    print("[har2spy] → Navigating...")
    browser_cmd("navigate", url=args.url)
    time.sleep(2)

    # Inject spy
    print("[har2spy] → Injecting network spy...")
    if inject_spy():
        print("[har2spy] ✓ Spy active")
    else:
        print("[har2spy] ⚠ Spy injection failed — using Performance API fallback")

    # Auto-detect search if needed
    if args.auto:
        elements = detect_search_elements()
        inputs = len(elements.get("inputs", []))
        buttons = len(elements.get("buttons", []))
        print(f"[har2spy] → Found {inputs} search inputs, {buttons} buttons")

    # Set marker
    set_marker("search_start")

    # Perform search
    if not args.search_selector:
        sel = "input[name='q'], input[type='search'], input[role='search']"
    else:
        sel = args.search_selector
    print(f"[har2spy] → Performing search...")
    result = perform_search(args.term, sel)
    print(f"[har2spy]   Search: {result}")
    time.sleep(args.wait)

    # Export HAR
    print("[har2spy] → Exporting HAR...")
    har_data = export_har(only_xhr=False)

    if har_data is None:
        print("[har2spy] ⚠ No HAR data captured via spy")
        # Fallback: capture from Performance API
        har_data = capture_performance()
        if har_data is None:
            print("[har2spy] ERROR: No data captured")
            return

    entries = har_data.get("log", {}).get("entries", [])
    print(f"[har2spy] ✓ Captured {len(entries)} entries")

    # Save HAR
    if args.output:
        output_path = args.output
    else:
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', args.url)
        output_path = os.path.join(OUTPUT_DIR, f"{safe}_{int(time.time())}.har.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(har_data, f, indent=2)
    print(f"[har2spy] ✓ HAR saved: {output_path}")

    # Analyze
    analysis = analyze_har(har_data["log"])
    print(f"[har2spy] → Analysis")
    print(f"   API endpoints:   {len(analysis['api_endpoints'])}")
    print(f"   Search endpoints: {len(analysis['search_endpoints'])}")
    print(f"   XHR endpoints:    {len(analysis['xhr_endpoints'])}")

    if analysis["rate_limiting"].get("detected", False):
        print(f"[har2spy] ⚠ Rate limiting detected!")
        for k, v in analysis["rate_limiting"].items():
            print(f"   {k}: {v}")

    if analysis["auth_endpoints"]:
        auth_methods = set(ep["auth_method"] for ep in analysis["auth_endpoints"])
        print(f"[har2spy] 🔐 Auth detected: {', '.join(auth_methods)}")

    # Show top endpoints
    for ep in analysis["api_endpoints"][:5]:
        flag = "XHR" if ep["is_xhr"] else "---"
        print(f"   [{flag}] {ep['method']} {ep['path']} → {ep['status']} ({ep.get('time_ms', '?')}ms)")

    # Save analysis
    analysis_path = output_path.replace(".har.json", ".analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"[har2spy] ✓ Analysis: {analysis_path}")

    # Generate client(s)
    fmt = args.format
    formats = list(FORMAT_FUNCS.keys()) if fmt == "all" else [fmt]
    for f in formats:
        if f not in FORMAT_FUNCS:
            print(f"[har2spy] ⚠ Unknown format: {f}")
            continue
        label, gen_fn = FORMAT_FUNCS[f]
        client = gen_fn(analysis, base_url=args.url)
        client_path = output_path.replace(".har.json", f".client.{f}")
        with open(client_path, "w") as cf:
            cf.write(client)
        print(f"[har2spy] ✓ {label}: {client_path}")

    return output_path


def capture_performance():
    """Fallback: capture from Performance API."""
    script = """
    var entries = performance.getEntriesByType('resource');
    var harEntries = entries.map(function(e) {
        return {
            startedDateTime: new Date(e.startTime).toISOString(),
            time: Math.round(e.duration),
            request: {
                method: 'GET',
                url: e.name,
                httpVersion: 'HTTP/1.1',
                cookies: [],
                headers: [],
                queryString: [],
                bodySize: -1,
                headersSize: -1,
                content: { size: -1, mimeType: '' }
            },
            response: {
                status: 0,
                statusText: '',
                httpVersion: 'HTTP/1.1',
                cookies: [],
                headers: [],
                headersSize: -1,
                bodySize: -1,
                content: { size: -1, mimeType: 'unknown', text: undefined }
            },
            cache: {},
            timings: { send: 0, wait: Math.round(e.duration / 2), receive: Math.round(e.duration / 2) },
            serverIPAddress: '',
            connection: '',
            pageref: 'page_1',
            _xhr: false
        };
    });
    return JSON.stringify({
        log: {
            version: '1.2',
            creator: { name: 'har2spy-perf-fallback' },
            pages: [{ id: 'page_1', startedDateTime: new Date(0).toISOString(), pageTimings: { onLoad: 0, onContentEvent: -1 } }],
            entries: harEntries
        }
    });
    """
    raw = browser_eval(script)
    if raw:
        try:
            return json.loads(raw)
        except:
            pass
    return None


def cmd_analyze(args):
    """Analyze HAR file."""
    log = load_har(args.har_file)
    analysis = analyze_har(log)
    print(json.dumps(analysis, indent=2, default=str))
    out_path = args.output or args.har_file.replace(".har.json", ".analysis.json")
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\n[har2spy] Analysis saved: {out_path}", file=sys.stderr)


def cmd_generate(args):
    """Generate API client from HAR file."""
    log = load_har(args.har_file)
    analysis = analyze_har(log)
    fmt = args.format
    if fmt not in FORMAT_FUNCS:
        print(f"Unknown format: {fmt}")
        sys.exit(1)
    label, gen_fn = FORMAT_FUNCS[fmt]
    client = gen_fn(analysis, base_url=args.base_url)
    out_path = args.output or args.har_file.replace(".har.json", f".client.{fmt}")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write(client)
    print(f"[har2spy] Generated {label}: {out_path}")
    if args.preview:
        print(client[:2000])


def cmd_wizard(args):
    """Interactive wizard mode."""
    print("=" * 60)
    print("🧭 har2spy Interactive Wizard")
    print("=" * 60)
    url = input("1. Target URL to scan: ").strip()
    term = input("2. Search term to use: ").strip()
    wait_str = input("3. Seconds to wait for network (default 5): ").strip() or "5"
    auto = input("4. Auto-detect search elements? (y/N): ").strip().lower() == "y"
    fmt = input("5. Output format (python/openapi/curl/all) [python]: ").strip() or "python"

    # Build synthetic args
    class Args:
        pass
    a = Args()
    a.url = url
    a.term = term
    a.auto = auto
    a.wait = int(wait_str)
    a.output = None
    a.format = fmt
    a.search_selector = None

    cmd_scan(a)


def cmd_version(args):
    print("har2spy v2.0 - Website Search API Capture Tool")


# ════════════════════════════════════════════════════════════════
# Main
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        prog="har2spy",
        description="🕵️‍♀️ Reverse-engineer website search APIs from HAR data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan a website's search and capture HAR
  har2spy scan https://duckduckgo.com --term "iPhone" --auto --wait 5

  # Analyze an existing HAR file
  har2spy analyze capture.har.json

  # Generate Python API client
  har2spy generate capture.har.json --format python -o client.py

  # Interactive wizard mode
  har2spy wizard
        """
    )

    subparsers = parser.add_subparsers(dest="command")

    # scan
    p = subparsers.add_parser("scan", help="Scan a website and capture HAR")
    p.add_argument("url", help="Target URL to scan")
    p.add_argument("--term", "-q", required=True, help="Search term/query")
    p.add_argument("--auto", action="store_true", help="Auto-detect search elements")
    p.add_argument("--search-selector", "-s", default=None, help="CSS selector for search input")
    p.add_argument("--wait", "-w", type=int, default=5, help="Seconds to wait (default: 5)")
    p.add_argument("--output", "-o", default=None, help="Output HAR file path")
    p.add_argument("--format", "-f", choices=list(FORMAT_FUNCS.keys()) + ["all"], default="python",
                   help="Output format (default: python)")
    p.set_defaults(func=cmd_scan)

    # analyze
    p = subparsers.add_parser("analyze", help="Analyze a HAR file")
    p.add_argument("har_file", help="HAR file to analyze")
    p.add_argument("--output", "-o", default=None, help="Output analysis file")
    p.set_defaults(func=cmd_analyze)

    # generate
    p = subparsers.add_parser("generate", help="Generate API client from HAR")
    p.add_argument("har_file", help="HAR file")
    p.add_argument("--format", "-f", choices=list(FORMAT_FUNCS.keys()) + ["all"], default="python",
                   help="Output format (default: python)")
    p.add_argument("--base-url", default="", help="Override base URL")
    p.add_argument("--output", "-o", default=None, help="Output file")
    p.add_argument("--preview", action="store_true", help="Print generated code")
    p.set_defaults(func=cmd_generate)

    # wizard
    p = subparsers.add_parser("wizard", help="Interactive guided scan")
    p.set_defaults(func=cmd_wizard)

    # version
    p = subparsers.add_parser("version", help="Show version")
    p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
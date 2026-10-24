#!/usr/bin/env python3
"""
har2spy v2.0 - Website Search API Capture & Client Generator

Captures HAR data from website search interactions and generates API clients.
Includes database schema discovery from captured HAR data.
"""

import argparse, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import subprocess

# ════════════════════════════════════════════════════════════════
# Config
# ════════════════════════════════════════════════════════════════
BROWSER = "python3"
SPY_JS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "har2spy.js")
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")


# ════════════════════════════════════════════════════════════════
# Browser Control
# ════════════════════════════════════════════════════════════════

def browser_cmd(action, **kwargs):
    parts = ["python3", "bridge_client.py", action]
    for k, v in kwargs.items():
        flag = "--" + k.replace("_", "-")
        parts.extend([flag, str(v)])
    r = subprocess.run(parts, capture_output=True, text=True, timeout=60)
    out = r.stdout.strip()
    out = "\n".join([l for l in out.split("\n") if not l.strip().startswith("tab_id:")])
    return out

def browser_eval(script):
    raw = browser_cmd("execute_js", script=script)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed.get("data", {}).get("text", "")
        return str(parsed)
    except (json.JSONDecodeError, TypeError):
        return raw


# ════════════════════════════════════════════════════════════════
# Network Spy
# ════════════════════════════════════════════════════════════════

def inject_spy():
    js_path = Path(SPY_JS_PATH)
    if not js_path.exists():
        print("[har2spy] ERROR: har2spy.js not found")
        return False
    browser_cmd("inject_spy", script=str(js_path))
    time.sleep(0.5)
    verify = browser_eval("return typeof window.__har2spy_exportHAR === 'function' ? 'OK' : 'FAIL'")
    if verify.strip() == "OK" or verify.strip() == "injected":
        return True
    return False

def set_marker(name):
    browser_eval(f"window.__har2spy_marker('{name}');")

def export_har(only_xhr=False):
    raw = browser_eval(f"return window.__har2spy_exportHAR({{onlyXHR: {str(only_xhr).lower()}}});")
    if not raw or raw == "null":
        return None
    try:
        return json.loads(raw)
    except:
        return None


# ════════════════════════════════════════════════════════════════
# Search Detection
# ════════════════════════════════════════════════════════════════

def detect_search_elements():
    script = '''
    (function() {
        var inputs = Array.from(document.querySelectorAll(
            'input[type="text"], input[type="search"], input[name*="q"], ' +
            'input[name*="search"], input[role="search"]'
        ));
        var btns = Array.from(document.querySelectorAll(
            'button[type="submit"], input[type="submit"], .search-button, .searchsubmit'
        ));
        return JSON.stringify({
            inputs: inputs.slice(0, 5).map(function(i, idx) {
                var sel = i.id ? "#" + i.id : 'input[name="' + i.name + '"]';
                return {idx: idx, selector: sel, placeholder: i.placeholder, name: i.name};
            }),
            buttons: btns.slice(0, 5).map(function(b) {
                return {selector: b.id ? "#" + b.id : ".class", text: b.textContent.trim().substring(0, 30)};
            })
        });
    })();
    '''
    raw = browser_eval(script)
    try:
        return json.loads(raw)
    except:
        return {"inputs": [], "buttons": []}

def perform_search(term, selector=None, wait=2):
    sel = selector or "input[name='q'], input[type='search'], input[role='search']"
    script = f"""
        var sel = {json.dumps(sel)};
        var term = {json.dumps(term)};
        var input = document.querySelector(sel);
        if (!input) return 'no_input';
        input.value = term;
        input.dispatchEvent(new Event('input', {{bubbles: true}}));
        input.dispatchEvent(new Event('change', {{bubbles: true}}));
        var form = input.closest('form');
        if (form) {{ form.submit(); return 'form_submitted'; }}
        var params = new URLSearchParams(window.location.search);
        params.set('q', term);
        window.location.search = params.toString();
        return 'url_updated';
    """
    return browser_eval(script)


# ════════════════════════════════════════════════════════════════
# HAR Analysis
# ════════════════════════════════════════════════════════════════

def load_har(path):
    with open(path) as f:
        data = json.load(f)
    if "log" not in data:
        data = {"log": data}
    return data["log"]

def infer_json_structure(data, path=""):
    result = {"path": path or "root", "type": type(data).__name__, "fields": [], "nested_objects": {}, "arrays": {}, "sample_values": {}}
    if isinstance(data, dict):
        for key, value in data.items():
            result["fields"].append({"name": key, "type": type(value).__name__, "sample": str(value)[:100]})
            result["sample_values"][key] = str(value)[:100]
            if isinstance(value, dict):
                result["nested_objects"][key] = infer_json_structure(value, f"{path}.{key}")
            elif isinstance(value, list) and value:
                result["arrays"][key] = {"item_type": type(value[0]).__name__, "item_count": len(value)}
        result["inferred_table"] = _guess_table_name(path, data)
    elif isinstance(data, list) and data:
        result["item_count"] = len(data)
        result["sample_object"] = infer_json_structure(data[0], f"{path}[0]")
    return result if result["fields"] or result["nested_objects"] else None

def _guess_table_name(path, data):
    parts = [p for p in path.split("/") if p and p.isalpha()]
    if parts:
        return parts[-1]
    if isinstance(data, dict):
        for key in data.keys():
            if key.lower() in {"users", "products", "orders", "items", "posts", "categories"}:
                return key
    return None

def analyze_response(entry):
    resp = entry.get("response", {})
    content = resp.get("content", {})
    mime = content.get("mimeType", "")
    text = content.get("text", "")
    size = content.get("size", 0)
    result = {"mime_type": mime, "is_json": "json" in mime.lower(), "is_html": "html" in mime.lower(),
              "response_size": size, "response_snippet": text[:200] if text else ""}
    if result["is_json"] and text:
        try:
            result["json_structure"] = infer_json_structure(json.loads(text))
        except:
            result["json_parse_error"] = True
    return result

def analyze_har(log_data):
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

        headers = {}
        for h in req.get("headers", []):
            name = h["name"].lower()
            if name not in {"host", "content-length", "connection", "accept-encoding"}:
                headers[name] = h["value"]
                headers_seen[name] = h["value"]

        body = req.get("postData", {}).get("text", "")[:2000] if method == "POST" else ""
        resp = entry.get("response", {})
        status = resp.get("status", 0)
        content = resp.get("content", {})
        mime = content.get("mimeType", "")
        resp_text = content.get("text", "")

        is_xhr = "json" in mime.lower()

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
            "_raw": entry,
        }
        api_endpoints.append(ep)

        if any(k in query_params for k in ["q", "query", "search", "term", "keyword"]):
            search_endpoints.append(ep)

        for h in req.get("headers", []):
            if h["name"].lower() == "authorization":
                ep["auth_method"] = "bearer" if h["value"].startswith("Bearer ") else "header"
                break
            if h["name"].lower() == "x-api-key":
                ep["auth_method"] = "apikey"
                break
        if ep.get("auth_method"):
            auth_endpoints.append(ep)

        for h in resp.get("headers", []):
            name = h["name"].lower()
            if "ratelimit" in name or name == "retry-after":
                rate_limit_info[name] = h["value"]

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
        "search_endpoints": search_endpoints,
        "auth_endpoints": auth_endpoints,
        "xhr_endpoints": list(set(xhr_endpoints)),
        "headers_seen": headers_seen,
        "rate_limiting": rate_limit_info if rate_limit_info else {"detected": False},
    }


# ════════════════════════════════════════════════════════════════
# Client Generation
# ════════════════════════════════════════════════════════════════

def generate_python(analysis, base_url=""):
    endpoints = analysis.get("api_endpoints", [])
    if not endpoints:
        return "# No API endpoints found in HAR data\n"
    primary = endpoints[0]
    base = base_url or f"{urlparse(primary['url']).scheme}://{urlparse(primary['url']).netloc}"
    path = primary["path"] or "/"
    method = primary["method"].lower()
    query_params = primary["query_params"]
    headers = primary.get("request_headers", {})

    safe_path = path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_") or "api"
    class_name = safe_path.title().replace("_", "") + "Client"

    lines = [
        '"""',
        f'Auto-generated API client for {base}',
        f'Generated by har2spy at {time.strftime("%Y-%m-%d %H:%M:%S")}',
        '"""',
        '', 'import requests', 'import json', '',
        f'class {class_name}:',
        f'    BASE_URL = {repr(base)}',
        f'    DEFAULT_HEADERS = {json.dumps(headers, indent=4)}',
        '',
    ]
    params_str = ", ".join(f'{k}: str = {repr(v)}' for k, v in query_params.items())
    lines.append(f'    def search(self, {params_str}) -> dict:')
    lines.append(f'        """Query the {base} API."""')
    lines.append(f'        url = self.BASE_URL + {repr(path)}')
    lines.append(f'        params = {{{", ".join(f"{repr(k)}: {k}" for k in query_params)}}}' if query_params else '        params = {}')
    lines.append(f'        resp = requests.{method}(url, params=params, headers=self.DEFAULT_HEADERS, timeout=30)')
    lines.append('        try:')
    lines.append('            return resp.json()')
    lines.append('        except Exception:')
    lines.append('            return {"text": resp.text, "status": resp.status_code}')
    lines.append('')
    lines.append('if __name__ == "__main__":')
    lines.append(f'    client = {class_name}()')
    example = ", ".join(f'{k}={repr(v)}' for k, v in query_params.items())
    lines.append(f'    result = client.search({example})')
    lines.append('    print(json.dumps(result, indent=2))')
    lines.append('')
    return "\n".join(lines)

def generate_openapi(analysis, base_url=""):
    endpoints = analysis.get("api_endpoints", [])
    if not endpoints:
        return "# No endpoints\n"
    primary = endpoints[0]
    base = base_url or f"{urlparse(primary['url']).scheme}://{urlparse(primary['url']).netloc}"
    spec = {"openapi": "3.0.0", "info": {"title": "Auto-generated API", "version": "1.0.0"},
            "servers": [{"url": base}], "paths": {}}
    for ep in endpoints:
        path = ep["path"] or "/"
        method = ep["method"].lower()
        if path not in spec["paths"]:
            spec["paths"][path] = {}
        params = [{"name": k, "in": "query", "required": False,
                   "schema": {"type": "string", "default": v}}
                  for k, v in ep.get("query_params", {}).items()]
        spec["paths"][path][method] = {
            "summary": f'{ep["method"]} {path}',
            "parameters": params,
            "responses": {"200": {"description": "Successful response",
                    "content": {"application/json": {"schema": {"type": "object"}}}}},
        }
    return json.dumps(spec, indent=2)

def generate_curl(analysis):
    lines = ["# Auto-generated curl commands", ""]
    for ep in analysis.get("api_endpoints", [])[:10]:
        req = ep.get("_raw", {})
        url = ep["url"]
        method = ep["method"]
        headers = [
            h for h in req.get("headers", [])
            if h["name"].lower() not in {"host", "content-length", "connection", "accept-encoding"}
        ]
        h_str = " ".join(f'-H "{h["name"]}: {h["value"]}"' for h in headers)
        body = req.get("postData", {}).get("text", "")
        b_str = f' -d "{body}"' if body else ""
        lines.append(f"curl -{method.lower()} {h_str} {repr(url)}{b_str}")
    return "\n".join(lines)

FORMAT_FUNCS = {
    "python": ("Python client", generate_python),
    "openapi": ("OpenAPI spec", generate_openapi),
    "curl": ("curl commands", generate_curl),
}


# ════════════════════════════════════════════════════════════════
# Database Schema Discovery (imported)
# ════════════════════════════════════════════════════════════════

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_discovery.schema_scanner import analyze_har_for_databases, print_discoveries


# ════════════════════════════════════════════════════════════════
# CLI Commands
# ════════════════════════════════════════════════════════════════

def cmd_scan(args):
    print(f"[har2spy] 🚀 Starting scan")
    print(f"   URL: {args.url}")
    print(f"   Term: '{args.term}'")
    print(f"   Auto-detect: {args.auto}, Wait: {args.wait}s")

    browser_cmd("navigate", url=args.url)
    time.sleep(2)

    print("[har2spy] → Injecting network spy...")
    if inject_spy():
        print("[har2spy] ✓ Spy active")
    else:
        print("[har2spy] ⚠ Spy injection failed")

    set_marker("search_start")

    if args.auto:
        elements = detect_search_elements()
        print(f"[har2spy] → Found {len(elements.get('inputs', []))} search inputs, {len(elements.get('buttons', []))} buttons")

    sel = args.search_selector or "input[name='q'], input[type='search'], input[role='search']"
    print(f"[har2spy] → Performing search...")
    result = perform_search(args.term, sel)
    print(f"[har2spy]   Search: {result}")
    time.sleep(args.wait)

    print("[har2spy] → Exporting HAR...")
    har_data = export_har(only_xhr=False)

    if har_data is None:
        print("[har2spy] ⚠ No HAR data captured")
        return

    entries = har_data.get("log", {}).get("entries", [])
    print(f"[har2spy] ✓ Captured {len(entries)} entries")

    output_path = args.output or os.path.join(OUTPUT_DIR,
        f"{re.sub(r'[^a-zA-Z0-9_-]', '_', args.url)}_{int(time.time())}.har.json")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(har_data, f, indent=2)
    print(f"[har2spy] ✓ HAR saved: {output_path}")

    analysis = analyze_har(har_data.get("log", har_data))
    print(f"[har2spy] → Analysis")
    print(f"   API endpoints:   {len(analysis['api_endpoints'])}")
    print(f"   Search endpoints: {len(analysis['search_endpoints'])}")

    analysis_path = output_path.replace(".har.json", ".analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"[har2spy] ✓ Analysis: {analysis_path}")

    for fmt in ([list(FORMAT_FUNCS.keys())] if args.format == "all" else [args.format]):
        pass
    formats = list(FORMAT_FUNCS.keys()) if args.format == "all" else [args.format]
    for f in formats:
        label, gen_fn = FORMAT_FUNCS[f]
        client = gen_fn(analysis, base_url=args.url)
        client_path = output_path.replace(".har.json", f".client.{f}")
        with open(client_path, "w") as cf:
            cf.write(client)
        print(f"[har2spy] ✓ {label}: {client_path}")

    return output_path

def cmd_analyze(args):
    log = load_har(args.har_file)
    analysis = analyze_har(log)
    print(json.dumps(analysis, indent=2, default=str))
    out_path = args.output or args.har_file.replace(".har.json", ".analysis.json")
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\n[har2spy] Analysis saved: {out_path}", file=sys.stderr)

def cmd_generate(args):
    log = load_har(args.har_file)
    analysis = analyze_har(log)
    fmt = args.format
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
    print("=" * 60)
    print("🧭 har2spy Interactive Wizard")
    print("=" * 60)
    url = input("1. Target URL to scan: ").strip()
    term = input("2. Search term to use: ").strip()
    wait_str = input("3. Seconds to wait for network (default 5): ").strip() or "5"
    auto = input("4. Auto-detect search elements? (y/N): ").strip().lower() == "y"
    fmt = input("5. Output format (python/openapi/curl/all) [python]: ").strip() or "python"

    class Args:
        pass
    a = Args()
    a.url, a.term, a.auto, a.wait = url, term, auto, int(wait_str)
    a.output, a.format, a.search_selector = None, fmt, None
    cmd_scan(a)

def cmd_version(args):
    print("har2spy v2.0 - Website Search API Capture Tool")

def cmd_db_discovery(args):
    """Run database schema discovery on a HAR file."""
    print("[har2spy] Starting database schema discovery...")
    discoveries = analyze_har_for_databases(args.har_file)
    print_discoveries(discoveries)


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
  har2spy scan https://duckduckgo.com --term "iPhone" --auto --wait 5
  har2spy analyze capture.har.json
  har2spy generate capture.har.json --format python -o client.py
  har2spy db-discovery capture.har.json
  har2spy wizard
        """
    )
    subparsers = parser.add_subparsers(dest="command")

    p = subparsers.add_parser("scan", help="Scan a website and capture HAR")
    p.add_argument("url", help="Target URL to scan")
    p.add_argument("--term", "-q", required=True, help="Search term/query")
    p.add_argument("--auto", action="store_true", help="Auto-detect search elements")
    p.add_argument("--search-selector", "-s", default=None, help="CSS selector for search input")
    p.add_argument("--wait", "-w", type=int, default=5, help="Seconds to wait")
    p.add_argument("--output", "-o", default=None, help="Output HAR file path")
    p.add_argument("--format", "-f", choices=list(FORMAT_FUNCS.keys()) + ["all"], default="python")
    p.set_defaults(func=cmd_scan)

    p = subparsers.add_parser("analyze", help="Analyze a HAR file")
    p.add_argument("har_file")
    p.add_argument("--output", "-o", default=None)
    p.set_defaults(func=cmd_analyze)

    p = subparsers.add_parser("generate", help="Generate API client from HAR")
    p.add_argument("har_file")
    p.add_argument("--format", "-f", choices=list(FORMAT_FUNCS.keys()), default="python")
    p.add_argument("--base-url", default="")
    p.add_argument("--output", "-o", default=None)
    p.add_argument("--preview", action="store_true")
    p.set_defaults(func=cmd_generate)

    p = subparsers.add_parser("db-discovery", help="Database & schema discovery from HAR")
    p.add_argument("har_file", help="HAR file to analyze")
    p.set_defaults(func=cmd_db_discovery)

    subparsers.add_parser("wizard", help="Interactive guided scan").set_defaults(func=cmd_wizard)
    subparsers.add_parser("version", help="Show version").set_defaults(func=cmd_version)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()
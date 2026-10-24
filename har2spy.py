#!/usr/bin/env python3
"""
har2spy — Reverse-engineer website search APIs from HAR data.

Usage:
  har2spy scan <url> --term "iPhone" --search-selector "input[name=q]" --submit-selector "button[type=submit]"
  har2spy scan <url> --term "iPhone" --auto
  har2spy analyze <har_file.json>
  har2spy generate <har_file.json> --lang python --output api_client.py
  har2spy serve  # Start local HAR viewer on :8080

Dependencies: pip install requests beautifulsoup4 lxml
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tempfile
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

# ─── Browser control wrapper ─────────────────────────────────

# Browser control via minis-browser-use CLI (no extra import needed)
BROWSER_BIN = "minis-browser-use"


def browser_exec(action: str, **kwargs) -> str:
    """Execute a browser action via minis-browser-use CLI and return stdout.

    The CLI appends 'tab_id: N' after JSON output — we strip that.
    """
    parts = ["minis-browser-use", action]
    for k, v in kwargs.items():
        flag = "--" + k.replace("_", "-")
        parts.extend([flag, str(v)])
    result = subprocess.run(parts, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"  [⚠] {action} returned exit {result.returncode}", file=sys.stderr)
        if result.stderr:
            print(f"  [stderr] {result.stderr[:500]}", file=sys.stderr)
    out = result.stdout.strip()
    # Strip trailing tab_id line(s)
    lines = [l for l in out.split('\n') if not l.strip().startswith('tab_id:')]
    return '\n'.join(lines)


def browser_exec_json(action: str, **kwargs) -> dict:
    """Execute a browser action and return parsed JSON.

    The minis-browser-use CLI returns a JSON structure:
    {
      "action": "...",
      "data": { ... },
      "ok": true,
      "tool": "minis-browser-use",
      ...
    }

    The 'data' field contains a 'text' field that often has 'tab_id: N' appended.
    This function extracts and cleans it.
    """
    raw = browser_exec(action, **kwargs)
    try:
        parsed = json.loads(raw)
        if "data" in parsed:
            data = parsed["data"]
            if "text" in data:
                text = data["text"]
                clean_lines = [l for l in text.split('\n') if not l.strip().startswith('tab_id:')]
                data["text"] = '\n'.join(clean_lines).strip()
            return data
        return parsed
    except json.JSONDecodeError:
        start = raw.find('{')
        end = raw.rfind('}')
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end + 1])
                if "data" in parsed:
                    data = parsed["data"]
                    if "text" in data:
                        text = data["text"]
                        clean_lines = [l for l in text.split('\n') if not l.strip().startswith('tab_id:')]
                        data["text"] = '\n'.join(clean_lines).strip()
                    return data
                return parsed
            except:
                pass
        return {"error": f"Could not parse JSON: {raw[:200]}"}


def read_js_module(name: str = "har2spy") -> str:
    """Read embedded JS from the package directory."""
    js_path = Path(__file__).parent / f"{name}.js"
    if js_path.exists():
        return js_path.read_text()
    # Fallback: use the full module inline
    return ""


# ─── HAR parsing & analysis ──────────────────────────────────

def load_har(path: str) -> dict:
    """Load a HAR file and return the parsed log dict."""
    with open(path) as f:
        data = json.load(f)
    if "log" not in data:
        data = {"log": data}
    return data["log"]


def analyze_har(log: dict) -> dict:
    """
    Analyze HAR entries and identify API/search endpoints.

    Returns a structured dict with:
      - api_endpoints: list of discovered API routes
      - search_endpoints: endpoints with query params that look like search
      - auth_endpoints: login/token endpoints
      - form_endpoints: endpoints that accept form submissions
      - xhr_endpoints: entries captured from XHR/fetch (most reliable)
    """
    entries = log.get("entries", [])

    api_endpoints = []
    search_endpoints = []
    auth_endpoints = []

    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")
        method = req.get("method", "GET").upper()

        if not url or url.startswith("data:") or url.startswith("blob:"):
            continue

        parsed = urlparse(url)
        path = parsed.path

        # Skip static assets
        static_ext = re.search(r'\.(css|js|png|jpe?g|gif|ico|svg|woff2?|webp|mp4|mp3)$', path, re.I)
        if static_ext:
            continue

        qs = parse_qs(parsed.query)

        # Build endpoint descriptor
        endpoint = {
            "method": method,
            "url": url,
            "path": path,
            "query_params": list(qs.keys()),
            "query_values": {k: v[:3] if isinstance(v, list) else v for k, v in qs.items()},
            "request_body": req.get("postData", {}).get("text", "")[:2000] if req.get("postData") else "",
            "request_headers": {h["name"].lower(): h["value"] for h in req.get("headers", [])},
            "status": entry.get("response", {}).get("status", 0),
            "response_type": detect_response_type(entry.get("response", {}).get("content", {}).get("mimeType", "")),
            "response_snippet": (entry.get("response", {}).get("content", {}).get("text", "") or "")[:500],
            "timings": entry.get("timings", {}),
            "time_ms": entry.get("time", 0),
            "is_xhr": entry.get("_xhr", False) or _looks_like_xhr(entry),
            "_raw": entry  # full entry for code generation
        }

        api_endpoints.append(endpoint)

        # Search detection
        search_params = ["q", "query", "search", "term", "keyword", "s", "q_", "searchterm"]
        if any(p in qs for p in search_params) or any(p in [h["name"].lower() for h in req.get("headers", [])] for p in ["x-search"]):
            endpoint["category"] = "search"
            search_endpoints.append(endpoint)

        # Auth detection
        auth_paths = ["/login", "/auth", "/token", "/signin", "/oauth", "/api_key"]
        if any(p in path.lower() for p in auth_paths) or "authorization" in endpoint["request_headers"]:
            endpoint["category"] = "auth"
            auth_endpoints.append(endpoint)

    # Sort by XHR status (XHR entries are most reliable for API detection)
    # Then by time (most recent)
    api_endpoints.sort(key=lambda e: (not e["is_xhr"], -e.get("time_ms", 0)))

    return {
        "total_entries": len(entries),
        "api_endpoints": api_endpoints,
        "search_endpoints": search_endpoints,
        "auth_endpoints": auth_endpoints,
        "analyzed_at": datetime.now().isoformat()
    }


def _looks_like_xhr(entry: dict) -> bool:
    """Heuristic: an entry looks like an XHR if its response content-type is JSON
    and content-length is small, or if method is GET/POST with JSON content-type."""
    resp = entry.get("response", {})
    ct = resp.get("content", {}).get("mimeType", "").lower()
    return "json" in ct or "xmlhttp" in ct or "fetch" in ct


def detect_response_type(mime: str) -> str:
    if "json" in mime:
        return "json"
    elif "xml" in mime:
        return "xml"
    elif "html" in mime:
        return "html"
    elif "text" in mime:
        return "text"
    elif "image" in mime:
        return "image"
    else:
        return "unknown"


# ─── API client generation ───────────────────────────────────

def generate_api_client(analysis: dict, lang: str = "python", base_url: str = "") -> str:
    """Generate an API client from analyzed HAR data."""

    if lang == "python":
        return _gen_python(analysis, base_url)
    elif lang == "js":
        return _gen_js(analysis, base_url)
    elif lang == "curl":
        return _gen_curl(analysis)
    else:
        raise ValueError(f"Unsupported language: {lang}")


def _gen_python(analysis: dict, base_url: str = "") -> str:
    endpoints = analysis["api_endpoints"]

    # Pick the most relevant search endpoint
    search_eps = [e for e in endpoints if e.get("category") == "search"]
    if not search_eps and endpoints:
        # Fallback: use XHR entries that look like API
        search_eps = [e for e in endpoints if e.get("is_xhr")]
    if not search_eps:
        search_eps = endpoints[:1]

    if not search_eps:
        return "# No API endpoints found in HAR data\n"

    primary = search_eps[0]
    parsed = urlparse(primary["url"])
    base = base_url or f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path

    # Extract query params
    qs = parse_qs(parsed.query)
    query_params = {k: v[0] if v else "" for k, v in qs.items()}

    # Extract request body if POST
    has_body = primary["method"] == "POST" and primary["request_body"]
    post_data_raw = primary["request_body"]

    # Try to parse post body as JSON or form data
    post_json = None
    post_form = {}
    if post_data_raw:
        try:
            post_json = json.loads(post_data_raw)
        except (json.JSONDecodeError, TypeError):
            # Try form-encoded
            post_form = dict(parse_qs(post_data_raw))
            post_form = {k: v[0] if v else "" for k, v in post_form.items()}

    # Extract headers (excluding host, cookie, etc. that should be dynamic)
    headers_to_keep = {}
    skip_headers = {"host", "cookie", "content-length", "connection", "accept-encoding", "referer"}
    for k, v in primary["request_headers"].items():
        if k.lower() not in skip_headers:
            headers_to_keep[k] = v

    # Build class name
    class_name = _make_class_name(path)

    lines = [
        '"""',
        f'Auto-generated API client for {base}',
        f'Extracted from HAR data by har2spy',
        f'Generated at: {datetime.now().isoformat()}',
        '"""',
        '',
        'import requests',
        'import json',
        '',
        '',
        f'class {class_name}:',
        f'    """API client for {base}"""',
        '',
        f'    BASE_URL = {repr(base)}',
        f'    DEFAULT_HEADERS = {json.dumps(headers_to_keep, indent=4)}',
        '',
    ]

    # Build method signature parameters (query params + body fields)
    method_name = _sanitize_method_name(path or "search")
    param_docs = []
    params_for_sig = []
    query_dict_lit = {}
    body_dict_lit = {}
    body_is_json = False

    # Query params -> method params
    for k, v in query_params.items():
        params_for_sig.append(f'{k}: str = {repr(v)}')
        param_docs.append(f'        {k}: Query parameter (captured: "{v}")')
        query_dict_lit[k] = k if k else v

    # Body params -> method params
    if has_body:
        if post_json and isinstance(post_json, dict):
            body_is_json = True
            for key, val in post_json.items():
                if isinstance(val, str):
                    params_for_sig.append(f'{key}: str = {repr(val)}')
                    param_docs.append(f'        {key}: JSON body field (captured: "{val}")')
                    body_dict_lit[key] = key
                elif isinstance(val, bool):
                    pv = repr(val)
                    params_for_sig.append(f'{key}: bool = {pv}')
                    param_docs.append(f'        {key}: JSON body field (captured: {val})')
                    body_dict_lit[key] = key
                elif isinstance(val, (int, float)):
                    pv = repr(val)
                    params_for_sig.append(f'{key} = {pv}')
                    param_docs.append(f'        {key}: JSON body field (captured: {val})')
                    body_dict_lit[key] = key
                else:
                    params_for_sig.append(f'{key}=None')
                    param_docs.append(f'        {key}: JSON body field (type: {type(val).__name__})')
                    body_dict_lit[key] = key
        elif post_form:
            for k, v in post_form.items():
                params_for_sig.append(f'{k}: str = {repr(v)}')
                param_docs.append(f'        {k}: Form field (captured: "{v}")')
                body_dict_lit[k] = k

    # Build the method body
    # Query params dict literal (with actual values, not variable refs if empty)
    if query_dict_lit:
        # Build params dict using the method parameter values
        qp_items = ", ".join(f'{repr(k)}: {k}' for k in query_dict_lit)
        params_build = f'params = {{{qp_items}}}'
    else:
        params_build = 'params = {}'

    # Body construction
    if body_dict_lit:
        body_items = ", ".join(f'{repr(k)}: {k}' for k in body_dict_lit)
        body_build = f'body = {{{body_items}}}'
    else:
        body_build = ''

    # requests call
    method_lower = primary["method"].lower()
    if body_is_json:
        call = (
            f'        resp = requests.{method_lower}(\n'
            f'            url,\n'
            f'            params=params,\n'
            f'            json=body,\n'
            f'            headers=self.DEFAULT_HEADERS,\n'
            f'            timeout=30\n'
            f'        )'
        )
    elif body_dict_lit:
        call = (
            f'        resp = requests.{method_lower}(\n'
            f'            url,\n'
            f'            params=params,\n'
            f'            data=body,\n'
            f'            headers=self.DEFAULT_HEADERS,\n'
            f'            timeout=30\n'
            f'        )'
        )
    else:
        call = (
            f'        resp = requests.{method_lower}(\n'
            f'            url,\n'
            f'            params=params,\n'
            f'            headers=self.DEFAULT_HEADERS,\n'
            f'            timeout=30\n'
            f'        )'
        )

    # Build method docstring params
    doc_lines = [
        f'        """Search/query the {base} API.',
        f'        Returns the parsed JSON response.',
    ]
    if param_docs:
        doc_lines.append('')
        doc_lines.extend(param_docs)
    doc_lines.append('        """')

    # Assemble method
    sig = f'    def {method_name}(self, {", ".join(params_for_sig)}) -> dict:'

    lines.extend([
        '',
        sig,
    ] + doc_lines + [
        f'        url = self.BASE_URL + {repr(path)}',
        '',
    ])

    if body_build:
        lines.append(f'        {body_build}')
        lines.append('')

    lines.append(f'        {params_build}')
    lines.append('')
    lines.append(call)
    lines.append('')
    lines.append('        try:')
    lines.append('            return resp.json()')
    lines.append('        except Exception:')
    lines.append('            return {"text": resp.text, "status": resp.status_code}')

    # get_raw_response method
    lines.extend([
        '',
        '    def get_raw_response(self, endpoint: str = "/") -> requests.Response:',
        '        """Fetch any endpoint and return the raw response."""',
        '        url = self.BASE_URL + endpoint',
        '        return requests.get(url, headers=self.DEFAULT_HEADERS, timeout=30)',
        '',
        '',
    ])

    # __main__ block
    # Build example call
    example_args = []
    for k in query_dict_lit:
        example_args.append(f'{k}={repr(query_dict_lit[k] and k or repr(v))}')
    for k in body_dict_lit:
        if k not in query_dict_lit:
            example_args.append(f'{k}=None')

    # Simpler: just use the defaults
    example_str = ", ".join(
        f'{k}={repr(v)}'
        for k, v in query_params.items()
    )
    if not example_str and body_dict_lit:
        # Just call with no extra args — defaults will apply
        example_str = ""

    lines.extend([
        f'    client = {class_name}()',
        f'    result = client.{method_name}({example_str})',
        '    print(json.dumps(result, indent=2))',
        '',
    ])

    return "\n".join(lines)


def _make_class_name(path: str) -> str:
    """Convert a URL path into a Python class name."""
    name = path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_")
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    if not name:
        name = "api"
    return name.title().replace("_", "") + "Client"


def _gen_js(analysis: dict, base_url: str = "") -> str:
    endpoints = analysis["api_endpoints"]
    primary = endpoints[0] if endpoints else None
    if not primary:
        return "// No API endpoints found\n"

    parsed = urlparse(primary["url"])
    base = base_url or f"{parsed.scheme}://{parsed.netloc}"
    path = parsed.path

    lines = [
        '// Auto-generated API client by har2spy',
        '',
        'const BASE_URL = ' + repr(base) + ';',
        '',
        'async function search(params = {}) {',
        '  const url = BASE_URL + ' + repr(path) + ';',
        '',
        f'  const response = await fetch(url, {{',
        f'    method: {repr(primary["method"])},',
        '    headers: {',
    ]

    # Headers
    skip_headers = {"host", "cookie", "content-length", "connection", "accept-encoding", "referer"}
    for k, v in primary["request_headers"].items():
        if k.lower() not in skip_headers:
            lines.append(f'      {repr(k)}: {repr(v)},')

    if primary["request_body"]:
        lines.append('    body: JSON.stringify({}),')
    lines.append('  });')
    lines.append('  return response.json();')
    lines.append('}')
    lines.append('')
    lines.append('// Usage:')
    lines.append('search({ q: "iPhone", page: 1 }).then(console.log);')
    lines.append('')

    return "\n".join(lines)


def _gen_curl(analysis: dict) -> str:
    lines = ["# Auto-generated curl commands by har2spy", ""]
    for ep in analysis["api_endpoints"][:10]:
        req = ep["_raw"]["request"] if "_raw" in ep else {}
        url = ep["url"]
        method = ep["method"]
        headers_str = " ".join(f'-H "{h["name"]}: {h["value"]}"' for h in req.get("headers", [])
                             if h["name"].lower() not in {"host", "content-length", "connection", "accept-encoding"})
        body = req.get("postData", {}).get("data", "")
        body_str = ""
        if body:
            body_str = f' -d {repr(body)}'
        lines.append(f"# {method} — {url}")
        lines.append(f'curl {headers_str} -X {method} {repr(url)}{body_str}')
        lines.append("")
    return "\n".join(lines)


def _sanitize_method_name(path: str) -> str:
    """Convert a URL path into a Python method name."""
    name = path.strip("/").replace("/", "_").replace("-", "_").replace(".", "_")
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)
    if not name:
        name = "search"
    return name


# ─── Scanning orchestration ──────────────────────────────────

def scan_website(url: str, term: str, search_selector: str = None,
                 submit_selector: str = None, auto: bool = False,
                 output: str = None, wait: int = 3,
                 user_agent: str = "desktop_safari") -> str:
    """
    Navigate to a website, inject the HAR spy, perform a search,
    and capture all network activity as HAR.
    """

    print(f"[har2spy] Starting scan: {url}")
    print(f"[har2spy] Search term: '{term}'")
    print(f"[har2spy] User agent: {user_agent}")

    # Step 1: Set user agent
    browser_exec("set_user_agent", user_agent=user_agent)
    time.sleep(0.5)

    # Step 2: Navigate to the page
    print(f"[har2spy] → Navigating to {url}")
    browser_exec("navigate", url=url)
    time.sleep(2)

    # Step 3: Inject the spy
    js_code = read_js_module()
    if js_code:
        print("[har2spy] → Injecting network spy")
        browser_exec("execute_js", script=js_code)
        time.sleep(0.5)

    # Verify injection
    verify = browser_exec_json("execute_js", script="return typeof window.__har2spy_exportHAR === 'function' ? 'OK' : 'FAIL';")
    spy_text = verify.get("text", "").strip()
    spy_ok = spy_text == "OK"
    print(f"[har2spy]   Spy status: {'OK' if spy_ok else 'MISSING'} ({spy_text})")

    # Step 4: Find search elements
    if auto or not search_selector:
        print("[har2spy] → Auto-detecting search elements")
        search_selector = detect_search_selector()
        if not search_selector:
            # Fallback heuristics
            candidates = browser_exec_json("execute_js", script="""
                const inputs = Array.from(document.querySelectorAll('input[type="text"], input[type="search"], input[name*="q"], input[name*="search"], input[role="search"]'));
                const btns = Array.from(document.querySelectorAll('button[type="submit"], input[type="submit"], button.search, .search-button'));
                return JSON.stringify({
                    search_inputs: inputs.slice(0, 5).map(i => ({selector: getSel(i), placeholder: i.placeholder, name: i.name, id: i.id})),
                    submit_buttons: btns.slice(0, 5).map(b => ({selector: getSel(b), text: b.textContent.trim().substring(0, 30)}))
                });
                function getSel(el) {
                    if (el.id) return '#' + el.id;
                    if (el.name) return 'input[name="' + el.name + '"]';
                    if (el.className) return '.' + el.className.split(' ')[0];
                    return el.tagName + (el.type ? '[type="' + el.type + '"]' : '');
                }
            """)
            cand_data = candidates.get("data", {}).get("text", "")
            print(f"[har2spy]   Search candidates: {cand_data[:300]}")

        if not search_selector:
            search_selector = "input[name='q'], input[type='search'], input[role='search']"

    if not submit_selector:
        submit_selector = "button[type='submit'], input[type='submit'], .search-button, .searchsubmit"
        print(f"[har2spy]   Using submit selector: {submit_selector}")

    # Step 5: Set marker (so we know which entries came from our search)
    print("[har2spy] → Setting capture marker")
    browser_exec_json("execute_js", script="window.__har2spy_marker('search_start');")

    # Step 6: Perform search via JS (more reliable than type/click across different sites)
    # We inject JS that finds the search input, sets its value, and triggers relevant events
    print(f"[har2spy] → Performing search via JS for '{term}'")
    search_selector_js = json.dumps(search_selector or 'input[name="q"], input[type="search"]')
    term_js = json.dumps(term)
    search_js = """
    (function() {
        var search_selector = %s;
        var term = %s;
        var input = document.querySelector(search_selector);
        if (input) {
            input.value = term;
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
            var form = input.closest('form');
            if (form) {
                form.submit();
            } else {
                var params = new URLSearchParams(window.location.search);
                params.set('q', term);
                window.location.search = params.toString();
            }
        }
        return 'search_done';
    })();
    """ % (search_selector_js, term_js)
    search_result = browser_exec_json("execute_js", script=search_js)
    search_output = search_result.get("text", "")
    print(f"[har2spy]   Search result: {search_output}")
    time.sleep(2)  # Wait for network to settle

    # Step 7: Wait for network activity to complete
    print(f"[har2spy] → Waiting {wait}s for network activity...")
    wait_js = """
        const checkCount = window.__har2spy_count ? window.__har2spy_count() : 0;
        return checkCount;
    """
    for _ in range(wait + 1):
        count_result = browser_exec_json("execute_js", script=wait_js)
        count_raw = str(count_result.get("text", "0"))
        try:
            count = int(float(count_raw))
        except:
            count = 0
        if count > 0:
            break
        time.sleep(1)

    # Step 8: Export HAR
    print("[har2spy] → Exporting HAR data")
    export_code = "window.__har2spy_exportHAR({ onlyXHR: false });"
    har_result = browser_exec_json("execute_js", script=export_code)
    har_text = har_result.get("text", "").strip()

    if not har_text or har_text in ("null", "undefined"):
        print("[har2spy] ⚠ No HAR data captured — falling back to Performance API")
        har_raw = capture_via_performance()
    else:
        try:
            har_data = json.loads(har_text)
            print(f"[har2spy] ✓ Captured {len(har_data.get('log', {}).get('entries', []))} HAR entries")
            har_raw = har_text
        except json.JSONDecodeError:
            print(f"[har2spy] ⚠ Raw response was not JSON: {har_text[:200]}")
            har_raw = capture_via_performance()

    # Save HAR
    har_log = json.loads(har_raw)["log"]

    if output:
        output_path = output
    else:
        safe_name = re.sub(r'[^a-zA-Z0-9_-]', '_', url)
        output_path = f"/var/minis/workspace/har2spy/output/{safe_name}_{int(time.time())}.har.json"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(har_log, f, indent=2)
    print(f"[har2spy] ✓ HAR saved to: {output_path}")

    # Step 10: Analyze
    print("[har2spy] → Analyzing captured API endpoints")
    analysis = analyze_har(har_log)
    print(f"[har2spy]   Found {len(analysis['api_endpoints'])} API endpoints")
    print(f"[har2spy]   {len(analysis['search_endpoints'])} with search params")
    print(f"[har2spy]   {len(analysis['auth_endpoints'])} auth endpoints")

    # Show top endpoints
    for ep in analysis["api_endpoints"][:5]:
        flag = "XHR" if ep["is_xhr"] else "---"
        print(f"  [{flag}] {ep['method']} {ep['path']} → {ep['status']} ({ep['time_ms']}ms)")

    # Save analysis
    analysis_path = output_path.replace(".har.json", ".analysis.json")
    with open(analysis_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"[har2spy] ✓ Analysis saved to: {analysis_path}")

    # Generate client
    print("[har2spy] → Generating API client")
    client_code = generate_api_client(analysis, lang="python")
    client_path = output_path.replace(".har.json", ".api_client.py")
    with open(client_path, "w") as f:
        f.write(client_code)
    print(f"[har2spy] ✓ Client saved to: {client_path}")

    return output_path


def capture_via_performance() -> str:
    """Fallback: use Performance API to capture network data."""
    perf_js = """
    const entries = performance.getEntriesByType('resource');
    const harEntries = entries.map(e => ({
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
            content: { size: -1, mimeType: e.responseEnd ? '' : '', text: undefined }
        },
        cache: {},
        timings: {
            send: 0,
            wait: Math.round(e.duration / 2),
            receive: Math.round(e.duration / 2)
        },
        serverIPAddress: '',
        connection: '',
        pageref: 'page_1'
    }));
    return JSON.stringify({
        log: {
            version: '1.2',
            creator: { name: 'har2spy-performance-fallback' },
            pages: [{ id: 'page_1', startedDateTime: new Date(0).toISOString(), pageTimings: { onLoad: 0, onContentEvent: -1 } }],
            entries: harEntries
        }
    });
    """
    har_result = browser_exec_json("execute_js", script=perf_js)
    return har_result.get("text", "")


def detect_search_selector() -> str:
    """Auto-detect the search input on the current page."""
    # This just returns None — the caller will use heuristics
    return None


# ─── CLI ─────────────────────────────────────────────────────

def cmd_scan(args):
    return scan_website(
        url=args.url,
        term=args.term,
        search_selector=args.search_selector,
        submit_selector=args.submit_selector,
        auto=args.auto,
        output=args.output,
        wait=args.wait,
        user_agent=args.user_agent
    )


def cmd_analyze(args):
    log = load_har(args.har_file)
    analysis = analyze_har(log)

    print(json.dumps(analysis, indent=2, default=str))

    # Save analysis
    out_path = args.output or args.har_file.replace(".har.json", ".analysis.json")
    with open(out_path, "w") as f:
        json.dump(analysis, f, indent=2, default=str)
    print(f"\n[har2spy] Analysis saved to: {out_path}", file=sys.stderr)


def cmd_generate(args):
    log = load_har(args.har_file)
    analysis = analyze_har(log)
    code = generate_api_client(analysis, lang=args.lang, base_url=args.base_url)

    out_path = args.output or args.har_file.replace(".har.json", ".api_client." + args.lang)
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        f.write(code)
    print(f"[har2spy] Generated {args.lang} client: {out_path}")
    print(code)


def cmd_serve(args):
    """Start a simple HAR viewer server."""
    import http.server
    import socketserver

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory="/var/minis/workspace/har2spy", **kw)

    PORT = args.port
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"[har2spy] Serving HAR files at http://localhost:{PORT}")
        print(f"[har2spy] Open http://localhost:{PORT} in your browser")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(
        prog="har2spy",
        description="Reverse-engineer website search APIs from HAR data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scan a website's search and capture HAR
  har2spy scan https://google.com --term "iPhone test" --auto

  # Analyze an existing HAR file
  har2spy analyze capture.har.json

  # Generate a Python API client from HAR
  har2spy generate capture.har.json --lang python -o client.py
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command")

    # scan
    p_scan = subparsers.add_parser("scan", help="Scan a website and capture HAR")
    p_scan.add_argument("url", help="Target URL")
    p_scan.add_argument("--term", "-q", required=True, help="Search term/query")
    p_scan.add_argument("--search-selector", "-s", default=None, help="CSS selector for search input")
    p_scan.add_argument("--submit-selector", "-b", default=None, help="CSS selector for submit button")
    p_scan.add_argument("--auto", action="store_true", help="Auto-detect search elements")
    p_scan.add_argument("--output", "-o", default=None, help="Output HAR file path")
    p_scan.add_argument("--wait", "-w", type=int, default=3, help="Seconds to wait for network (default: 3)")
    p_scan.add_argument("--user-agent", default="desktop_safari", choices=["desktop_safari", "mobile_safari"], help="User agent")
    p_scan.set_defaults(func=cmd_scan)

    # analyze
    p_analyze = subparsers.add_parser("analyze", help="Analyze a HAR file")
    p_analyze.add_argument("har_file", help="HAR file")
    p_analyze.add_argument("--output", "-o", default=None, help="Output analysis file")
    p_analyze.set_defaults(func=cmd_analyze)

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate API client from HAR")
    p_gen.add_argument("har_file", help="HAR file")
    p_gen.add_argument("--lang", "-l", choices=["python", "js", "curl"], default="python", help="Output language")
    p_gen.add_argument("--base-url", default="", help="Override base URL")
    p_gen.add_argument("--output", "-o", default=None, help="Output file")
    p_gen.set_defaults(func=cmd_generate)

    # serve
    p_serve = subparsers.add_parser("serve", help="Start HAR viewer server")
    p_serve.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)
    args.func(args)


if __name__ == "__main__":
    main()

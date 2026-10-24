#!/usr/bin/env python3
"""Test har2spy scan with httpbin search-like flow."""

import subprocess, time, json

def run_shell(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip(), r.stderr.strip()

def run_jsexec(script):
    """Execute JS in browser and return just the text return value."""
    # The execute_js tool returns JSON with data.text = the actual return value
    r = subprocess.run(['minis-browser-use', 'execute_js', '--script', script],
                       capture_output=True, text=True, timeout=30)
    try:
        result = json.loads(r.stdout)
        return result.get('data', {}).get('text', r.stdout)
    except:
        return r.stdout

print("=== har2spy E2E test ===")
print("1. Navigating to httpbin.org/html...")
run_shell("minis-browser-use navigate --url https://httpbin.org/html")
time.sleep(2)

print("2. Injecting spy...")
with open('har2spy.js') as f:
    spy_js = f.read()
run_jsexec(spy_js)

time.sleep(0.5)

print("3. Checking spy status...")
status = run_jsexec("return typeof window.__har2spy_exportHAR === 'function' ? 'OK' : 'FAIL'")
print(f"   Status: {status}")

print("4. Setting capture marker...")
run_jsexec("window.__har2spy_marker('search_start')")

print("5. Typing search term...")
run_jsexec(f"document.querySelector('input[type=\"text\"]').value='iPhone 16'; document.querySelector('form').submit();")
time.sleep(2)

print("6. Exporting HAR...")
har_raw = run_jsexec("return window.__har2spy_exportHAR({onlyXHR: false});")
try:
    har = json.loads(har_raw)
    entries = har.get('log', {}).get('entries', [])
    print(f"   ✓ {len(entries)} entries captured")
    for e in entries[:10]:
        req = e.get('request', {})
        url = req.get('url', '')
        method = req.get('method', '')
        # Only show non-asset entries
        if not any(url.endswith(ext) for ext in ['.ico', '.css', '.js', '.png', '.jpg']):
            print(f"   [{method}] {url}")
except json.JSONDecodeError as ex:
    print(f"   ✗ JSON parse error: {ex}")
    print(f"   raw: {har_raw[:200]}")

print("7. Analyzing...")
# Now analyze
analyze = run_shell(f"cd /var/minis/workspace/har2spy && python3 har2spy.py analyze -o /tmp/test_analysis.json /dev/stdin <<< '{har_raw}' 2>&1")
print(f"   {analyze}")
#!/usr/bin/env python3
"""Quick end-to-end test of har2spy browser injection."""

import subprocess, time, json, sys

def run(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
    return r.stdout.strip(), r.stderr.strip()

def run_js(script):
    """Run JS in the browser, handling the script content safely via a temp file approach."""
    # Write script to temp file
    with open('/tmp/_js_cmd.js', 'w') as f:
        f.write(script)
    # Use node to read and pass it
    r = subprocess.run(['minis-browser-use', 'execute_js', '--script', script],
                       capture_output=True, text=True, timeout=30)
    return r.stdout.strip(), r.stderr.strip()

# 1. Navigate
print("1. Navigating to https://httpbin.org/html")
out, err = run("minis-browser-use navigate --url https://httpbin.org/html")
print(f"   stdout: {out[:200]}")
time.sleep(2)

# 2. Read spy JS
print("2. Injecting har2spy.js")
with open('har2spy.js') as f:
    spy_js = f.read()

out, err = run_js(spy_js + "\nreturn window.__har2spy_installed === true;")
print(f"   stdout: {out[:200]}")
if err:
    print(f"   stderr: {err[:200]}")
time.sleep(0.5)

# 3. Check spy
print("3. Checking spy status")
out, err = run_js("return typeof window.__har2spy_exportHAR === 'function' ? 'OK' : 'MISSING';")
print(f"   result: {out}")

# 4. Set marker
print("4. Setting marker")
out, err = run_js("return window.__har2spy_marker ? window.__har2spy_marker('search_start') : -1;")
print(f"   result: {out}")

# 5. Trigger a fetch
print("5. Triggering fetch to https://httpbin.org/get?q=hello")
run_js("""
fetch('https://httpbin.org/get?q=hello')
  .then(r => r.json())
  .then(d => console.log('fetch done'))
  .catch(e => console.log('fetch error: ' + e.message));
""")
time.sleep(2)

# 6. Export HAR
print("6. Exporting HAR")
out, err = run_js("return window.__har2spy_exportHAR({onlyXHR: false});")
print(f"   stdout len: {len(out)}")
if out:
    try:
        har = json.loads(out)
        entries = har.get('log', {}).get('entries', [])
        print(f"   entries: {len(entries)}")
        for e in entries[:5]:
            req = e.get('request', {})
            print(f"     {req.get('method','?')} {req.get('url','?')[:80]}")
    except json.JSONDecodeError as ex:
        print(f"   parse error: {ex}")
        print(f"   raw: {out[:300]}")
else:
    print(f"   no output, stderr: {err[:300]}")

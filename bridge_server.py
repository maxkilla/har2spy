#!/usr/bin/env python3
"""Persistent Playwright bridge server for har2spy.

Run once (background); stays up so navigate→inject→execute_js share state.
Talk to it via bridge_client.py on port $HAR2SPY_PORT (default 4499).
"""
import urllib.parse, os, json, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from playwright.sync_api import sync_playwright

PORT = int(os.environ.get("HAR2SPY_PORT", "4499"))
p = sync_playwright().start()
browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
context = browser.new_context()
page = context.new_page()
_lock = threading.Lock()

def _run(action, params):
    if action == "navigate":
        page.goto(params["url"], wait_until="networkidle")
        wt = float(params.get("wait", 0))
        if wt:
            page.wait_for_timeout(int(wt * 1000))
        return {"status":"navigated"}
    if action == "inject_spy":
        with open(params["script"]) as f:
            script = f.read()
        page.add_init_script(script)
        page.evaluate(script)
        return {"status":"injected"}
    if action == "execute_js":
        try:
            result = page.evaluate(f"new Function({json.dumps(params['script'])})()")
            return {"data":{"text":str(result)}}
        except Exception as e:
            return {"error":str(e)}
    return {"error":f"unknown action {action}"}

class H(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass
    def do_GET(self):
        with _lock:
            try:
                action = self.path.split("?")[0].lstrip("/")
                qs = self.path.split("?")[1] if "?" in self.path else ""
                params = {urllib.parse.unquote(k): urllib.parse.unquote(v) for k,v in (p.split("=") for p in qs.split("&") if "=" in p)}
                payload = json.dumps(_run(action, params))
            except Exception as e:
                payload = json.dumps({"error": str(e)})
            b = payload.encode()
            self.send_response(200); self.send_header("content-type","application/json")
            self.send_header("content-length",str(len(b))); self.end_headers()
            self.wfile.write(b)

print(f"[har2spy bridge] listening :{PORT}", flush=True)
HTTPServer(("0.0.0.0", PORT), H).serve_forever()

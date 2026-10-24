#!/usr/bin/env python3
import urllib.parse, sys, urllib.request

cmd = sys.argv[1]
params = {}
for i in range(2, len(sys.argv)):
    k = sys.argv[i].lstrip("-")
    v = sys.argv[i + 1] if i + 1 < len(sys.argv) else ""
    params[k.replace("-", "_")] = v

qs = "&".join(f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}" for k, v in params.items())
url = f"http://localhost:{__import__('os').environ.get('HAR2SPY_PORT','4499')}/{cmd}?{qs}"
print(urllib.request.urlopen(url, timeout=30).read().decode())

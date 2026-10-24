#!/usr/bin/env python3
"""
Database & Schema Discovery from HAR Data

Analyzes captured HAR data to discover:
- GraphQL schemas and introspection responses
- JSON response structures (inferred database tables)
- API endpoint patterns (REST resource naming)
- Connection strings, database URLs
- Filter/sort parameters (indexed columns)
- Error messages (SQL leaks)
- Authentication tokens
"""

import json, re
from urllib.parse import urlparse, parse_qs
from collections import defaultdict


class DatabaseSchemaScanner:
    def __init__(self, har_data):
        self.har = har_data
        self.entries = har_data.get("log", {}).get("entries", [])
        self.discoveries = {
            "graphql": [],
            "json_schemas": [],
            "endpoints": defaultdict(list),
            "connection_strings": [],
            "error_leaks": [],
            "pagination_fields": [],
            "filter_fields": [],
            "auth_tokens": [],
            "db_hosts": [],
        }

    def scan(self):
        """Run all discovery scans."""
        self._scan_graphql()
        self._scan_json_schemas()
        self._scan_endpoints()
        self._scan_connection_strings()
        self._scan_error_leaks()
        self._scan_pagination_and_filters()
        self._scan_auth_tokens()
        self._scan_db_hosts()
        return self.discoveries

    # ── GraphQL Discovery ──
    def _scan_graphql(self):
        """Find GraphQL queries, mutations, and introspection responses."""
        graphql_patterns = [
            r'(?:query|mutation|subscription)\s+\w+',
            r'__schema',
            r'__type',
            r'__typename',
        ]
        for entry in self.entries:
            req = entry.get("request", {})
            body = req.get("postData", {}).get("text", "")
            url = req.get("url", "")

            # GraphQL endpoints
            if "graphql" in url.lower():
                self.discoveries["graphql"].append({
                    "url": url,
                    "method": req.get("method", "GET"),
                    "body": body[:500],
                })
                continue

            # GraphQL in POST body
            if body:
                for pattern in graphql_patterns:
                    if re.search(pattern, body, re.IGNORECASE):
                        self.discoveries["graphql"].append({
                            "url": url,
                            "method": req.get("method", "GET"),
                            "pattern_matched": pattern,
                            "body_preview": body[:200],
                        })
                        break

            # GraphQL introspection in response
            resp = entry.get("response", {})
            resp_text = resp.get("content", {}).get("text", "")
            if "__schema" in resp_text or "__type" in resp_text:
                self.discoveries["graphql"].append({
                    "url": url,
                    "introspection": True,
                    "response_preview": resp_text[:500],
                })

    # ── JSON Schema Discovery ──
    def _scan_json_schemas(self):
        """Analyze JSON responses to infer database table structure."""
        seen_structures = {}
        for entry in self.entries:
            resp = entry.get("response", {})
            content = resp.get("content", {})
            mime = content.get("mimeType", "")
            text = content.get("text", "")
            if not text or "json" not in mime.lower():
                continue

            try:
                data = json.loads(text)
            except:
                continue

            structure = self._infer_structure(data)
            if structure:
                key = structure.get("inferred_table") or structure.get("path")
                if key not in seen_structures:
                    seen_structures[key] = structure
                    self.discoveries["json_schemas"].append(structure)

    def _infer_structure(self, data, path=""):
        """Recursively infer JSON structure like a DB schema."""
        result = {
            "path": path or "root",
            "type": type(data).__name__,
            "fields": [],
            "nested_objects": {},
            "arrays": {},
            "sample_values": {},
        }

        if isinstance(data, dict):
            for key, value in data.items():
                field_info = {
                    "name": key,
                    "type": type(value).__name__,
                    "sample": str(value)[:100],
                }
                result["fields"].append(field_info)
                result["sample_values"][key] = str(value)[:100]

                if isinstance(value, dict):
                    result["nested_objects"][key] = self._infer_structure(value, f"{path}.{key}")
                elif isinstance(value, list) and value:
                    result["arrays"][key] = {
                        "item_type": type(value[0]).__name__,
                        "item_count": len(value),
                    }

            # Try to infer table name from path or structure
            result["inferred_table"] = self._guess_table_name(path, data)

        elif isinstance(data, list) and data:
            result["item_count"] = len(data)
            if data:
                first = data[0]
                result["sample_object"] = self._infer_structure(first, f"{path}[0]")

        return result if result["fields"] or result["nested_objects"] else None

    def _guess_table_name(self, path, data):
        """Guess database table name from JSON structure."""
        # Check path
        path_parts = path.split("/")
        candidates = [p for p in path_parts if p and p.isalpha()]
        if candidates:
            return candidates[-1]

        # Check keys that look like table names
        if isinstance(data, dict):
            for key in data.keys():
                if key.lower() in {"users", "products", "orders", "items", "posts", "categories"}:
                    return key

        return None

    # ── Endpoint Pattern Discovery ──
    def _scan_endpoints(self):
        """Categorize endpoints by resource naming patterns."""
        resource_patterns = {
            "users": r"/(?:api/)?users(?:/|\?|$)",
            "products": r"/(?:api/)?products(?:/|\?|$)",
            "orders": r"/(?:api/)?orders(?:/|\?|$)",
            "categories": r"/(?:api/)?categories(?:/|\?|$)",
            "posts": r"/(?:api/)?posts(?:/|\?|$)",
            "customers": r"/(?:api/)?customers(?:/|\?|$)",
            "inventory": r"/(?:api/)?inventory(?:/|\?|$)",
            "reviews": r"/(?:api/)?reviews(?:/|\?|$)",
            "categories": r"/(?:api/)?categories(?:/|\?|$)",
        }

        for entry in self.entries:
            req = entry.get("request", {})
            url = req.get("url", "")
            parsed = urlparse(url)
            path = parsed.path

            for resource, pattern in resource_patterns.items():
                if re.search(pattern, path, re.IGNORECASE):
                    self.discoveries["endpoints"][resource].append({
                        "url": url,
                        "method": req.get("method", "GET"),
                        "path": path,
                        "query_params": dict(parse_qs(parsed.query)),
                    })
                    break

    # ── Connection String Discovery ──
    def _scan_connection_strings(self):
        """Look for database connection strings in headers, URLs, or bodies."""
        conn_patterns = [
            r'(?:postgres|postgresql|mysql|mongodb|redis|oracle|sqlserver|mssql)://[^\s"\'<>]+',
            r'(?:DATABASE_URL|DB_URL|CONNECTION_STRING)\s*[:=]\s*["\']?([^\s"\'<>]+)',
            r'(?:host|server)\s*[:=]\s*["\']?([^\s"\'<>]+)',
        ]

        for entry in self.entries:
            req = entry.get("request", {})
            text_to_check = (
                req.get("url", "")
                + json.dumps(req.get("headers", []))
                + req.get("postData", {}).get("text", "")
            )
            resp = entry.get("response", {})
            text_to_check += resp.get("content", {}).get("text", "")

            for pattern in conn_patterns:
                matches = re.findall(pattern, text_to_check, re.IGNORECASE)
                for match in matches:
                    self.discoveries["connection_strings"].append({
                        "url": req.get("url", ""),
                        "pattern": pattern[:50],
                        "match": match[:200],
                    })

    # ── Error Message / SQL Leak Discovery ──
    def _scan_error_leaks(self):
        """Scan for database error messages that leak schema info."""
        sql_error_patterns = [
            r'(?:SQL|mysql|postgres|sqlite|oracle|mssql|sql server)\s+(?:error|syntax|exception)',
            r'(?:ORA-|SQLSTATE|PG::|mysql_fetch|sqlite3_)',
            r'(?:You have an error in your SQL syntax|Unclosed quotation mark|Incorrect syntax near)',
        ]

        for entry in self.entries:
            resp = entry.get("response", {})
            text = resp.get("content", {}).get("text", "")
            for pattern in sql_error_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    self.discoveries["error_leaks"].append({
                        "url": entry.get("request", {}).get("url", ""),
                        "status": resp.get("status", 0),
                        "error_preview": text[:500],
                    })
                    break

    # ── Pagination & Filter Discovery ──
    def _scan_pagination_and_filters(self):
        """Find pagination and filter parameters that hint at indexed columns."""
        for entry in self.entries:
            req = entry.get("request", {})
            parsed = urlparse(req.get("url", ""))
            query_params = parse_qs(parsed.query)

            # Pagination
            pagination_keys = {"page", "limit", "offset", "per_page", "page_size", "skip", "take", "cursor", "after", "before"}
            found_pagination = {k: v for k, v in query_params.items() if k.lower() in pagination_keys}
            if found_pagination:
                self.discoveries["pagination_fields"].append({
                    "url": req.get("url", ""),
                    "params": found_pagination,
                })

            # Filter/sort (potential indexed columns)
            filter_keys = {"sort", "order", "filter", "where", "search", "q", "query", "category", "type", "status"}
            found_filters = {k: v for k, v in query_params.items() if k.lower() in filter_keys}
            if found_filters:
                self.discoveries["filter_fields"].append({
                    "url": req.get("url", ""),
                    "params": found_filters,
                })

    # ── Auth Token Discovery ──
    def _scan_auth_tokens(self):
        """Extract authentication tokens and API keys."""
        for entry in self.entries:
            req = entry.get("request", {})
            for h in req.get("headers", []):
                name = h["name"].lower()
                value = h["value"]

                if name == "authorization":
                    self.discoveries["auth_tokens"].append({
                        "url": req.get("url", ""),
                        "header": "Authorization",
                        "type": "bearer" if value.startswith("Bearer ") else "basic",
                        "value_preview": value[:50],
                    })
                elif name in {"x-api-key", "api-key", "apikey"}:
                    self.discoveries["auth_tokens"].append({
                        "url": req.get("url", ""),
                        "header": h["name"],
                        "type": "api_key",
                        "value_preview": value[:50],
                    })
                elif name == "cookie":
                    # Look for session tokens
                    if any(k in value.lower() for k in {"session", "token", "auth", "jwt"}):
                        self.discoveries["auth_tokens"].append({
                            "url": req.get("url", ""),
                            "header": "Cookie",
                            "type": "session_cookie",
                            "value_preview": value[:100],
                        })

    # ── Database Host Discovery ──
    def _scan_db_hosts(self):
        """Find potential database hostnames in URLs and headers."""
        db_host_patterns = [
            r'db\.[a-zA-Z0-9.-]+\.com',
            r'database\.[a-zA-Z0-9.-]+\.com',
            r'(?:postgres|mysql|mongodb|redis)\.[a-zA-Z0-9.-]+\.com',
            r'(?:rds|elasticache|documentdb)\.amazonaws\.com',
        ]

        for entry in self.entries:
            url = entry.get("request", {}).get("url", "")
            for pattern in db_host_patterns:
                matches = re.findall(pattern, url, re.IGNORECASE)
                for match in matches:
                    self.discoveries["db_hosts"].append({
                        "url": url,
                        "host": match,
                    })


def analyze_har_for_databases(har_path):
    """Main entry point: load HAR and return database discoveries."""
    with open(har_path) as f:
        har_data = json.load(f)
    scanner = DatabaseSchemaScanner(har_data)
    return scanner.scan()


def print_discoveries(discoveries):
    """Pretty-print database discoveries."""
    print("=" * 60)
    print("🗄️  DATABASE & SCHEMA DISCOVERY RESULTS")
    print("=" * 60)

    # GraphQL
    gql = discoveries.get("graphql", [])
    if gql:
        print(f"\n🔗 GraphQL Endpoints ({len(gql)}):")
        for g in gql[:5]:
            print(f"   {g.get('method', 'GET')} {g.get('url', '')[:100]}")
            if g.get("introspection"):
                print("      ⚠️  GRAPHQL INTROSPECTION DETECTED - Full schema exposed!")

    # JSON schemas
    schemas = discoveries.get("json_schemas", [])
    if schemas:
        print(f"\n📋 JSON Response Schemas ({len(schemas)}):")
        for s in schemas[:10]:
            print(f"   Path: {s['path']}")
            print(f"      Type: {s['type']}, Table: {s.get('inferred_table', 'unknown')}")
            fields = [f["name"] for f in s.get("fields", [])[:5]]
            print(f"      Fields: {', '.join(fields)}")

    # Endpoints
    endpoints = discoveries.get("endpoints", {})
    if endpoints:
        print(f"\n🎯 API Resource Endpoints:")
        for resource, eps in endpoints.items():
            print(f"   {resource}: {len(eps)} endpoints")
            for ep in eps[:3]:
                print(f"      {ep['method']} {ep['path']}")

    # Connection strings
    conns = discoveries.get("connection_strings", [])
    if conns:
        print(f"\n🔗 Connection Strings ({len(conns)}):")
        for c in conns[:5]:
            print(f"   {c['match'][:100]}")

    # Error leaks
    errors = discoveries.get("error_leaks", [])
    if errors:
        print(f"\n⚠️  SQL/DB Error Leaks ({len(errors)}):")
        for e in errors[:5]:
            print(f"   {e['url'][:80]} → {e['error_preview'][:100]}")

    # Pagination
    pag = discoveries.get("pagination_fields", [])
    if pag:
        print(f"\n📄 Pagination Patterns ({len(pag)}):")
        for p in pag[:5]:
            print(f"   {p['url'][:80]} → {list(p['params'].keys())}")

    # Auth tokens
    auth = discoveries.get("auth_tokens", [])
    if auth:
        print(f"\n🔐 Auth Tokens ({len(auth)}):")
        for a in auth[:5]:
            print(f"   {a['header']}: {a['type']} ({a['value_preview']})")

    # DB hosts
    hosts = discoveries.get("db_hosts", [])
    if hosts:
        print(f"\n🌐 Database Hosts ({len(hosts)}):")
        for h in hosts[:5]:
            print(f"   {h['host']}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python schema_scanner.py <har_file.json>")
        sys.exit(1)
    discoveries = analyze_har_for_databases(sys.argv[1])
    print_discoveries(discoveries)

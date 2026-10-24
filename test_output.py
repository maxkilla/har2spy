"""
Auto-generated API client for https://httpbin.org
Extracted from HAR data by har2spy
Generated at: 2026-10-23T22:02:37.847211
"""

import requests
import json


class Get:
    """API client for https://httpbin.org"""

    BASE_URL = 'https://httpbin.org'
    DEFAULT_HEADERS = {
    "accept": "application/json",
    "user-agent": "Mozilla/5.0"
}


    def get(self, q: str = 'iPhone 16 Pro', sort: str = 'price', order: str = 'desc') -> dict:
        """Search/query the https://httpbin.org API.
        Returns the parsed JSON response.

        q: Query parameter (captured: "iPhone 16 Pro")
        sort: Query parameter (captured: "price")
        order: Query parameter (captured: "desc")
        """
        url = self.BASE_URL + '/get'

        params = {'q': q, 'sort': sort, 'order': order}

        resp = requests.get(
            url,
            params=params,
            headers=self.DEFAULT_HEADERS,
            timeout=30
        )

        try:
            return resp.json()
        except Exception:
            return {"text": resp.text, "status": resp.status_code}

    def get_raw_response(self, endpoint: str = "/") -> requests.Response:
        """Fetch any endpoint and return the raw response."""
        url = self.BASE_URL + endpoint
        return requests.get(url, headers=self.DEFAULT_HEADERS, timeout=30)


    client = Get()
    result = client.get(q='iPhone 16 Pro', sort='price', order='desc')
    print(json.dumps(result, indent=2))

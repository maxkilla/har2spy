"""
Auto-generated API client for https://improving.duckduckgo.com
Extracted from HAR data by har2spy
Generated at: 2026-10-24T03:40:33.373896
"""

import requests
import json


class TLMWtClient:
    """API client for https://improving.duckduckgo.com"""

    BASE_URL = 'https://improving.duckduckgo.com'
    DEFAULT_HEADERS = {}


    def t_l_m_wt(self, iao: str = '1', nr: str = '1', dt: str = '1', rl: str = 'us-en', dl: str = 'en', ck: str = '0', atbi: str = 'false', i: str = 'false', q: str = 'coffee maker', ct: str = 'US', kl: str = 'wt-wt', kp: str = '-1', serp_return: str = '0', djsd: str = '0', blay: str = 'pa18a3w3pa18w7v1n1a1r1,', dsig: str = 'about:m,wikinlp:l', isig: str = 'deep_answer:m', aiheaderexp: str = 'b', ama5exp: str = 'b', biaexp: str = 'b', desktopadclickablecontentexp: str = 'b', disableredditmetadataexp: str = 'b', discussionsciexp: str = 'b', duckaiinautocomplete: str = 'b', duckchat_alpha: str = 'b', externalmapsexp: str = 'b', litexp: str = 'c', locstr_exp: str = 'b', msvrtexp: str = 'b', searchbarexp: str = 'b', serpperfexp: str = 'e', toolexp: str = 'b', useclsexp: str = 'b', videxp: str = 'a', weatherexp: str = 'b', you_news_expansion_exp: str = 'b', you_news_verticalexp: str = 'b') -> dict:
        """Search/query the https://improving.duckduckgo.com API.
        Returns the parsed JSON response.

        iao: Query parameter (captured: "1")
        nr: Query parameter (captured: "1")
        dt: Query parameter (captured: "1")
        rl: Query parameter (captured: "us-en")
        dl: Query parameter (captured: "en")
        ck: Query parameter (captured: "0")
        atbi: Query parameter (captured: "false")
        i: Query parameter (captured: "false")
        q: Query parameter (captured: "coffee maker")
        ct: Query parameter (captured: "US")
        kl: Query parameter (captured: "wt-wt")
        kp: Query parameter (captured: "-1")
        serp_return: Query parameter (captured: "0")
        djsd: Query parameter (captured: "0")
        blay: Query parameter (captured: "pa18a3w3pa18w7v1n1a1r1,")
        dsig: Query parameter (captured: "about:m,wikinlp:l")
        isig: Query parameter (captured: "deep_answer:m")
        aiheaderexp: Query parameter (captured: "b")
        ama5exp: Query parameter (captured: "b")
        biaexp: Query parameter (captured: "b")
        desktopadclickablecontentexp: Query parameter (captured: "b")
        disableredditmetadataexp: Query parameter (captured: "b")
        discussionsciexp: Query parameter (captured: "b")
        duckaiinautocomplete: Query parameter (captured: "b")
        duckchat_alpha: Query parameter (captured: "b")
        externalmapsexp: Query parameter (captured: "b")
        litexp: Query parameter (captured: "c")
        locstr_exp: Query parameter (captured: "b")
        msvrtexp: Query parameter (captured: "b")
        searchbarexp: Query parameter (captured: "b")
        serpperfexp: Query parameter (captured: "e")
        toolexp: Query parameter (captured: "b")
        useclsexp: Query parameter (captured: "b")
        videxp: Query parameter (captured: "a")
        weatherexp: Query parameter (captured: "b")
        you_news_expansion_exp: Query parameter (captured: "b")
        you_news_verticalexp: Query parameter (captured: "b")
        """
        url = self.BASE_URL + '/t/l_m_wt'

        params = {'iao': iao, 'nr': nr, 'dt': dt, 'rl': rl, 'dl': dl, 'ck': ck, 'atbi': atbi, 'i': i, 'q': q, 'ct': ct, 'kl': kl, 'kp': kp, 'serp_return': serp_return, 'djsd': djsd, 'blay': blay, 'dsig': dsig, 'isig': isig, 'aiheaderexp': aiheaderexp, 'ama5exp': ama5exp, 'biaexp': biaexp, 'desktopadclickablecontentexp': desktopadclickablecontentexp, 'disableredditmetadataexp': disableredditmetadataexp, 'discussionsciexp': discussionsciexp, 'duckaiinautocomplete': duckaiinautocomplete, 'duckchat_alpha': duckchat_alpha, 'externalmapsexp': externalmapsexp, 'litexp': litexp, 'locstr_exp': locstr_exp, 'msvrtexp': msvrtexp, 'searchbarexp': searchbarexp, 'serpperfexp': serpperfexp, 'toolexp': toolexp, 'useclsexp': useclsexp, 'videxp': videxp, 'weatherexp': weatherexp, 'you_news_expansion_exp': you_news_expansion_exp, 'you_news_verticalexp': you_news_verticalexp}

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


    client = TLMWtClient()
    result = client.t_l_m_wt(iao='1', nr='1', dt='1', rl='us-en', dl='en', ck='0', atbi='false', i='false', q='coffee maker', ct='US', kl='wt-wt', kp='-1', serp_return='0', djsd='0', blay='pa18a3w3pa18w7v1n1a1r1,', dsig='about:m,wikinlp:l', isig='deep_answer:m', aiheaderexp='b', ama5exp='b', biaexp='b', desktopadclickablecontentexp='b', disableredditmetadataexp='b', discussionsciexp='b', duckaiinautocomplete='b', duckchat_alpha='b', externalmapsexp='b', litexp='c', locstr_exp='b', msvrtexp='b', searchbarexp='b', serpperfexp='e', toolexp='b', useclsexp='b', videxp='a', weatherexp='b', you_news_expansion_exp='b', you_news_verticalexp='b')
    print(json.dumps(result, indent=2))

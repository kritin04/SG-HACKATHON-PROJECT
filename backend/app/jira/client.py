"""Minimal Jira REST API v3 client (works with Jira Cloud and with the local demo tracker in jira_sim/).

Auth: Jira Cloud uses Basic auth with your Atlassian e-mail + an API token
      (create one at https://id.atlassian.com/manage-profile/security/api-tokens).
"""
from __future__ import annotations

import httpx


class JiraError(RuntimeError):
    pass


class JiraClient:
    def __init__(self, base_url: str, email: str = "", token: str = "", timeout: float = 20):
        self.base = base_url.rstrip("/")
        auth = (email, token) if email and token else None
        self.http = httpx.Client(base_url=self.base, auth=auth, timeout=timeout,
                                 headers={"Accept": "application/json", "Content-Type": "application/json"})

    def _req(self, method: str, path: str, **kw):
        try:
            r = self.http.request(method, path, **kw)
        except httpx.HTTPError as exc:
            raise JiraError(f"Cannot reach Jira at {self.base}: {exc}") from exc
        if r.status_code == 401:
            raise JiraError("Jira rejected the credentials (check e-mail and API token)")
        if r.status_code >= 400:
            raise JiraError(f"Jira {method} {path} failed: {r.status_code} {r.text[:200]}")
        return r.json() if r.content else {}

    def myself(self) -> dict:
        return self._req("GET", "/rest/api/3/myself")

    def search(self, jql: str, fields: list[str] | None = None, limit: int = 200) -> list[dict]:
        """Enhanced JQL search (POST /rest/api/3/search/jql, with paging); falls back to the classic /search."""
        fields = fields or ["*all"]
        issues, token = [], None
        try:
            while len(issues) < limit:
                body = {"jql": jql, "fields": fields, "maxResults": min(50, limit - len(issues))}
                if token:
                    body["nextPageToken"] = token
                data = self._req("POST", "/rest/api/3/search/jql", json=body)
                issues += data.get("issues", [])
                token = data.get("nextPageToken")
                if not token or data.get("isLast", True):
                    break
            return issues
        except JiraError as exc:
            if "404" not in str(exc) and "405" not in str(exc):
                raise
        data = self._req("GET", "/rest/api/3/search", params={"jql": jql, "maxResults": limit, "fields": ",".join(fields)})
        return data.get("issues", [])

    def issue(self, key: str) -> dict:
        return self._req("GET", f"/rest/api/3/issue/{key}")

    def create_issue(self, fields: dict) -> dict:
        return self._req("POST", "/rest/api/3/issue", json={"fields": fields})

    def add_comment(self, key: str, adf_body: dict) -> dict:
        return self._req("POST", f"/rest/api/3/issue/{key}/comment", json={"body": adf_body})

    def fields(self) -> list[dict]:
        return self._req("GET", "/rest/api/3/field")

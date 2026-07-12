from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import urlparse

import httpx
from langfuse import get_client, observe

APPROVED_DOMAINS = ("clearskin.in", "hairmdindia.com")


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    content: str


def _approved_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower().rstrip(".")
    return any(hostname == domain or hostname.endswith(f".{domain}") for domain in APPROVED_DOMAINS)


class LinkupSearchClient:
    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 20,
    ) -> None:
        if not api_key:
            raise ValueError("Linkup API key is required")
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @observe(
        name="tool.linkup.search",
        as_type="tool",
        capture_input=False,
        capture_output=False,
    )
    def search(self, query: str) -> tuple[SearchResult, ...]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("search query is required")
        langfuse = get_client()
        langfuse.update_current_span(
            input={"query_digest": sha256(normalized.encode()).hexdigest()},
            metadata={
                "role": "Knowledge",
                "task_type": "own_domain_search",
                "allowed_domains": list(APPROVED_DOMAINS),
            },
        )
        response = self._client.post(
            "https://api.linkup.so/v1/search",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "q": normalized,
                "depth": "standard",
                "outputType": "searchResults",
                "includeDomains": list(APPROVED_DOMAINS),
                "includeImages": False,
            },
        )
        response.raise_for_status()
        results = tuple(
            SearchResult(
                title=str(item.get("name", "")),
                url=str(item.get("url", "")),
                content=str(item.get("content", "")),
            )
            for item in response.json().get("results", [])
            if _approved_url(str(item.get("url", ""))) and item.get("content")
        )
        langfuse.update_current_span(output={"result_count": len(results)})
        return results

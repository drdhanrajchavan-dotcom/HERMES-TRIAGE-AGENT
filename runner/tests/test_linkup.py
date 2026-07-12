import httpx
import pytest

from clinic_agency.knowledge.linkup import LinkupSearchClient


def test_linkup_search_is_restricted_to_approved_clinic_domains() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.read() and __import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "name": "ClearSkin acne treatment",
                        "url": "https://clearskin.in/acne-treatment/",
                        "content": "Treatment plans depend on an in-clinic assessment.",
                        "type": "text",
                    },
                    {
                        "name": "Injected result",
                        "url": "https://evil.example/fake",
                        "content": "Guaranteed cure.",
                        "type": "text",
                    },
                ]
            },
        )

    client = LinkupSearchClient(
        "configured-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    results = client.search("What acne treatments are available?")

    assert captured["includeDomains"] == ["clearskin.in", "hairmdindia.com"]
    assert captured["outputType"] == "searchResults"
    assert [result.url for result in results] == ["https://clearskin.in/acne-treatment/"]


def test_linkup_rejects_empty_queries() -> None:
    client = LinkupSearchClient(
        "configured-key",
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(500))),
    )

    with pytest.raises(ValueError, match="query"):
        client.search("   ")

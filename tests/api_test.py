import asyncio

import respx
from httpx import Response

from api.async_client import AsyncLibraryAPIClient
from api.sync_client import SyncLibraryAPIClient


@respx.mock
def test_get_work_success():
    client = SyncLibraryAPIClient(base_url="https://openlibrary.org")
    work_id = "OL45804W"

    respx.get(f"https://openlibrary.org/works/{work_id}.json").mock(
        return_value=Response(
            200, json={"title": "Fantastic Book", "key": "/works/OL45804W"}
        )
    )

    data = client.get_work(work_id)
    assert data["title"] == "Fantastic Book"


@respx.mock
def test_get_work_404_handling():
    client = SyncLibraryAPIClient(base_url="https://openlibrary.org")
    respx.get("https://openlibrary.org/works/OL00000W.json").mock(
        return_value=Response(404)
    )

    data = client.get_work("OL00000W")
    assert data == {}


@respx.mock
def test_async_fetch_subject_works():
    async_client = AsyncLibraryAPIClient(base_url="https://openlibrary.org")
    respx.get("https://openlibrary.org/subjects/python.json?limit=5&offset=0").mock(
        return_value=Response(200, json={"works": [{"title": "Python 101"}]})
    )

    result = asyncio.run(async_client.fetch_subject_works_async("python", limit=5))
    assert len(result["works"]) == 1
    assert result["works"][0]["title"] == "Python 101"

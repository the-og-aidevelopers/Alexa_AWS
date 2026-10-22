import asyncio

import httpx
import pytest


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv("DOSE_DB", str(tmp_path / "spa.sqlite"))
    monkeypatch.setenv("DOSE_AUTH_PROVIDER", "demo")
    from dose_check import server as module

    return module


def get(module, path):
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app), base_url="http://test", trust_env=False) as client:
            return await client.get(path)

    return asyncio.run(run())


def test_every_page_serves_the_built_app(server, monkeypatch, tmp_path):
    (tmp_path / "index.html").write_text("<title>Pillow</title><div id=root></div>")
    monkeypatch.setattr(server, "WEB", tmp_path)
    for path in ("/", "/agent", "/login"):
        page = get(server, path)
        assert page.status_code == 200 and "Pillow" in page.text


def test_a_missing_build_says_how_to_build(server, monkeypatch, tmp_path):
    monkeypatch.setattr(server, "WEB", tmp_path / "nothing-here")
    page = get(server, "/")
    assert page.status_code == 503
    assert "npm run build" in page.text

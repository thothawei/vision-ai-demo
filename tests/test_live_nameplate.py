"""M7 銘牌真的打本機 Ollama：pytest -m live"""

import pytest

pytestmark = pytest.mark.live


@pytest.fixture
def ollama_env(monkeypatch):
    monkeypatch.setenv("LLM_ENGINE", "ollama")


def test_live_nameplate(client, ollama_env, nameplate_png):
    res = client.post("/api/nameplate/read", files={"file": ("np.png", nameplate_png, "image/png")})

    assert res.status_code == 200, res.text
    body = res.json()
    item = body["items"][0]
    print("\n[M7 live 銘牌]", body["engine"], body["elapsed_ms"], "ms", item)
    assert body["verdict"] == "OK"
    assert "CK-850V" in item["型號"]
    assert "20260088" in item["序號"]

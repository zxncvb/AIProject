import sys
from pathlib import Path


SDK_ROOT = Path(__file__).parents[2] / "sdk" / "python"
if str(SDK_ROOT) not in sys.path:
    sys.path.insert(0, str(SDK_ROOT))

from enterprise_ai_platform import EnterpriseAIPlatformClient


def test_sdk_wait_for_result_polls_until_terminal(monkeypatch):
    client = EnterpriseAIPlatformClient("https://platform.example.com")
    responses = iter([{"status": "running"}, {"status": "succeeded", "output": {"ok": True}}])
    monkeypatch.setattr(client, "get_result", lambda _token: next(responses))
    monkeypatch.setattr("enterprise_ai_platform.time.sleep", lambda _seconds: None)
    result = client.wait_for_result("signed.token", poll_interval=0.1, timeout=1)
    assert result["status"] == "succeeded"
    assert result["output"] == {"ok": True}


def test_sdk_invoke_and_wait_returns_sync_response_without_polling(monkeypatch):
    client = EnterpriseAIPlatformClient("https://platform.example.com")
    monkeypatch.setattr(client, "invoke", lambda *_args: {"status": "succeeded", "output": {"ok": True}})
    monkeypatch.setattr(client, "wait_for_result", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("must not poll")))
    assert client.invoke_and_wait("acme", "app", {})["status"] == "succeeded"

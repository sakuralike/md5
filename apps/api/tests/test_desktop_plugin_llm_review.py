import json
from types import SimpleNamespace

from password_detective.core.config import Settings
from password_detective.modules.desktop_plugins import llm_review


def _arguments(provider: str) -> tuple[Settings, SimpleNamespace, SimpleNamespace, SimpleNamespace]:
    return (
        Settings(
            desktop_plugin_llm_review_provider=provider,
            desktop_plugin_llm_review_base_url="https://llm.synthetic.example",
            desktop_plugin_llm_review_api_key="synthetic-key",
            desktop_plugin_llm_review_model="synthetic-model",
        ),
        SimpleNamespace(slug="com.synthetic.review"),
        SimpleNamespace(
            semver="1.0.0",
            manifest_json={"plugin_id": "com.synthetic.review"},
            requested_capabilities=["ui:command"],
        ),
        SimpleNamespace(summary={"blocked": False}, evidence={"findings": []}),
    )


def test_openai_compatible_llm_review_uses_chat_completions(monkeypatch) -> None:
    captured = {}

    def fake_post(url, headers, body, timeout):
        captured.update(url=url, headers=headers, body=body, timeout=timeout)
        return json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"verdict": "pass", "risk_level": "low", "summary": "通过"}
                            )
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_review, "_post", fake_post)
    settings, plugin, version, review = _arguments("openai_compatible")
    result = llm_review.review_plugin(
        settings,
        plugin=plugin,
        version=version,
        static_result=review,
    )

    assert result is not None and result.verdict == "pass"
    assert captured["url"] == "https://llm.synthetic.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer synthetic-key"


def test_anthropic_compatible_llm_review_uses_messages(monkeypatch) -> None:
    def fake_post(url, headers, body, timeout):
        assert url == "https://llm.synthetic.example/v1/messages"
        assert headers["x-api-key"] == "synthetic-key"
        return json.dumps(
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "verdict": "needs_manual_review",
                                "risk_level": "medium",
                                "summary": "人工复核",
                            }
                        )
                    }
                ]
            }
        )

    monkeypatch.setattr(llm_review, "_post", fake_post)
    settings, plugin, version, review = _arguments("anthropic_compatible")
    result = llm_review.review_plugin(
        settings,
        plugin=plugin,
        version=version,
        static_result=review,
    )

    assert result is not None and result.verdict == "needs_manual_review"

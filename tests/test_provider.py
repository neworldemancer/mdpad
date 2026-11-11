import pytest

from mdpad import app as mdpad_app
from mdpad import provider as prov


@pytest.mark.parametrize(
    "url,expected",
    [
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://[::1]:11434/v1", True),
        ("https://api.openai.com/v1", False),
        ("not a url", False),
        ("", False),
    ],
)
def test_is_local(url, expected):
    assert prov.is_local(url) == expected


def test_list_models_rejects_blank_key_for_remote_host():
    with pytest.raises(prov.ProviderError):
        prov.list_models(base_url="https://api.openai.com/v1", api_key="")


def test_chat_completion_rejects_blank_key_for_remote_host():
    with pytest.raises(prov.ProviderError):
        prov._chat_completion(system="s", user="u", provider={"base_url": "https://api.openai.com/v1", "model": "m"})


def test_resolve_endpoint_allows_blank_key_for_local_url():
    bu, ak = mdpad_app._resolve_endpoint("http://localhost:11434/v1", "")
    assert bu == "http://localhost:11434/v1"
    assert ak == ""


def test_resolve_endpoint_still_requires_key_for_remote_url():
    with pytest.raises(ValueError):
        mdpad_app._resolve_endpoint("https://api.openai.com/v1", "")


def test_revise_calls_the_model_for_a_local_endpoint_without_a_key(monkeypatch):
    """Regression test: revise() used to require a truthy api_key before even
    trying, silently falling back to the mock for a no-auth local provider
    like Ollama."""
    monkeypatch.setattr(
        prov,
        "_chat_completion",
        lambda **kwargs: '{"replacement_text": "real", "explanation": "e", "warnings": []}',
    )
    proposal = prov.revise(
        package_text="pkg",
        selection="sel",
        instruction="do it",
        provider={"base_url": "http://localhost:11434/v1", "api_key": "", "model": "llama3"},
    )
    assert proposal.mock is False
    assert proposal.replacement_text == "real"


def test_revise_falls_back_to_mock_without_a_key_for_a_remote_endpoint():
    proposal = prov.revise(
        package_text="pkg",
        selection="sel",
        instruction="do it",
        provider={"base_url": "https://api.openai.com/v1", "api_key": "", "model": "gpt-4"},
    )
    assert proposal.mock is True

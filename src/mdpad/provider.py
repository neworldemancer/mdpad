"""OpenAI-compatible provider call, strict-JSON validation, and an offline mock.

The model must return strict JSON: ``{replacement_text, explanation, warnings}``.
When no provider is configured the call falls back to a deterministic mock so the
context / diff / accept flow works with zero setup. All model access goes through
this one function -- swap the transport here to support another backend.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx

SYSTEM_PROMPT = (
    "You are a scientific writing assistant. Revise the SELECTED TEXT only, "
    "following the user's instruction. Never invent citations. Preserve LaTeX "
    "math verbatim unless the instruction is about the math. Distinguish "
    "established facts from hypotheses. Respond with STRICT JSON and nothing "
    'else: {"replacement_text": str, "explanation": str, "warnings": [str]}.'
)


class ProviderError(RuntimeError):
    """Raised when the provider request or its response is unusable."""


@dataclass
class Proposal:
    replacement_text: str
    explanation: str
    warnings: list[str] = field(default_factory=list)
    mock: bool = False

    def as_dict(self) -> dict:
        return self.__dict__


def _mock(selection: str, instruction: str) -> Proposal:
    return Proposal(
        replacement_text=selection,
        explanation=(
            "Mock response — no model provider is configured, so the selected "
            f"text is returned unchanged. Instruction was: {instruction!r}."
        ),
        warnings=["Configure a provider in Settings to get real edits."],
        mock=True,
    )


def list_models(*, base_url: str, api_key: str, timeout: float = 15) -> list[str]:
    """Return sorted model ids from an OpenAI-compatible ``GET /models`` endpoint."""
    base_url = (base_url or "").rstrip("/")
    if not (base_url and api_key):
        raise ProviderError("Base URL and API key are required to list models.")
    try:
        resp = httpx.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except httpx.HTTPError as e:
        raise ProviderError(f"Model-list request failed: {e}") from e
    except (KeyError, TypeError, ValueError) as e:
        raise ProviderError(f"Unexpected model-list response: {e}") from e
    return sorted(m["id"] for m in data if isinstance(m, dict) and m.get("id"))


def _chat_completion(*, system: str, user: str, provider: dict) -> str:
    """Shared OpenAI-compatible ``/chat/completions`` call; returns raw content.

    Blank ``base_url``/``api_key``/``model`` raise ``ProviderError`` -- callers
    that want an offline fallback (e.g. ``revise``) must check beforehand.
    """
    base_url = (provider.get("base_url") or "").rstrip("/")
    api_key = provider.get("api_key") or ""
    model = provider.get("model") or ""
    if not (base_url and api_key and model):
        raise ProviderError("Provider not configured: base_url, api_key and model are required.")

    payload = {
        "model": model,
        "temperature": float(provider.get("temperature", 0.3)),
        "max_tokens": int(provider.get("max_tokens", 1024)),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=float(provider.get("timeout", 60)),
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPStatusError as e:
        detail = e.response.text.strip().replace("\n", " ")[:300]
        raise ProviderError(f"Provider {e.response.status_code}: {detail or e}") from e
    except httpx.HTTPError as e:
        raise ProviderError(f"Provider request failed: {e}") from e
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"Unexpected provider response shape: {e}") from e


def chat_text(*, system: str, user: str, provider: dict) -> str:
    """Plain-text chat completion (no JSON parsing) -- used for summarization
    and change-detection, which want prose, not the strict-JSON revise schema."""
    return _chat_completion(system=system, user=user, provider=provider)


def revise(*, package_text: str, selection: str, instruction: str, provider: dict) -> Proposal:
    base_url = (provider.get("base_url") or "").rstrip("/")
    api_key = provider.get("api_key") or ""
    model = provider.get("model") or ""
    if not (base_url and api_key and model):
        return _mock(selection, instruction)

    content = _chat_completion(system=SYSTEM_PROMPT, user=package_text, provider=provider)
    return _validate(content)


def _extract_json(content: str) -> str:
    """Pull the JSON object out of a model reply that may wrap it in a
    ``<think>`` reasoning block, markdown fences, or surrounding prose."""
    s = content
    if "</think>" in s:
        s = s.rsplit("</think>", 1)[1]
    i, j = s.find("{"), s.rfind("}")
    return s[i:j + 1] if i != -1 and j > i else s.strip()


def _validate(content: str) -> Proposal:
    try:
        data = json.loads(_extract_json(content))
    except json.JSONDecodeError as e:
        raise ProviderError(f"Model did not return valid JSON: {e}") from e
    if not isinstance(data, dict) or "replacement_text" not in data:
        raise ProviderError("Model JSON missing required field 'replacement_text'.")
    warnings = data.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    return Proposal(
        replacement_text=str(data["replacement_text"]),
        explanation=str(data.get("explanation", "")),
        warnings=[str(w) for w in warnings],
    )

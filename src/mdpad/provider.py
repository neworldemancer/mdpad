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


def revise(*, package_text: str, selection: str, instruction: str, provider: dict) -> Proposal:
    base_url = (provider.get("base_url") or "").rstrip("/")
    api_key = provider.get("api_key") or ""
    model = provider.get("model") or ""
    if not (base_url and api_key and model):
        return _mock(selection, instruction)

    payload = {
        "model": model,
        "temperature": float(provider.get("temperature", 0.3)),
        "max_tokens": int(provider.get("max_tokens", 1024)),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": package_text},
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
        content = resp.json()["choices"][0]["message"]["content"]
    except httpx.HTTPError as e:
        raise ProviderError(f"Provider request failed: {e}") from e
    except (KeyError, IndexError, TypeError) as e:
        raise ProviderError(f"Unexpected provider response shape: {e}") from e

    return _validate(content)


def _validate(content: str) -> Proposal:
    try:
        data = json.loads(content)
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

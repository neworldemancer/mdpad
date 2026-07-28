"""Build the compact, inspectable context package sent to the model.

Order (from the vision brief): project summary -> current section -> selected
text -> user instruction. Nothing else is sent. Token counts are rough ``len/4``
estimates -- a deliberate PoC stand-in for a real tokenizer.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sections import Section


def est_tokens(text: str) -> int:
    return max(1, round(len(text) / 4)) if text else 0


@dataclass
class ContextItem:
    label: str
    text: str
    tokens: int


@dataclass
class ContextPackage:
    items: list[ContextItem]
    total_tokens: int

    def as_dict(self) -> dict:
        return {
            "items": [item.__dict__ for item in self.items],
            "total_tokens": self.total_tokens,
        }

    def as_prompt(self) -> str:
        """Flatten the package into the exact text handed to the model."""
        return "\n\n".join(f"## {item.label}\n{item.text}" for item in self.items)


def build_context(
    *,
    project_summary: str,
    section: Section | None,
    selection: str,
    instruction: str,
) -> ContextPackage:
    raw = [
        ("Project summary", project_summary.strip()),
        ("Current section", f"{section.title}\n\n{section.text}" if section else ""),
        ("Selected text", selection.strip()),
        ("Instruction", instruction.strip()),
    ]
    items = [ContextItem(label, txt, est_tokens(txt)) for label, txt in raw if txt]
    return ContextPackage(items, sum(i.tokens for i in items))

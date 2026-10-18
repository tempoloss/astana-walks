"""Nothing the eval writes may name a model link that is not Google's: a private gateway profile
(`openai:<model>@<PROFILE>`, `openai:...`) is shown as one fixed label, in the runs files, the summaries and the
generated docs alike."""

from __future__ import annotations

import re

PRIVATE_LINK = "резервная модель (частный профиль)"
_SPEC = re.compile(
    r"\b([a-z][a-z0-9_-]*):((?:[\w./@-]|:(?=[\w./@-]))+)"
)  # a model name may hold colons


def _replace(m: re.Match[str]) -> str:
    provider, model = m.group(1), m.group(2)
    return PRIVATE_LINK if provider == "openai" or "@" in model else m.group(0)


def public_text(text: str | None) -> str | None:
    """`text` with every non-Google link spec (an attempt trace, a chain, a model name) replaced."""
    return None if text is None else _SPEC.sub(_replace, text)


def public_run(run: dict) -> dict:
    """`run` (one JSONL record) with its link names made public, in place."""
    run["model_link"] = public_text(run["model_link"])
    run["chain"] = [public_text(x) for x in run.get("chain", [])]
    run["generation_trace"] = public_text(run.get("generation_trace"))
    run["generation_note"] = public_text(run.get("generation_note", ""))
    intent = run.get("intent") or {}
    for key in ("model", "trace"):
        if key in intent:
            intent[key] = public_text(intent[key])
    return run

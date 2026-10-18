"""Builds results.jsonl (one row per case and mode) and findings.groups.json from results.<label>.jsonl.

    uv run python ../docs/fuzz/AssistantQA3/build_catalogue.py            # from app/

Row: case, mode (offline|live), family, requests (the exact JSON of every step; `state` shown as a placeholder), expected (the rule
in words), actual (per step: kind, lang, reply, notices, places with category / minutes / hours shown / padding), verdict
(PASS | S1 | S2 | S3 | S4: the worst severity of its findings), findings.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import matrix_cases as mc  # noqa: E402

ORDER = {"S1": 0, "S2": 1, "S3": 2, "S4": 3}


def expected_rule(case: dict, step: dict) -> str:
    e = step["expect"]
    parts = []
    if e.get("cats"):
        parts.append(("the wish is stated outright: " if e.get("hard") else "") + f"places of {e['cats']}, none outside")
    if e.get("kinds"):
        parts.append(f"answer kind in {e['kinds']}")
    if e.get("none"):
        parts.append("no place cards")
    if e.get("follow"):
        parts.append(f"follow-up «{e['follow']}» keeps the dialogue (see check)")
    if e.get("intent"):
        parts.append(f"intent carries {e['intent']}")
    if e.get("no_cat"):
        parts.append(f"never {e['no_cat']}")
    if e.get("near"):
        parts.append(f"first place within 900 m of the {e['near']} bookmark")
    if e.get("toward"):
        parts.append(f"first place closer to the {e['toward']} bookmark than the user")
    if e.get("ab"):
        parts.append("the memory setting visibly changes the answer vs the same dialogue without it")
    parts.append("always: hours/prices only from data, open only with data, no invented place, minutes match distance, answer in the message language, "
                 "no doubled words, no technical words, latency within limit")
    return "; ".join(parts)


def main() -> None:
    cases = {c["id"]: c for c in mc.CASES}
    rows = []
    for label in ("offline", "live"):
        path = HERE / f"results.{label}.jsonl"
        if not path.exists():
            continue
        by_case = defaultdict(list)
        for line in path.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            by_case[r["case"]].append(r)
        for cid, steps in by_case.items():
            c = cases[cid]
            steps.sort(key=lambda r: r["step"])
            fnd = [f for s in steps for f in s.get("findings", [])]
            worst = min((f["sev"] for f in fnd), key=lambda s: ORDER[s], default=None)
            rows.append({
                "case": cid, "mode": label, "family": c["family"], "tags": c["tags"],
                "memory": c["memory"], "bookmarks": c["bookmarks"],
                "requests": [s.get("request") for s in steps],
                "expected": [expected_rule(c, st) for st in c["steps"][: len(steps)]],
                "actual": [{
                    "say": s["say"], "kind": s["kind"], "lang": s["lang"], "reply": s["reply"], "notice": s["notice"], "answers": s["answers"],
                    "generation": (s.get("meta") or {}).get("generation"), "wall_s": s.get("wall_s"),
                    "places": [{k: p[k] for k in ("name", "category", "primary", "walk_min", "dist_m", "hours_state", "hours_text", "hours_raw", "hours_source", "padding", "price")}
                               for p in (s.get("places") or [])],
                } for s in steps],
                "verdict": worst or "PASS",
                "findings": [{k: f[k] for k in ("sev", "code", "msg", "step")} for f in fnd],
            })
    rows.sort(key=lambda r: (r["case"], r["mode"]))
    with (HERE / "results.jsonl").open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{len(rows)} rows;", dict(Counter(r["verdict"] for r in rows)))
    print("by mode:", dict(Counter((r["mode"], r["verdict"]) for r in rows)))
    fam = defaultdict(Counter)
    for r in rows:
        fam[r["family"]][r["verdict"]] += 1
    for f, c in sorted(fam.items()):
        print(f"  {f}: {dict(c)}")


if __name__ == "__main__":
    main()

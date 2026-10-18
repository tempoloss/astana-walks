"""Пересчёт чисел DialogueFuzz2 и UiFuzz (v1, v2) из закоммиченных файлов `docs/fuzz/`.

Запуск из корня репозитория: `python docs/fuzz/recount_new_rounds.py` (только стандартная библиотека).
Каждое число из `docs/verification.md` и из сводок этих раундов печатается отсюда; перцентиль — элемент
`sorted(xs)[round(p * (len(xs) - 1))]`.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

FUZZ = Path(__file__).resolve().parent


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def pct(xs: list[float], p: float) -> float:
    return sorted(xs)[round(p * (len(xs) - 1))]


def place_ids(side: dict) -> list[str]:
    return [p["id"] for p in side["places"]]


def dialogue_fuzz2() -> None:
    root = FUZZ / "DialogueFuzz2"
    dialogues = jsonl(root / "dialogues.jsonl")
    protocols = jsonl(root / "protocols.jsonl")
    findings = jsonl(root / "findings.jsonl")
    turns = [(p["id"], t) for p in protocols for t in p["turns"]]
    replies = sum(len(d["steps"]) for d in dialogues)
    print("== DialogueFuzz2")
    print("диалогов:", len(dialogues), "| реплик:", replies, "| прогонов (реплика × 2 режима):", replies * 2)
    print("записанных ответов в protocols.jsonl:", sum(2 for _ in turns), "(offline + ai)")
    for label, prefix in (("базовые d*", "d"), ("новые n*", "n")):
        sub = [d for d in dialogues if d["id"].startswith(prefix)]
        print(f"  {label}: диалогов {len(sub)}, реплик {sum(len(d['steps']) for d in sub)}")
    print("реплик в диалоге:", dict(sorted(Counter(len(d["steps"]) for d in dialogues).items())))
    for label, prefix in (("базовые d*", "d"), ("новые n*", "n")):
        sub = [t for i, t in turns if i.startswith(prefix)]
        print(f"  {label}: состав/порядок мест различается в {sum(place_ids(t['offline']) != place_ids(t['ai']) for t in sub)} из {len(sub)} реплик")
        sub_f = [f for f in findings if f["dialog"].startswith(prefix)]
        print(f"  {label}: вердикты {dict(Counter(f['verdict'] for f in sub_f))}, диалогов с не-OK {len({f['dialog'] for f in sub_f if f['verdict'] != 'OK'})}")
    print("языки:", dict(Counter(d["lang"] for d in dialogues)), "| старт:", dict(Counter(d["origin"] for d in dialogues)))
    print("вердикты по репликам:", dict(Counter(f["verdict"] for f in findings)))
    non_ok = {f["dialog"] for f in findings if f["verdict"] != "OK"}
    print("диалогов с хотя бы одной не-OK репликой:", len(non_ok), "из", len(dialogues))
    print("feature_gap по темам:", dict(Counter(f["persona"].split("_")[0] for f in findings if f["verdict"] == "feature_gap")))
    kinds_agree = sum(t["offline"]["kind"] == t["ai"]["kind"] for _, t in turns)
    print("kind офлайн == ИИ:", kinds_agree, "из", len(turns))
    print("kind в findings.jsonl расходится:", sum(f["kinds"][0] != f["kinds"][1] for f in findings))
    differ = sum(place_ids(t["offline"]) != place_ids(t["ai"]) for _, t in turns)
    with_places = [t for _, t in turns if t["offline"]["places"] or t["ai"]["places"]]
    both = [t for t in with_places if t["offline"]["places"] and t["ai"]["places"]]
    print("реплик с местами хотя бы в одном режиме:", len(with_places), "| состав/порядок мест различается:", differ)
    print("оба режима дали места:", len(both), "| другой первый (primary):", sum(t["offline"]["places"][0]["id"] != t["ai"]["places"][0]["id"] for t in both))
    print("число мест, офлайн:", dict(sorted(Counter(len(t["offline"]["places"]) for _, t in turns).items())))
    print("число мест, ИИ:", dict(sorted(Counter(len(t["ai"]["places"]) for _, t in turns).items())))
    print("kind (офлайн):", dict(Counter(t["offline"]["kind"] for _, t in turns)))
    print("ИИ generation:", dict(Counter(str(t["ai"]["generation"]) for _, t in turns)))
    print("ИИ-шаблон при живом ИИ-разборе:", [f"{i}[{t['turn']}]" for i, t in turns if t["ai"]["generation"] == "template"])
    llm = [f["llm_ms"] for f in findings if f["llm_ms"]]
    print(f"латентность ИИ-реплик: n={len(llm)}, медиана {statistics.median(llm) / 1000:.1f} с, p90 {pct(llm, 0.9) / 1000:.1f} с, макс {max(llm) / 1000:.1f} с")
    off = [t["offline"]["ms"] for _, t in turns]
    print(f"латентность офлайн (turn meta): медиана {statistics.median(off)} мс, макс {max(off)} мс")


def ui_round(name: str) -> None:
    root = FUZZ / "UiFuzz" / name
    findings = jsonl(root / "findings.jsonl")
    shots = sorted((root / "shots").glob("*.png"))
    print(f"== UiFuzz {name}")
    print("находок:", len(findings), dict(Counter(f["severity"] for f in findings)), "| скриншотов в репозитории:", len(shots))
    print("классы (id без номера/персоны):", dict(Counter(f["id"].split("-")[0] + "-" + f["id"].split("-")[1] for f in findings)))
    print("console/pageerror-записей:", sum(f["id"].startswith("console") for f in findings))
    if name == "v2":
        sessions = {(f["persona"], f["viewport"]) for f in findings}
        print("персон/вьюпортов с находками:", len({s[0] for s in sessions}), "/", len(sessions))
        hits = [f for f in findings if f["id"].startswith("hit-target")]
        print("hit-target:", len(hits), "| на телефоне:", sum(f["viewport"] == "390x844" for f in hits), "| на десктопе:", sum(f["viewport"] != "390x844" for f in hits))
        print("разных (элемент, размер):", len({f["actual"].strip() for f in hits}))
        targeted = jsonl(root / "targeted.jsonl")
        print("targeted.jsonl:", len(targeted), dict(Counter(f["id"].rsplit("-", 2)[0] for f in targeted)))


if __name__ == "__main__":
    dialogue_fuzz2()
    ui_round("v1")
    ui_round("v2")

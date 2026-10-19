"""One-screen project status for the owner's Telegram reports (every ~15 min while waves run)."""
from __future__ import annotations
import json
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]


def sh(cmd: str) -> str:
    try:
        return subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True,
                              timeout=20, encoding="utf-8", errors="replace").stdout.strip()
    except Exception as e:
        return f"(err {e})"


def main() -> None:
    lines = [f"astana-walks · статус {time.strftime('%H:%M')}"]
    cj = HERE / "supply_census.jsonl"
    if cj.exists():
        ok = [json.loads(l) for l in cj.read_text(encoding="utf-8").splitlines() if l.strip()]
        done = [r for r in ok if "error" not in r]
        lines.append(f"census: доказано {len(done)}/48 слоёв, ошибок-повторов {len(ok) - len(done)}; "
                     + "; ".join(f"{r['layer']} {r.get('total')}/{r.get('named')}" for r in done[-2:]))
    cm = HERE / "catalog_match.jsonl"
    dump = HERE / "catalog_card_dump.json"
    if cm.exists():
        rows = [json.loads(l) for l in cm.read_text(encoding="utf-8").splitlines() if l.strip()]
        hit = [r for r in rows if r.get("match") is not False]
        sched = sum(1 for r in hit if r.get("schedule"))
        gal = sum(1 for r in hit if (r.get("gallery_count") or 0) > 0)
        chk = sum(1 for r in hit if r.get("avg_check") not in (None, 0, ""))
        lines.append(f"каталог: проверено {len(rows)} POI, матчей {len(hit)} (часы {sched}, галереи {gal}, avg_check {chk})")
    elif dump.exists():
        lines.append("каталог: ключ ожил, дамп первой карчки снят, краул стартует")
    else:
        lines.append("каталог: блок = окно key+IP (не отзыв ключа: через VPS-выход тот же запрос "
                     "отвечал 200/956 секундами позже); watchdog --check через VPS раз в 15 мин, "
                     "при 200 сам крутит сессию --match (лимит 350, пауза 2.3-3.4 c, resume+miss-лог)")
    if dump.exists() and not cm.exists():
        pass
    base = ROOT / "data" / "poi.enriched.json"
    b = json.loads(base.read_text(encoding="utf-8"))
    cats: dict[str, int] = {}
    for r in b:
        cats[r["category"]] = cats.get(r["category"], 0) + 1
    hrs = sum(1 for r in b if r.get("opening_hours"))
    lines.append(f"база: {len(b)} POI | clinic={cats.get('clinic', 0)} money={cats.get('money', 0)} | часы у {hrs} ({100 * hrs // len(b)}%)")
    lines.append("git: сегодня " + sh('git log --oneline --since="00:00" | wc -l')
                 + " коммитов, HEAD " + sh("git log --oneline -1 | cut -c1-8"))
    print("\n".join(lines))


if __name__ == "__main__":
    main()

"""Phrase battery: everyday requests that produce NO reaction from the parser.

Silent means: after `parse_rules` the intent has no categories, no wished, no
free_text_keywords, no named_places/landmark_refs — and `out_of_data` does not
apologise either. A silent phrase makes the app answer a generic walk instead
of the asked kind, without admitting it (the invisible class, 24.15).

Run against a specific tree by pointing ROOT at it (worktree for a clean HEAD
measurement; the live tree to diff what a PR closed):
    python collect/recon/round13/silent_battery.py [ROOT]
Writes silent_battery.jsonl next to this file (always the live repo copy).
"""
import json, sys, time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "silent_battery.jsonl"

PHRASES = [
 'где поесть','кофейня','обед','дешёвый обед','пиво','алкоголь','сигареты','табак',
 'детский сад','поликлиника','травмпункт','сбербанк','банк','банкомат','перевести деньги',
 'почта','марка','отправить посылку','грузовое такси','остановка','автобус','метро','вокзал',
 'фонтан','скамейка','лавочка','туалет','детская площадка','батут','верёвочный парк',
 'зоопарк','аквариум','аттракцион','кинотеатр','театр','концерт','фестиваль','музей',
 'галерея','библиотека','коворкинг','wifi','зарядка','розетка',
 'кафе с детской комнатой','постамат','ozon','wildberries','где гулять с собакой',
 'выгул собак','парковка','платная парковка','велопрокат','самокаты','лыжи','каток',
 'бассейн','сауна','баня','массаж','стрижка','барбершоп','ногти','ремонт телефонов',
 'фото на документы','нотариус','адвокат','ЗАГС','суд','полиция','МЧС','пожарная',
 'ветклиника','передержка животных','гостиница','апартаменты','хостел','переночевать',
 'экскурсия','гид','сувениры','рынок','ярмарка','фудкорт','аптека','круглосуточная аптека',
 'обмен валют','ломбард','мечеть','церковь','синагога','кладбище','мемориал',
 'вечный огонь','пантеон','байтерек','арка','набережная','эко-тропа','смотровая площадка',
]


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parents[2]
    sys.path.insert(0, str(root / "app"))
    from walks.dialog_nlu import out_of_data
    from walks.intent import parse_rules
    from walks.lexicon import landmark_refs, named_places
    rows = []
    for t in PHRASES:
        i = parse_rules(t, datetime(2026, 10, 19, 15, 0)).intent
        ch = {
            "categories": list(i.categories),
            "wished": list(i.wished),
            "keywords": list(i.free_text_keywords),
            "named_places": bool(named_places(t)),
            "landmark_refs": bool(landmark_refs(t)),
        }
        ood = out_of_data(t)
        silent = ood is None and not any(ch.values())
        rows.append({"phrase": t, "ood": ood, "silent": silent, **ch})
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    n = sum(1 for r in rows if r["silent"])
    print(f"root={root} at {time.strftime('%F %T')} | phrases={len(rows)} silent={n}")
    print("silent:", [r["phrase"] for r in rows if r["silent"]])


if __name__ == "__main__":
    main()

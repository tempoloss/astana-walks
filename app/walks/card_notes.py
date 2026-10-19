"""The notes under a card that code writes from the record and the request, whoever wrote the card's own text: the
chain, the weather / air / darkness, the holiday and the hours, a place that is not of the requested kind, the
wishes the data cannot confirm, the marks of people."""

from __future__ import annotations

from .attributes import has_socket, has_wifi, pets_signal
from .claims import capacity_backed, note_keys, unsupported_wishes
from .colocated import SHARED_COORD
from .feedback import hours_label
from .i18n import category_name, holiday_name, points, source_label, t
from .kids import unnamed_more
from .models import HOURS_SUFFIX, Candidate, Intent, WeatherInfo
from .radius import FAR_ON_FOOT, NEAREST_FAR, km_text
from .reasons import hours_notes, weather_notes
from .stay import TIGHT_FIT, min_stay


def people_notes(c: Candidate, intent: Intent) -> list[str]:
    """Hours evidence from people's marks, a level of its own beside the OSM hours."""
    ev = c.people
    lang = intent.language
    label = hours_label(ev, lang) if ev is not None else None
    if ev is None or label is None:
        return []
    note = f"{label[0].upper()}{label[1:]}{t('people_sep', lang)}{source_label(ev.demo, lang)}"
    vs = f"people_vs_{HOURS_SUFFIX.get(c.poi.hours_source() or '', 'osm')}"
    if c.hours_state == "open" and ev.hours != "open":
        return [f"{note}; {t(vs, lang)}."]
    if c.hours_state == "unknown" and ev.hours != "mixed":
        return [f"{note}; {t('people_not_hours', lang)}."]
    return [f"{note}."] if c.hours_state == "unknown" else []


# what of Wi-Fi and sockets the person asked (Intent.needs_wifi_socket, Intent.work_needs) the record cannot confirm:
# neither («Wi-Fi/розетки не подтверждены», the label the eval counts), sockets («Wi-Fi есть по данным; розетки не
# подтверждены»), Wi-Fi
WORK_NOTES = (
    "note_wifi",
    "note_socket_unverified_wifi",
    "note_socket_unverified",
    "note_wifi_unverified_socket",
    "note_wifi_unverified",
)


def work_note(c: Candidate, intent: Intent) -> str:
    """The note key of the Wi-Fi / sockets asked for that the record does not confirm, '' when it confirms all that was
    asked: a tag of the record is «по данным»; people's marks count too (their own line says them)."""
    if not intent.needs_wifi_socket:
        return ""
    ev = c.people
    wifi_tag, sock_tag = has_wifi(c.poi), has_socket(c.poi)
    wifi, sock = wifi_tag or bool(ev and ev.wifi), sock_tag or bool(ev and ev.socket)
    if not (wifi or sock):
        return "note_wifi"
    asked = intent.work_needs or "both"  # the model alone set the wish: Wi-Fi and sockets
    if asked != "wifi" and not sock:
        return "note_socket_unverified_wifi" if wifi_tag else "note_socket_unverified"
    if asked != "socket" and not wifi:
        return "note_wifi_unverified_socket" if sock_tag else "note_wifi_unverified"
    return ""


def claim_notes(removed: list[str], data: list[str], lang: str) -> list[str]:
    """The notes of what the model claimed that the record does not back (walks.claims), unless the card's own notes
    say it already: a stripped «есть розетки» next to «Wi-Fi есть по данным; розетки не подтверждены» needs no second
    «Wi-Fi/розетки не подтверждены»."""
    work = any(t(k, lang) in data for k in WORK_NOTES)
    out: list[str] = []
    for key in note_keys(removed):
        note = t(key, lang)
        if note not in data and note not in out and not (work and key == "note_wifi"):
            out.append(note)
    return out


def _wish_notes(c: Candidate, intent: Intent) -> list[str]:
    """Notes for the wishes the records cannot confirm: diets (and the coeliac advice), the night with unknown hours,
    and wishes no field can answer (a toilet, a changing table, a kids menu)."""
    lang, out = intent.language, []
    for r in c.reasons:
        kind, _, diet = r.partition(":")
        if kind == "diet_unverified":
            out.append(t(f"note_diet_{diet}", lang))
        elif kind == "diet_none":
            out.append(t(f"note_diet_none_{diet}", lang))
        else:
            continue
        if diet == "gluten_free":
            out.append(t("note_gluten_medical", lang))
    if "night_unknown" in c.reasons:
        out.append(t("note_night_unknown", lang))
    if intent.minor:
        out.append(t("note_minor", lang))
    if getattr(intent, "pets", False) and not pets_signal(c.poi):
        out.append(t("note_pets", lang))
    if getattr(intent, "group_size", 0) >= 2 and not capacity_backed(c):
        out.append(t("note_group", lang))
    if cap := getattr(intent, "price_cap_kzt", 0):
        out.append(t("note_price_cap", lang, cap=cap))
    elif intent.budget == "low" and "fee" not in c.poi.tag_dict():
        out.append(t("note_cheaper", lang))
    words = intent.free_text_keywords
    if (
        c.poi.category == "public_toilet"
    ):  # the record IS the toilet asked for: no «нет данных о туалете» on it
        words = [k for k in words if unsupported_wishes([k], "ru") != ["туалет рядом"]]
    out += [t("note_unsupported", lang, what=w) for w in unsupported_wishes(words, lang)]
    return out


def data_notes(c: Candidate, intent: Intent, weather: WeatherInfo | None = None) -> list[str]:
    lang = intent.language
    out: list[str] = []
    if c.nearby_same:
        out.append(t("note_chain", lang, n=points(c.nearby_same, lang)))
    out.extend(weather_notes(c, weather, lang))
    if c.hours_note.startswith("праздник"):
        name = holiday_name(c.hours_note.split(": ", 1)[-1], lang)
        out.append(t("note_holiday", lang, name=name))
    out.extend(hours_notes(c, lang))
    if NEAREST_FAR in c.reasons:
        cat = category_name(c.poi.category, lang)
        out.append(t("note_nearest_far", lang, cat=cat, km=km_text(c.distance_m, lang)))
    elif (
        FAR_ON_FOOT in c.reasons
    ):  # the nearest dentist 7 km away: the card that leads the way there
        out.append(t("note_far_on_foot", lang))
    elif c.padding == "expanded":
        out.append(t("note_expanded", lang))
    if "off_category" in c.reasons:
        indoor_pick = "weather_indoor" in c.reasons or "air_indoor" in c.reasons
        shelter = indoor_pick and weather is not None and weather.indoor_preferred
        out.append(t("note_off_category_weather" if shelter else "note_off_category", lang))
    if note := work_note(c, intent):  # «Wi-Fi есть по данным; розетки не подтверждены»
        out.append(t(note, lang))
    out.extend(people_notes(c, intent))
    if "visited" in c.reasons:
        out.append(t("note_visited", lang))
    if "wheelchair_unverified" in c.reasons:
        out.append(t("note_wheelchair", lang))
    if "halal_unverified" in c.reasons:
        out.append(t("note_halal", lang))
    if "halal_none" in c.reasons:
        out.append(t("note_halal_none", lang))
    out.extend(_wish_notes(c, intent))
    if c.nearby_anon:
        out.append(unnamed_more(c.nearby_anon, lang))
    if (
        TIGHT_FIT in c.reasons and intent.time_stated
    ):  # «впритык по времени»: only against a time the person set
        lo, left = min_stay(c.poi.category), intent.time_budget_min - 2 * c.travel_min
        out.append(t("note_tight", lang, lo=lo, left=max(left, 0)))
    if SHARED_COORD in c.reasons:
        out.append(t("note_shared_coord", lang))
    return out

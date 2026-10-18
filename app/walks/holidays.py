"""Public holidays / non-working days of Kazakhstan, 2026-2027 (static list).

On such a day the OSM `opening_hours` of a venue (usually written for ordinary weekdays) is not reliable, so
`hours.hours_state` turns an "open" state into "unknown (праздник)". A closed state stays closed.

Sources (checked 2026-10-16):
- 2026: official list of the Government portal, https://www.gov.kz/article/33969?lang=ru
  ("Праздничные и выходные дни в Республике Казахстан в 2026 году"): 1-2 Jan; 8 Mar -> Mon 9 Mar; 21-23 Mar
  (Sat/Sun 21-22 Mar -> Tue/Wed 24-25 Mar); 1 May; 7 May; 9 May (Sat) -> Mon 11 May; 6 Jul; 25 Oct (Sun) ->
  Mon 26 Oct; 16 Dec. First day of Kurban Ait 27 May and Orthodox Christmas 7 Jan are days off without transfer.
- Law "О праздниках в Республике Казахстан" of 13.12.2001 No. 267-II, art. 3 (https://adilet.zan.kz/rus/docs/
  Z010000267_), as amended by Law of 11.06.2026 No. 306-VIII, in force from 01.07.2026: Constitution Day moves
  from 30 Aug to 15 Mar (so 30 Aug is NOT a holiday in 2026-2027, 15 Mar is from 2027). adilet.zan.kz renders
  with JavaScript, so the amended art. 3 text was read from the reprints at https://pro1c.kz/news/zakonodatelstvo/
  den-konstitutsii-rk-perenesen-na-15-marta/ and https://cdb.kz/sistema/novosti/
  prazdnovanie_dnya_konstitutsii_pereneseno_na_15_marta/, which quote the law.
- 2027 is NOT an official list: no Government transfer resolution for 2027 was found, so the dates are computed
  by the law's rule (a state/national holiday on Sat/Sun moves the day off to the next working day) from art. 3 as
  amended. Kurban Ait 2027 follows the lunar calendar (DUMK): expected Sun 16 May (no transfer for religious
  holidays); Mon 17 May is added as well because the exact day may shift by one - the only effect of a false
  positive is "open" -> "unknown", never a wrong "open".
"""

from __future__ import annotations

from datetime import date

HOLIDAYS: dict[date, str] = {
    # 2026, gov.kz
    date(2026, 1, 1): "Новый год",
    date(2026, 1, 2): "Новый год",
    date(2026, 1, 7): "Рождество Христово",
    date(2026, 3, 8): "Международный женский день",
    date(2026, 3, 9): "Международный женский день (перенос)",
    date(2026, 3, 21): "Наурыз мейрамы",
    date(2026, 3, 22): "Наурыз мейрамы",
    date(2026, 3, 23): "Наурыз мейрамы",
    date(2026, 3, 24): "Наурыз мейрамы (перенос)",
    date(2026, 3, 25): "Наурыз мейрамы (перенос)",
    date(2026, 5, 1): "Праздник единства народа Казахстана",
    date(2026, 5, 7): "День защитника Отечества",
    date(2026, 5, 9): "День Победы",
    date(2026, 5, 11): "День Победы (перенос)",
    date(2026, 5, 27): "Курбан айт",
    date(2026, 7, 6): "День Столицы",
    date(2026, 10, 25): "День Республики Казахстан",
    date(2026, 10, 26): "День Республики Казахстан (перенос)",
    date(2026, 12, 16): "День Независимости",
    # ---- 2027 (computed by the weekend-transfer rule; see module docstring)
    date(2027, 1, 1): "Новый год",
    date(2027, 1, 2): "Новый год",
    date(2027, 1, 4): "Новый год (перенос)",
    date(2027, 1, 7): "Рождество Христово",
    date(2027, 3, 8): "Международный женский день",
    date(2027, 3, 15): "День Конституции Республики Казахстан",
    date(2027, 3, 21): "Наурыз мейрамы",
    date(2027, 3, 22): "Наурыз мейрамы",
    date(2027, 3, 23): "Наурыз мейрамы",
    date(2027, 3, 24): "Наурыз мейрамы (перенос)",
    date(2027, 5, 1): "Праздник единства народа Казахстана",
    date(2027, 5, 3): "Праздник единства народа Казахстана (перенос)",
    date(2027, 5, 7): "День защитника Отечества",
    date(2027, 5, 9): "День Победы",
    date(2027, 5, 10): "День Победы (перенос)",
    date(2027, 5, 16): "Курбан айт (дата по лунному календарю)",
    date(2027, 5, 17): "Курбан айт (дата по лунному календарю)",
    date(2027, 7, 6): "День Столицы",
    date(2027, 10, 25): "День Республики Казахстан",
    date(2027, 12, 16): "День Независимости",
}


def holiday_name(d: date) -> str | None:
    """Name of the public holiday / transferred day off on `d`, or None."""
    return HOLIDAYS.get(d)

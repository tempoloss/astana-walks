# walks.dialog — the dialogue API

One pure function per user message: `take_turn(state, message, env) -> Outcome(turn, state, result)`. Models are
pydantic (JSON in and out): `walks/dialog_types.py`. A UI renders `Turn` and sends the user's text back; it never
parses follow-ups, computes «open now», builds buttons or cuts text itself.

```python
from walks.dialog import new_state, with_location, take_turn, TurnEnv
state = new_state(lat, lon, lang="ru")                 # rounded to ~100 m inside
out = take_turn(state, "хочу кофе", TurnEnv(...))      # TurnEnv optional
turn, state = out.turn, out.state                      # out.result: python-only walks.models.Result | None
state = with_location(state, lat, lon)                 # the user moved the point: the dialogue restarts
```

* A button click is `take_turn(state, chip.send)`; there is no other action API. «Новый поиск» (`kind="reset"`) is a phrase
  the parser reads as a reset.
* `take_turn` never mutates `state`; the state is JSON and holds no request text (ids, rounded coordinates, constraints;
  `demo_base` only for a dialogue that is pinned, see the last point).
* `TurnEnv` (all optional): `when`, `weather` (a `WeatherInfo`, or a function that returns one: it is called only by a search
  that is not pinned, so a pinned answer never waits for the live weather; the web server's function returns the last value
  of a background refresh, `walks.weather.latest_weather`, and never touches the network itself), `use_llm` (False = rules + template text),
  `router`, `profile`, `feedback`,
  `pois`, `language` (fixed by the user; None = detected per message, sticky for messages with no signal),
  `budget_min` (30 / 60 / 120) and `company` («solo» / «pair» / «kids») — taps next to the input box, applied to a NEW
  search only, the words of the message win, `bookmarks` (the user's own named places from their device, ≤ 10, see below),
  `on_stage(name)` called with `parse`, `search`, `write`, `route`.
* **Bookmarks** (`TurnEnv.bookmarks`, `POST /api/turn` `bookmarks[{name ≤ 40, kind home|work|study|other, lat, lon}]`):
  rounded to 3 decimals, used for this request only, never stored or logged (a request that carries any is never written to
  the request log). A message that names one — «рядом с домом», «возле школы», its own name — is searched around it
  (`turn.origin` is then the bookmark, the lead says «от «Дом»»); «по пути домой», «по дороге на работу» is searched along
  the way (places closer to it than the user, small detour; the origin stays the user). The words that named it are not a wish
  for a place («возле школы» is not a request for schools). Late (22:00–05:00) with a `home` bookmark, a request for food,
  coffee or a drink prefers places closer to home than the user is, and the lead adds «и как раз по пути домой» only when the
  first place really lies that way (`Result.on_the_way`). A follow-up keeps the bookmark (`DialogState.bookmark` /
  `bookmark_mode`) while it is still sent.
* The demo pin (`WALKS_DEMO_PIN=1`) is decided per request (`demo_pin.pins(text, base)`): only a recorded request — a scenario
  starter or one of `presets.DEMO_REQUESTS` — and a follow-up of a dialogue that began with one (`state.demo_base` is that first
  message) run at the pinned time, with the pinned weather, router and seed marks (as the old UI did). Every other request
  is answered like an unpinned app: `env.when` or the real local time, `env.weather`, `env.router`, `env.feedback`. A request
  that is not a follow-up leaves the pin, and so does the rest of its dialogue (`demo_base` becomes None).

## Turn kinds

`places` (≤3 places, `places[0].primary`), `none_found`, `place_answer` (a question about shown or named places, or about the
afisha / the airport bus; no new search, `state.shown` unchanged; `places[0]` is the place answered about), `clarify` (nothing actionable: one
question and 4–6 `start` chips), `thanks`, `bye`, `refusal`. `reply` of a `places` turn is the **lead**, one or two sentences
(`walks/dialog_lead.py`): the conditions in Astana now («Сейчас +12 °C, ощущается как +9, идут осадки, уже темно, в Астане
действует НМУ — воздух хуже обычного, поэтому сначала места в помещении»), what the person wants («Вы ищете, где
выпить»: the model's paraphrase after code's checks, else «Вы ищете: бар»), then the recommendation with the facts from
the data («советую «X», 6 мин пешком, открыто до 02:00 — и как раз по пути домой; ниже ещё два места»). Every number,
hour and name is inserted by code; the temperature is said only for the real present (a time set by hand, `env.when`,
says nothing about another hour); an absent datum is not mentioned. A follow-up («поближе») gets only the new
recommendation. Any other turn: one short sentence (an answer about
several places: one short sentence each); `notice` is one honest remark under it («на бар этого времени мало: обычно
нужно от 30 мин»), usually empty; the page no longer shows weather / air / darkness as separate boxes. Chips: at most four contextual `refine` chips that would change the request (ru
`send` = the phrases of `scripts/warm_cache.py`) plus one `reset`; `label` is shown, `send` is handed back.

A message the rules cannot read (slang, typos, «куда сходить») goes to the model's intent step **before** any clarifying
question (when a model is available): the model's reading is reused by the search (one call), a kind of place or a wish it
finds is searched. A bare «куда сходить / where should I go / қайда барсам болады» that the model does not read (or with no
model) gets the default answer of `walks/outing.py` (a walk, a sight, a café, a museum, ordered by the usual rules; the lead
names no kind); `clarify` is answered only for a message nobody reads. Safety stays: a minor never gets bars, a refusal (the
rules', or the model's own `refusal`) is never lifted, and a kind the person asked for that a safety rule left out is said in
one sentence at the start of the lead («Бары и алкоголь до 18 лет не предлагаю.», «Бары не показываю: включено «без
алкоголя».»), never named as the wish. «Вы ищете: …» names only the kinds the person's own words name (`Intent.wished`),
never a kind a mood, a default or a back-fill added.

A kind the message rules out («не хочу в кафе, хочу гулять», «не надо заведений», «без алкоголя») is `Intent.refused`: a hard
exclusion in retrieval for that request and its follow-ups, which the model cannot bring back (`merge_intents`); a negator
reaches the kind past «хочу / надо / идти / в / на» but never past a comma («нет, хочу в кафе» is a café). A toilet («туалет»,
«где туалет», «дәретхана», «toilet», «restroom») is the kind `public_toilet`, never padded with other places; when the data
hold none near, the reply says so as the data's absence («В наших данных туалетов рядом нет — уточните на месте или в
ближайшем ТРЦ/кафе»), never «рядом нет туалетов»; next to another kind («кафе с туалетом») it stays a wish the cards answer
honestly. The reply speaks the language of the current message (`lang_fixed` aside): a Cyrillic message is never answered
in English, a short word of both languages keeps a Kazakh dialogue, and a message without words («☕») takes the saved answer
language of the profile.

`Place`: id, name, kind, category, lat/lon, `primary`, `why` (≤ ~25 words, whole sentences), `what_to_do` (one
sentence), `ai_idea`, `walk{minutes, distance_m, method, mode, text}`, `hours{state, text, raw, source{label,url}, issue,
note, data_date}` (text: «Открыто до 22:00» / «Закрыто, откроется в 10:00» / «Открыто круглосуточно» / «Часы
неизвестны»), `people`, `caveat`, `note`, `text_source` (`llm` | `template`), `padding`, `sources[]`, address, phone,
website, and the optional `Hours.today` / `Hours.soon` / `Place.price` (see «Fields for the compact panel»). After «ещё» an AI
answer never carries a template back-fill card (one voice per answer).

**A wish the person names beats the system's defaults.** «погулять / прогуляться / пройтись / подышать», «в парк», «на смотровую»,
a dog to walk (`Intent.wished`: the kinds the words themselves name, read by the rules from the current message; a mood such as
«с ребёнком» or «холодно» names none) is answered with outdoor walking places (park, square, embankment, viewpoint) whatever the
weather, the air or the darkness: no indoor substitution, no café or mall as padding, and the stated kind comes before anything
the system added (also at 23:00–06:00 and in the late-home bias). The conditions only order inside the kind (nearer first;
after dark places beside a street the data tag `lit=yes` first, `city_layers.lit_near`; no tag is never «unlit»), shorten the
stay, and are said in the lead as advice («воздух хуже обычного, уже темно, гулять лучше недолго; сначала места у освещённых
улиц (по данным OpenStreetMap)»). The time-fit rule keeps a named kind whose usual stay is longer than the time left, flagged
(`NAMED_OVER_BUDGET`). A request with no stated wish («куда сходить») keeps the indoor substitution (`padding: substituted`,
`caveat`). A children's playground is not in the walking family: with a child in frost or smog the shelter rule stays.
«Вы ищете …» keeps the person's terms: the model's paraphrase must name the stated wish (`walks.want`), otherwise the template
says it («Вы ищете, где прогуляться»). The profile's «не показывать» (`Constraints.avoid`) is a hard exclusion in retrieval, lifted
only for a kind the message names by its own word («хочу кофе», «в бар»; a word for a family such as «поесть» does not lift
it); an empty result is the honest «ничего не нашлось». Saved settings that changed the answer are
said once at the end of the lead («Учтены ваши настройки: халяль — отмечен у 1 из 24 мест рядом, их ставлю первыми»), with the
real counts of the records (`Filters.halal_*`, `step_free_*`, `excluded_alcohol`); nothing is said per card, and halal is
never said on an answer without a place to eat. The budget setting is «не важно / недорого» only: the data hold no prices,
so a mid-range or pricier bill could change nothing (a profile saved with one loads as «не важно»).
`meta.generation_retry` (optional, `""` | `live` | `failed`): a recorded / cached answer left no card
with the model's own text, so on a stand with live models the chain was asked once more without the cache (`live`: that
answer is used; `failed`: the models could not answer and the recorded cards stay). Replay-only and offline never retry.

Questions about places resolve to: an ordinal («второе»), a shown place's name, a plural («они»), the place the last
question was about, else the main one; a place NAMED in the message is answered wherever it is (distance, hours with
today's interval and source, or «в данных нет»); a name that is not in the data is said so.

## Lines from the data layers (optional fields)

Every field below is optional, empty or `None` when its layer has nothing to say, and appears only when the data backs
it. An old client that ignores them keeps working. Nothing here reaches
the model's prompt or payload (the recorded demo answers keep their cache keys): it is deterministic post-processing of a
finished search. Wording is in `walks/i18n_notices.py`, `i18n_signals.py`, `i18n_afisha.py` (kk / ru / en).

* `Turn.events` — «Сегодня рядом» (`heading`, `items[]`, `note`): on a `places` / `none_found` turn at most **two**
  events of the afisha (`data/events.json`) that are on near the point or start inside the next three hours, each with
  `title`, `when`, `venue`, `distance_m`, `price`, `text` and `source{label,url}` (the event's own page). Silent (`None`)
  when `nearby_events` has nothing; «событий нет» is never said. `note` carries the staleness remark of an old snapshot.
* A question about the afisha («что сегодня интересного», «концерт вечером», «кино сегодня», «афиша»; kk / en alike) is a
  `place_answer` turn with no `places` and `state.shown` unchanged: `events` holds up to **three** events from now to the
  end of the day within 3 km, and `note` names the few sources the afisha has (Sxodim, InAstana, YouTicket, …) and says
  it is not every event of the city. With nothing listed, `reply` says so and names the sources; with no file, «данных
  афиши нет». It never invents an event.
* `Turn.notices[]` — one extra line each, `{kind, text, source{label,url}, detail}`:
  `weather` — an active official Kazhydromet notice **about Astana**, short, with its link (`source.url`, mandatory):
  «НМУ в Астане 18 октября» (the bulletin names several cities; only Astana's day is kept, never a list of others) or a
  storm warning cut to the sentences that name Astana. The weather *now* (temperature, precipitation, the airport
  station's fog / wind, bad air, darkness) is not a notice: it is part of the lead sentence (`reply`, see «Turn kinds»).
  `airport` — «последний автобус № 10 в аэропорт — 21:23» (nn-airport.kz), only when the request mentions an airport,
  flight, train or station (аэропорт, вылет, рейс, вокзал, поезд; kk / en) **and** the time makes it relevant (the evening
  before the last bus, after it has left, before the first runs).
* «Как добраться до аэропорта» / «последний автобус»: a `place_answer` whose `reply` lists the routes, their first and last
  departures, the interval and the fare, with the `airport` notice (link) at any hour; without the timetable file it says
  there is none and where to look.
* `Place.signal` — `{kind: "osm_note", text, source{label,url}, date}`: an **open** OpenStreetMap note (≤ 50 m, mentions
  the place's name or kind) classified as closure or hours: «на OpenStreetMap есть заметка: место могло закрыться
  (27.06.2026)» with the link to the note. A suspicion, never «закрыто». `Result.recs[i].confidence` of such a place is at
  most `medium`. Also on the card of a `place_answer`.
  `kind: "state_registry"`: the one schedule line of a ЦОН card («сб: 09:00-13:00; по данным gov4c.kz», `source` = the
  operator's page, `date` = snapshot day) for the asked day. A request that names a state service («ЦОН в субботу
  работает?», «справку получить», ХҚКО, `public service centre`) is a normal `places` turn of the nearest ЦОН; `reply` is
  «<ЦОН>: в субботу — 09:00–13:00. Источник: ЦОН (gov4c.kz).» («сейчас» for today / no day; «завтра», a weekday ahead =
  that day), or, when no branch works then, «По данным gov4c.kz в воскресенье ни один ЦОН не работает.»; chips only
  «ещё / поближе», no route. A ЦОН never appears in any other answer. A sports object with register №730 gets no card
  line: its office week is added to the answer about its hours as «график администрации … — не часы работы объекта».
* `Place.stop` — `{name, minutes, distance_m, text, source}`: the nearest bus stop (GTFS stops, the two directions of
  one stop merged, within 500 m) with the walking minutes; card details only.
* `Route.lighting` — one line, only after dark and only when the street lines of every leg are known and most of the way
  runs along ways tagged `lit` in OpenStreetMap: «большая часть пути по освещённым улицам — по данным OpenStreetMap».
  Streets without a tag are unknown, never dark: there is no line about unlit streets.

## Fields for the compact panel (optional)

All optional, ignored by an old client; each is absent (or `None`) when the data has nothing behind it.

* `Hours.today` — the open spans of the arrival day in hours, `[[8.0, 24.0]]`, what a card's day strip draws. `[]` is a
  place whose schedule is known and which is closed all day; `None` is no schedule at all (also while `state` is
  `unknown`: no strip is drawn, never drawn from a schedule the answer does not trust). `Hours.soon` — the place
  is open and its schedule closes within the hour after arrival («скоро закроется»); the page colours that state amber.
* `Place.price` — `{text, source{label,url}, date}`: the place's own price wording («1000 тг.», «500-3,000 tenge»),
  verbatim and never parsed into a number, whose it is (the venue's site, the museum register, Wikivoyage, …: named the same
  way as in the answer to «сколько стоит») and the day it was read. The card and the details say «Вход: …» only when it exists.
* `Route.kind` — `plan` when the user listed stops in an order (`Intent.plan_order`) and the route runs through at least
  two of them; `nearest` otherwise (the nearest-first loop that only sets the minutes of the legs, not a path to walk). The
  map draws the whole route for a `plan` and only the way to the selected place for `nearest`.
* `place_legs` in the page's answer (`web.turns.answer`, beside `turn`, one entry per `turn.places`, in order): `place_legs[i]` =
  `{minutes, meters, method, shape}`, the way from the turn's origin to that place. The minutes, metres and method are
  the place's `walk` (`valhalla` | `straight` | `estimate`); `shape` is the street line `[[lat, lon], …]` or `null` (the
  map then draws a faint straight line, with «≈» before the minutes). The line comes from the router's cache, or from one
  request to a router of one's own (`WALKS_VALHALLA_URL`, kept in memory); the shared public server is never asked for a line.
* `at` in the page's answer — `{time: "HH:MM", date: "YYYY-MM-DD"}`, the moment the answer is about (what the day strip
  marks as «сейчас»); `GET /api/config` has `now`, the stand's clock (`YYYY-MM-DDTHH:MM`, the pinned moment in a demo).


## CLI

`python -m walks.cli --dialog [--script file.json] --lat .. --lon .. [--lang ru|kk|en] [--no-llm] [--offline] [--time ..]
[--weather ..] [--no-walking]`: one message per stdin line or a JSON list (`"text"` or `{"say", "lang", "time"}`); one JSON
object per turn: `{"say", "turn", "state"}`.

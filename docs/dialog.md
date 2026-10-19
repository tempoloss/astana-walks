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
  `on_stage(name)` called as the core enters each step: `parse` (the turn starts reading the message), then for a search
  `search`, `hours`, `write` (once per reading searched: a model reading that differs from the rules' one searches
  again) and `route`.
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

**The model writes from facts, code checks them.** Each candidate goes to the model as a fact sheet (`walks/facts.py`): name,
kind, its own description (Wikipedia, Wikivoyage, the official site, OSM), cuisine, the features its tags state (seats outside,
Wi-Fi, a playground, lit, free entry …), the street, the verified hours and walking minutes, people's marks. A reason must use
at least one concrete fact of its place and no filler that fits any place («удобно расположено», «в уютной обстановке», «отлично
подходит для», «Закажите горячие блюда», «Ещё одно кафе»; `walks/specific.py`): a vague card is asked once more (`rewrite`) when
the first answer came within 5.5 s of the request (`walks/llm.REWRITE_CUTOFF_S`), then the template's fact-based card replaces
what is still vague; a later answer skips the rewrite and gets the template's card at once. Numbers in the model's text are
kept only when the record holds them (its walking minutes, the times of its hours). The model's `opening` becomes the lead when
code can stand behind it (it names the first card, the stated wish, only the payload's numbers, no place the answer does not
show, the answer language); otherwise the template lead. The conditions line is said once per dialogue (`DialogState.told`),
not before every answer.

**A status is written by code only, for one moment.** «Открыто до 22:00 / Закрыто, откроется в 10:00 / Открыто круглосуточно»
come from `walks/status.py`: the state and the next change are read from the record at the same moment (the arrival; a
card once mixed the state on arrival with the change time on departure and said «Open until 10:00» at 03:10 for a place open
10:00–21:00), and a close after midnight that is half a day away is said with its day («до 05:00 следующего дня»). The model
gets that line ready (`status` in the fact sheet, no raw schedule) and any sentence of its reasons or opening that states a
status or an hour in other words is dropped (`specific.keep_status`). A reason never states the status either: the card's
hours line does. Template reasons are the record's own facts (wishes it confirms, people's marks, cuisine, features,
Wikipedia), never a selection note («ближайшее из N подобранных», «категория — как вы просили», «совпадает с …»); with none
the card says only what the place is. The conditions are said only when they matter for the request: the cold, the sky and
the dark for a walk, the air only for a stated outdoor wish, the official notice for a walk or a drive, at most two clauses;
a café answer gets none, and the notice line under it is not shown. «По пути домой» needs real progress toward home (a
share of the way, `bookmarks.TOWARD_SHARE`) and a sane detour. An English answer shows the record's English name.

**Variety.** A place shown earlier in the dialogue is not offered again while others answer the request, unless the message
names it (`walks/variety.py`, `Conversation.shown_ids` kept for the whole dialogue at one point); an unnamed record («Парк /
сквер») comes after the named places of its kind. «Поближе» never widens the radius past its cap. «Подешевле / подороже» exist
only where the kind of place is the lever (food: fast food and a café are cheaper by nature, a restaurant pricier; the lead says
«цен в данных нет»); a bar, a cinema or a mall gets no such chip. «С ребёнком» on a walk brings the playgrounds in.
With no time stated (and no «недалеко / рядом / nearby»), the search reaches as far as a 90-minute outing (`radius_floor_m`,
~1.1 km, not when the weather or the air caps the walk) while the route is still planned for the default 60 minutes; the
widening steps stop where the time's own circle would. «Что посмотреть / what should I see / не көруге болады /
достопримечательности» is a named wish of landmarks, viewpoints and museums (`sights_wish`); the sight the person stands at
(Байтерек from Байтерек) is offered, not skipped as the starting point.
`meta.generation_retry` (optional, `""` | `live` | `failed`): a recorded / cached answer left no card
with the model's own text, so on a stand with live models the chain was asked once more without the cache (`live`: that
answer is used; `failed`: the models could not answer and the recorded cards stay). Replay-only and offline never retry.

Questions about places resolve to: an ordinal («второе»), a shown place's name, a plural («они»), the place the last
question was about, else the main one; a place NAMED in the message is answered wherever it is (distance, hours with
today's interval and source, or «в данных нет»); a name that is not in the data is said so.

What the data answers about a place (`walks/dialog_facts.py`, topics of `PlaceAnswer.topic`; never a new search, `state.shown`
unchanged): `entry` — «вход платный», «does it cost money to go in», «киру ақылы ма» — the place's own price wording (the
museum register's, the site's, Wikivoyage's) with its source and the day it was read («по данным реестра музеев, данные на
17.10.2026»), else «в данных этого нет»; `menu` / `menu_kazakh` / `menu_kids` — «what do they serve», «is that Kazakh food»,
«есть детское меню» — the OpenStreetMap `cuisine` tag and the place's own description with its source; a kids' menu and the
menu itself are in no record and the answer says so; `route` — «how long to walk from here to Baiterek» — minutes from the
person to the named place, by the streets when the walking router has the leg («по улицам»), else by the straight line; `hours`
with a day — «а в воскресенье», «is it open tomorrow» — that day's hours with the day named, never «сейчас».

A question about the weather («какая погода», «а че там с погодой», «what's the weather tomorrow, what should I wear», «ауа райы
қандай», «что надеть», `walks/dialog_weather.py`) is a `place_answer` with `answers[0].topic == "weather"` (the airport
observation with the MET Norway forecast beside it; for another time the forecast of that hour, or «прогноза на это время в
данных нет») and, when a Kazhydromet notice for Astana is in force, `answers[1].topic == "weather_notice"` with its link;
`places` repeats the places shown before (same ids) so the map keeps them; a request with a place kind or «куда / где / что
делать» in it is still a search.

Time words (`walks/dialog_when.py`): «завтра», «послезавтра», «утром / днём / вечером / ночью», «в воскресенье», «tomorrow
morning», «lunch tomorrow» (a meal sets the hour only next to a day), «ертең», «кешке», «жексенбіде». They set `env.when`
for the turn, so open-now, hours and the forecast are for that time, are cut out of the message before it is read, and a
search reply starts with the time it answers for («Завтра днём, 13:00. …»); a time alone repeats the previous kind as a
follow-up (the hours of the place when the last answer was about one place). The present is never stamped. A state-service
request («ЦОН в субботу») keeps its own reading of the day.

Round 2 (`walks/dialog_facts.py`, `dialog_when.py`, `dialog_weather.py`): `socket` — «а тут розетки есть» — the `socket:*` / Wi-Fi tags of the
record, else «в данных этого нет»; `kids_room` — «ойын бөлмесі бар ма», «детская комната» — the `for_kids` tag or the place's own words, else the
same; `visit` — «is it worth going up at night or in the morning», «стоит ли» — the hours (with today's interval) and the entry price of the
named place, the «night / morning» in it being no time word. A saved place is any bookmark name, said with its «my» or not: «how long to walk
back to my hotel» is a `route` answer from the person to it (the places shown before stay on the map), «something nice to see on my way back to
the hotel» is a search along the way. A message that names its own kind or asks its own question is never the «С ребёнком» refinement (only a
bare «с ребёнком / баламен / а если с детьми» is); «на бегу» is `fast` (food on the go), never running. «Суық емес болса …» / «если не
холодно …» / «if it's not cold …» says whether it is cold at the asked time (the observation, or the MET Norway entry of that hour; cold is a
feels-like of 5 °C or less): not cold — the street as asked; cold — the same request indoors; no temperature in the data — as asked, said so.

Round 3: a weather follow-up with a comparison («а завтра днём будет теплее?», «will it be warmer», «жылырақ па») is the forecast of that
time against the present observation, in degrees («Теплее, чем сейчас, на 4 °C»), never a search; every weather question of a dialogue is
answered. «Щас скучно куда сходить» (bored AND asking where to go; a bare «скучно» is still asked back) is an outing with no café
(`outing.BORED_KINDS`: entertainment, show or film, sight, park, museum; food kinds refused), the afisha block beside it when it has events.
A message of mixed Russian and Kazakh is read by its words (`dialog_nlu.language_votes`: a kazakh letter or function word votes kk, a word only
Russian has votes ru, shared words vote for neither): more words win, a tie goes to the dialogue's (interface) language. For a request with a
later time the conditions (the lead, the cold verdict, the card) are those of THAT time: the MET Norway entry of the hour in place of the present
observation (`dialog_weather.weather_at`), the notices that are in force then; no entry - no temperature is claimed. `answer.at.day` (days ahead
of today, 0 for a pinned demo answer) lets the card say «завтра 10:00–18:00 · завтра 12:00» instead of «сегодня … сейчас».

Round 4: a question about the weather inside a dialogue about a place is still the weather («а на улице щас холодно, мне идти?», «а завтра
дождь будет?»): the weather's own words (`wx_cold / wx_rain / wx_heat / wx_smog`) are the question, not a wish for a place and not the
person's report of the weather. «Сколько стоит вход и есть ли там туалет» answers every part (`PlaceQuestion.also`: the topics of the LATER
parts of the message, split at «и / and / және / ,»): the entry price, the toilet from the record's `toilets` tag or «в данных этого нет».
«До какого часа он работает / until when» (`closing`) is the hours answer of the card (same source): open now - until when; closed now - the
next opening and the closing after it. «Мұнда / бұл жерде …» marks a question about the shown place. A kind a follow-up refuses stays refused
(`Intent.refused`) even when the request never named it. A part of the day or a clock time («вечером», «в 19:00», «at 7 pm») that has gone by
today is moved to tomorrow and the reply says so («Сегодня вечер уже прошёл — подбираю на завтра»); «вечером» in the small hours is the coming
evening, said («Сейчас ночь — беру ближайший вечер»).

Round 5: a message with several parts about the shown place («а до скольки он работает и есть ли розетки и вайфай») is read as up to 16 words
when it asks two topics or more, and «есть» at its end or before «и» marks it a question about the place; «вайфай / wi-fi / wifi / интернет»
is the `wifi` topic, answered apart from `socket` (a record's `socket:*` tags). A request with a child that wanted a playground and got no
play place among the places shown says so before the answer (`dialog_facts.all_gaps`, `kids_none_place`: «Детских площадок и игровых мест
рядом в данных нет …»), never a café or a gallery in the cold passed off as «где поиграть». The comparison of the forecast with now is one
function (`dialog_weather.compare_clause`): each temperature is rounded once, as the answer shows it, and the difference is of those numbers
in every language. «Күндіз» is the afternoon (13:00), as «днём».

Round 6: a message's parts are read in the order they are said (`dialog_questions._asked_topics`: the first topic of each part split at «и / and /
және / ,»), so «сколько стоит вход и до сколько работает» is `entry` then `closing` («до сколько», «қашанға дейін» are the closing time). New
topics: `atm` (only of a place the message points at — «есть ли там банкомат»; «где банкомат» is a search): `amenity=atm` / `atm=yes` or «в данных
этого нет — уточните в отделении»; `exchange` (a question FORM: «меняют ли там доллары», «do they change dollars», «доллар айырбастай ма»):
`amenity=bureau_de_change`, `currency:USD=yes`, an `exchange` tag, else the same honest line; `round_clock` («банкомат круглосуточно»): yes when
the schedule is 24/7, no with the day's interval otherwise. `PlaceQuestion.kind_safe`: a question about a shown place even when its text names a
kind. A child next to an errand kind (pharmacy, money, grocery, lodging, toilet) is the reason, not a wish: `with_kids` is dropped and no kids'
places are offered. A Kazakh message that is only kazakh words ending in the question particle («доллар айырбастай ма») is answered in Kazakh.
Kazakh lead: ««X» барыңыз», «Іздегеніңіз: …».

Friends' feedback: a kind of place our categories cannot represent (`walks/dialog_unmapped.py`: a PS / computer club, hookah, sauna / bath,
karaoke, billiards, bowling, a quest, massage / spa) is said, not swapped: the search runs for the closest represented kind with the kind's
own words as keywords and NO padding (every other category is refused), and the reply starts with «Игровых клубов … в наших данных рядом нет.
Показываю ближайшее по смыслу.» unless a place of the answer carries the kind's own words in its name or tags (`Gap.found_in`). Code, homework, maths
and translation requests (`dialog_scope.off_topic`) get one scope line and no place, unless the message also names a kind, an outing or asks «где /
рядом». A message of steps («… и потом …», `split_refusal`) whose one step is refused (sexual services, now also «массаж с окончанием») is refused in
that step in one sentence and the other steps are answered; a pizza is its own kind (`pizza` concept: keywords «пицца / pizza», so «Додо Пицца» and
`cuisine=pizza` rise). Typos of key place words (`walks/dialog_typos.py`: «кофк», «прак», «паерк»; one edit from exactly one key word, 4+ letters, 5+ in
English, never a word the lexicon already reads or a real word of `REAL_WORDS`; a test runs every word of the dataset's own texts and expects none
mended). «В сторону X по пути» (`walks/dialog_toward.py`, `TurnEnv.geocode` = the stand's local address search) searches along the way to the geocoded
target and says so («Ищу по пути в сторону «…»»); a target that is not found is said and the search is near the start. `TurnEnv` and `Outcome` live in
`walks/dialog_env.py` and are re-exported by `walks.dialog`.

Wave 9 (round 7 of the personas). *Illness is no weather* (`walks/symptoms.py`: `has_symptom`, `sick_who`): «температурит», «жар», «ыстықтап жатыр», «қызуы көтерілді», «заболел», «кашель», «fever» never go to the weather answer (`asks_weather` is False) and never give a weather hint when an errand kind is asked («Өзіңіздің айтуыңызша, ыстық» is gone). A sick person is a clinic / pharmacy wish: `Intent.sick` = `"child"` / `"adult"` (rules only; in `RULES_ONLY_FIELDS` and `generate._WORD_FIELDS`, so the prompt and the cache keys stay as recorded), the child is the reason (`with_kids` dropped, never a playground), no kind named → `clinic` + `pharmacy`; «поликлиника», «педиатр», «терапевт», «балалар емханасы» are clinics, a hospital / in-patient ward / ambulance is honestly missing («нет больниц и скорой помощи») with «при угрозе жизни звоните 103». *Language*: in a kazakh dialogue a close word-vote (the russian side ahead by one word at most) answers in kazakh. *Scope*: jokes, sports results, news, trivia and chit-chat get the scope line that says what the app does, unless the message also asks for a place («where to watch the champions league» → bars with the honest «matches are not marked» line). Unmapped: PS / Xbox / computer clubs. *Areas*: a river or a district («в сторону Есиля», Ишим, Нура, Сарыарка, Байконур, «район Алматы») resolves to the district centre, never to a same-named street. *Weather + what to do*: «а че там с погодой, и чем занимать себя, если дождь» answers the weather and then searches indoors; «если дождь» is a condition, not a report of rain.

The kazakh «бар» is «there is» («туалет бар ма», «қай жерде кафе бар»): the search is for the thing asked about; «бар» is the
bar kind only as a noun («барға барайық», «бар іздеп жүрмін», «pub/bar»). A kind a follow-up refuses («не торговый центр»,
«жоқ, бұл емес… сауда орталығы емес») leaves the request (`FollowUp.drop`, `Intent.refused`); when nothing is left the
turn is `clarify` («что ищем вместо?»).

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
* `Turn.more` — «Ещё N мест рядом» (`walks/dialog_more.py`): on a `places` turn up to **seven** further places of the same
  wish that the answer did not show, **nearest first** by the walking minutes the row says (then metres; the three cards
  are the ranking's pick, the list is read by distance and its label says so), as `Place`s
  built by code only (`place_from_candidate`): the state of the hours at the arrival time is the retrieval's own check
  (the same as a card's), minutes and metres are the retrieval's estimate (`walk.method` is `estimate`), no `why` and no
  `what_to_do` because no model wrote for them. Candidates retrieval padded in (`backfill`, `substituted`) never appear,
  an errand (pharmacy, cash machine, shop, lodging) lists only its own kinds, **confirmed open first** and the nearest
  within each group, a request with `plan_order` has none. `Turn.more_order` is `distance` or `open_first` (`''` with no
  rows): the page's button reads «Ещё N мест рядом — по расстоянию» / «— сначала открытые». It is built after the
  generation step: the model payload and the first three places are unchanged, and `state.shown` is still the three.
* `place_legs` in the page's answer (`web.turns.answer`, beside `turn`, one entry per `turn.places`, then one per `turn.more`, in order): `place_legs[i]` =
  `{minutes, meters, method, shape}`, the way from the turn's origin to that place. The minutes, metres and method are
  the place's `walk` (`valhalla` | `straight` | `estimate`); `shape` is the street line `[[lat, lon], …]` or `null` (the
  map then draws a faint straight line, with «≈» before the minutes). The line comes from the router's cache, or from one
  request to a router of one's own (`WALKS_VALHALLA_URL`, kept in memory); the shared public server is never asked for a line.
  The places of `turn.more` take the cached line only (seven more lookups would slow every answer).
* `at` in the page's answer — `{time: "HH:MM", date: "YYYY-MM-DD"}`, the moment the answer is about (what the day strip
  marks as «сейчас»); `GET /api/config` has `now`, the stand's clock (`YYYY-MM-DDTHH:MM`, the pinned moment in a demo).


## CLI

`python -m walks.cli --dialog [--script file.json] --lat .. --lon .. [--lang ru|kk|en] [--no-llm] [--offline] [--time ..]
[--weather ..] [--no-walking]`: one message per stdin line or a JSON list (`"text"` or `{"say", "lang", "time"}`); one JSON
object per turn: `{"say", "turn", "state"}`.

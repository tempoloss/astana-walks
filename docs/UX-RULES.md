# UI/UX rules for «Анық» — from the owner's own saved design videos

Source: the owner's private knowledge base of saved design videos (items 439, 455, 685–752; the full dump of the ideas
is not part of this repository). Every interface change follows these rules and names the item ids it applied
(e.g. «736: заголовок ×2 к телу»).

## Type (728, 729, 736, 738, 455, 687)
- One type scale, every step deliberate; size + weight + line-height set per role. Never a random size.
- One family. Hierarchy by size, weight and colour, not by extra fonts. No monospace for labels; numbers use
  `font-variant-numeric: tabular-nums` of the main font (693, 694).
- At most three weights: 400 body, 500 labels/buttons, 600 titles.
- No ALL-CAPS micro labels: they slow reading and look dated (455). If a tiny uppercase label must exist, give it
  letter-spacing. Sentence case is the default.
- Body text must not compete with titles. Long text gets a looser line-height and slightly lower contrast (455).
- kk strings are 20–30 % longer: no fixed widths. Use min-width + padding and let the text set the width (687).

## Space and layout (728, 732, 733, 736, 455)
- 4 px base unit: every padding, gap and margin is a multiple of 4.
- One side margin per surface (e.g. 16 px on phone). All content aligns to it.
- Relation by proximity: related items sit closer. Too much space between sections disconnects them (455).
- Double the space around the one important element instead of adding borders or colour (736).

## Dividers, radii, shadows (455, 692, 695)
- Dark or heavy dividers fragment the screen. Use hairlines with low contrast, or no line, and separate by spacing.
- Radius scales with the element: ~4–6 small chips and badges, 8–10 buttons, 12–14 cards, 16+ sheets.
  Pills only for single-line elements. A side touching the screen edge has radius 0. A nested radius is the outer
  radius minus the padding.
- Shadows only on what sits above the page layer: sheet, popover, menu. Not on every card. «Everything floats →
  nothing floats» (692).

## Colour (692, 711, 736, 737, 745)
- One accent, spent only where attention must go: the primary action and the selected item. Everything else neutral.
- No pastel badges, no coloured tiles, no gradients (the «AI slop» look).
- Red only for destructive actions and «закрыто».
- Never colour alone: pair it with an icon or a word.

## Labels and data (455, 693, 694)
- Drop a label when the value explains itself («7 мин», «512 м», a phone number, «500 ₸»). Ambiguous values
  (dates, «данные на …») keep a short label.
- Badges are minimal: 1–2 words, no decorative icons (455).
- Mobile record rows: identity left, the key value in a fixed top-right slot with tabular numerals, state and date on
  the line below (693).
- Missing data is one plain muted word or a dash. Never a decorative pattern: the striped «часы неизвестны» is
  exactly what the owner called «полосатая хуйня» (694: «empty cell → dash»).
- Do not say the same thing twice. «Часы неизвестны» plus «Часов работы нет ни в одном источнике, поэтому пишем
  «неизвестно»» is one fact said twice.

## Detail record (693, 455)
- The full record opens in a bottom sheet on phone. Group by the person's task, not by data fields:
  - now: open / closed, today's hours;
  - getting there: walk, bus;
  - about: why, what to do;
  - contacts;
  - sources, collapsed by default.
- Primary actions stay in a sticky bottom bar (455).

## Search (723) — the address field of «Где вы?»
- The placeholder teaches: concrete examples («Кенесары 40, Хан Шатыр, Мәңгілік Ел»), not «Поиск».
- Recent picks appear on focus; one tap reuses one.
- 3–5 good results beat 10. Each result has a kind badge (дом / улица / место) and its district.
- Full keyboard support: arrows, Enter, Esc, a visible focus ring.
- «Ничего не найдено» is never a dead end: offer «Выбрать на карте» and «Моё местоположение».

## Forms and settings (439, 697/701, 703, 708, 711, 721)
- Group by the person's task. Smart defaults; no empty forms. Hide advanced options behind one tap.
- Toggles apply instantly: flip at once, roll back on error. Heavy text (free text) needs an explicit save.
- Mark changed settings.
- Destructive actions live in one separate zone at the bottom. Their buttons use concrete verbs («Удалить место»),
  and red appears only there.
- Validate on blur, then live; confirm the corrected state.
- No control may do nothing. Every toggle must visibly change what the assistant does.

## Feedback, waiting, AI (685, 691, 705, 726, 730, 751)
- Make it feel fast: the person's message appears instantly.
- If a wait passes ~300 ms, show a skeleton shaped like the coming answer (lead lines + one card). No spinner for
  waits over 3 s. For long waits, honest steps («Понимаю запрос → Ищу места → Проверяю часы → Пишу ответ»).
- No loading flash under 300 ms.
- AI text carries its source; unsourced claims are marked. We already have «Идея ИИ» and source lines — keep them
  compact.

## Touch and gestures (700, 704, 707, 710, 734)
- Nothing important hides behind hover on touch. Use `@media (hover: hover)` for hover-only styles.
- Hit areas ≥ 44 px come from padding, not bigger icons.
- Right-click = long-press: the same menu, grouped by intent, destructive last.
- Hidden gestures need a visible entry point too. A gesture is only a shortcut, so «Добавить место» must be a real
  button.
- Delete with «Вернуть» (undo toast), not a confirm dialog.
- Primary actions sit large and near the thumb (bottom).

## Empty, done, notices (686, 702, 720, 727)
- An empty state has a human sentence, one next action and nothing else.
- After an action, say concretely what happened and offer the next step.
- Toasts: bottom-right on desktop, top on phone. Errors stay until dismissed.

## Icons (688)
- One stroke width everywhere. Outline icons; filled only for the selected state.
- Icon size follows the text: 16 px icon for 14 px text.
- Icon colour = text colour (secondary grey); the accent only when active.

## Motion (709, 724, 728)
- Enter 200–300 ms ease-out, exit 150–200 ms ease-in, feedback < 100 ms.
- Never block input during an animation. Content fades in slower than it fades out.

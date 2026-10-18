// The plate at the top left of the map (desktop): the sections and the time row. The time row sets the time of the next
// search today («сейчас», «через час», «вечером»: all the API takes is a time of today). On a phone the plate is only
// the top bar.

import { h } from './dom.js';
import { onLang, tr } from './i18n.js';

const EVENING = 19 * 60; // «вечером»
let app;
let assistant;
let loadedAt = 0;

const hhmm = (min) => `${String(Math.floor(min / 60)).padStart(2, '0')}:${String(min % 60).padStart(2, '0')}`;

// the stand's clock: the real local time the server gave at load, moving with this tab
function nowMinutes() {
  const [hh, mm] = app.config.now.slice(11, 16).split(':').map(Number);
  return hh * 60 + mm + Math.floor((Date.now() - loadedAt) / 60000);
}

function timeRow() {
  const row = document.getElementById('when');
  const here = assistant.state();
  const now = nowMinutes();
  const hour = now + 60 < 24 * 60 ? hhmm(now + 60) : null;
  const evening = now < EVENING ? hhmm(EVENING) : null;
  const custom = here.at && here.at !== hour && here.at !== evening ? here.at : null;
  const pick = (at) => () => assistant.setAt(at);
  const opt = (label, at, enabled, pressed, extra) =>
    h('button', { type: 'button', 'aria-pressed': String(pressed), disabled: !enabled, onclick: pick(at), dataset: { when: String(at) } }, label, extra);
  row.replaceChildren(
    ...[
      opt(tr('when_now'), null, true, !here.at && !custom, [' · ', h('span', { class: 'tnum', text: hhmm(now % (24 * 60)) })]),
      opt(tr('when_hour'), hour, hour !== null, here.at === hour && hour !== null),
      opt(tr('when_evening'), evening, evening !== null, here.at === evening && evening !== null),
      custom ? opt(tr('when_at', { t: custom }), custom, true, true) : null,
    ].filter(Boolean),
  );
}

export const renderPlate = timeRow;

export function initPlate(ctx, assistantModule) {
  app = ctx;
  assistant = assistantModule;
  loadedAt = Date.now();
  onLang(renderPlate);
  renderPlate();
  setInterval(timeRow, 30000);
}

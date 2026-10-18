// «Память»: what the assistant remembers. The dialogue lives only in this tab. The personal profile is off until the
// user turns it on; then «Запомнить: …?» chips and «Был здесь / Понравилось» fill it, every item can be deleted, and
// «Забыть всё» deletes the file. The browser keeps only the random id of that file (and `?u=<id>` restores it).
// «Изменить вручную» is a form in plain sections (who you are, food, budget, access, the walk, which places) and one
// free text for the AI; the server refuses what contradicts itself, the form does not offer it (a child's age shows
// only next to «с детьми», a kind of place is either liked or left out).

import { api } from './api.js';
import { h, icon } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';

const ON = 'anyq.profile.on';
const ID = 'anyq.profile.id';
const AGE_BANDS = ['0-3', '4-7', '8-12', '13+'];
const LANGUAGE_NAME = { kk: 'қазақша', ru: 'русский', en: 'English' };
let view = { id: null, items: [], form: null, categories: [], about_max: 500 };
let formOpen = false;
let formStatus = ''; // '' | 'saved' | 'failed': the line under the save button

export function on() {
  return localStorage.getItem(ON) === '1';
}

export function id() {
  return localStorage.getItem(ID);
}

function setId(next) {
  if (next) localStorage.setItem(ID, next);
  else localStorage.removeItem(ID);
}

async function refresh() {
  try {
    view = await api.profile(id(), currentLang());
    if (!view.id && id()) setId(null);
  } catch {
    view = { id: id(), items: [], form: null, categories: [], about_max: 500 };
  }
}

export async function act(action) {
  if (action.action !== 'save') formStatus = '';
  try {
    view = await api.profileAction({ id: id(), lang: currentLang(), ...action });
    setId(view.id);
    render();
    return true;
  } catch {
    return false;
  }
}

// ---- the form's controls: a switch, a segmented choice, a chip, a section

function toggleRow(label, checked, onChange) {
  const input = h('input', { type: 'checkbox', role: 'switch', checked: Boolean(checked) });
  input.addEventListener('change', () => onChange(input.checked));
  return h('label', { class: 'mf-toggle' }, h('span', { text: label }), input);
}

// options: [[value, label], …]; the picked one is aria-checked, a tap picks it. `bare`: the section title already is
// the label, so none is drawn (the group keeps it as its accessible name)
function segmented(label, options, current, onPick, { cols = options.length, tpl = '', bare = false } = {}) {
  const buttons = options.map(([value, text]) => {
    const btn = h('button', { type: 'button', role: 'radio', 'aria-checked': String(value === current), text });
    btn.addEventListener('click', () => {
      for (const other of buttons) other.setAttribute('aria-checked', String(other === btn));
      onPick(value);
    });
    return btn;
  });
  return h('div', { class: 'mf-field' }, bare ? null : h('span', { class: 'mf-label', text: label }),
    h('div', { class: 'mf-seg', role: 'radiogroup', 'aria-label': label, style: `--cols:${cols}${tpl ? `;--tpl:${tpl}` : ''}` }, buttons));
}

function section(title, ...kids) {
  return h('fieldset', { class: 'mf-sec' }, h('legend', { text: title }), kids);
}

function kindPickers(draft, categories) {
  const groups = {};
  const paint = () => {
    for (const [group, buttons] of Object.entries(groups)) {
      for (const [key, btn] of buttons) btn.setAttribute('aria-pressed', String(draft[group].includes(key)));
    }
  };
  const pick = (group, other) => (key) => {
    draft[group] = draft[group].includes(key) ? draft[group].filter((k) => k !== key) : [...draft[group], key];
    draft[other] = draft[other].filter((k) => k !== key); // never both liked and left out
    paint();
  };
  const make = (group, other, label) => {
    const choose = pick(group, other);
    groups[group] = categories.map(({ key, name }) => {
      const btn = h('button', { type: 'button', class: 'mf-chip', 'data-kind': group, 'aria-pressed': 'false', text: name });
      btn.addEventListener('click', () => choose(key));
      return [key, btn];
    });
    return h('div', { class: 'mf-field', role: 'group', 'aria-label': label },
      h('span', { class: 'mf-label', text: label }),
      h('div', { class: 'mf-chips' }, groups[group].map(([, btn]) => btn)));
  };
  const liked = make('liked', 'avoid', tr('mf_liked'));
  const avoid = make('avoid', 'liked', tr('mf_avoid'));
  paint();
  return [liked, avoid, h('p', { class: 'fine', text: tr('mf_kinds_hint') })];
}

function aboutField(draft, max) {
  const area = h('textarea', { class: 'mf-about', rows: 4, maxlength: max, placeholder: tr('mf_about_ph'), 'aria-describedby': 'mf-about-note' });
  area.value = draft.about;
  const count = h('span', { class: 'mf-count', 'aria-hidden': 'true' });
  const update = () => {
    draft.about = area.value;
    count.textContent = tr('mf_count', { n: area.value.length, max });
  };
  area.addEventListener('input', update);
  update();
  return [
    h('p', { class: 'fine', text: tr('mf_about_hint') }),
    area,
    h('div', { class: 'mf-note', id: 'mf-about-note' }, icon('info'), h('span', { text: tr('mf_about_note') }), count),
  ];
}

function form() {
  if (!view.form) return null;
  const draft = { ...view.form, liked: [...view.form.liked], avoid: [...view.form.avoid] };
  const ageField = segmented(tr('mf_kids_age'),
    [['', tr('mf_age_none')], ...AGE_BANDS.map((band) => [band, band.replace('-', '–')])],
    draft.kids_age_band || '', (v) => { draft.kids_age_band = v || null; }, { tpl: 'minmax(0, 1.7fr) repeat(4, minmax(0, 1fr))' });
  ageField.hidden = !draft.with_kids;

  const el = h('form', { class: 'mf', novalidate: true },
    h('p', { class: 'fine', text: tr('mf_intro') }),
    section(tr('mf_s_who'),
      toggleRow(tr('mf_kids'), draft.with_kids, (on_) => {
        draft.with_kids = on_;
        if (!on_) draft.kids_age_band = null; // an age without «с детьми» is meaningless: never sent
        ageField.hidden = !on_;
        if (!on_) for (const b of ageField.querySelectorAll('button')) b.setAttribute('aria-checked', String(b.textContent === tr('mf_age_none')));
      }),
      ageField,
      segmented(tr('mf_lang'),
        [['', tr('mf_lang_as_query')], ...Object.entries(LANGUAGE_NAME)], draft.language || '', (v) => { draft.language = v || null; }, { cols: 2 })),
    section(tr('mf_s_food'),
      toggleRow(tr('mf_halal'), draft.halal, (v) => { draft.halal = v; }),
      toggleRow(tr('mf_alc'), draft.no_alcohol, (v) => { draft.no_alcohol = v; })),
    section(tr('mf_s_budget'),
      segmented(tr('mf_s_budget'), ['any', 'low', 'medium', 'high'].map((v) => [v, tr(`mf_b_${v}`)]), draft.budget, (v) => { draft.budget = v; }, { cols: 2, bare: true })),
    section(tr('mf_s_access'),
      segmented(tr('mf_s_access'), ['none', 'stroller', 'wheelchair'].map((v) => [v, tr(`mf_m_${v}`)]), draft.mobility, (v) => { draft.mobility = v; }, { bare: true }),
      h('p', { class: 'fine', text: tr('mf_access_hint') })),
    section(tr('mf_s_walk'),
      toggleRow(tr('mf_quiet'), draft.quiet, (v) => { draft.quiet = v; }),
      segmented(tr('mf_pace'), ['slow', 'normal', 'fast'].map((v) => [v, tr(`mf_p_${v}`)]), draft.walk_pace, (v) => { draft.walk_pace = v; }),
      segmented(tr('mf_cold'), ['low', 'normal', 'high'].map((v) => [v, tr(`mf_c_${v}`)]), draft.cold_tolerance, (v) => { draft.cold_tolerance = v; })),
    section(tr('mf_s_kinds'), kindPickers(draft, view.categories)),
    section(tr('mf_s_about'), aboutField(draft, view.about_max)),
    h('div', { class: 'mf-actions' },
      h('button', { type: 'submit', class: 'primary-btn', text: tr('mf_save') }),
      h('span', { class: 'mf-status', role: 'status', 'data-state': formStatus, text: formStatus ? tr(formStatus === 'saved' ? 'mf_saved' : 'mf_save_fail') : '' })),
  );
  el.addEventListener('submit', async (e) => {
    e.preventDefault();
    formStatus = (await act({ action: 'save', form: draft })) ? 'saved' : 'failed';
    // a failed save keeps the page (and what was typed); a saved one has just been redrawn from the stored form
    const status = document.querySelector('#memory-root .mf-status');
    status?.setAttribute('data-state', formStatus);
    status?.replaceChildren(tr(formStatus === 'saved' ? 'mf_saved' : 'mf_save_fail'));
  });
  const box = h('details', { class: 'disclosure mf-box', open: formOpen }, h('summary', {}, h('span', { text: tr('panel_edit') }), icon('chevron')), el);
  box.addEventListener('toggle', () => { formOpen = box.open; });
  return box;
}

function render() {
  const root = document.getElementById('memory-root');
  const enabled = on();
  const toggle = h('input', { type: 'checkbox', role: 'switch', checked: enabled, id: 'mem-toggle' });
  toggle.addEventListener('change', () => {
    localStorage.setItem(ON, toggle.checked ? '1' : '0');
    render();
  });
  const items = view.items.length
    ? h('ul', { class: 'mem-items' }, view.items.map((item) =>
      h('li', {}, h('span', { text: item.label }),
        h('button', { type: 'button', class: 'ghost icon', 'aria-label': tr('mem_forget_item', { item: item.label }), onclick: () => act({ action: 'forget', key: item.key }) }, icon('close')))))
    : h('p', { class: 'fine', text: tr('panel_empty') });
  root.replaceChildren(
    h('header', {}, h('h2', { text: tr('mem_title') }),
      h('button', { type: 'button', class: 'ghost icon', 'aria-label': tr('close'), onclick: () => document.getElementById('memory').close() }, icon('close'))),
    h('p', { class: 'fine', text: tr('mem_dialog_note') }),
    h('label', { class: 'mf-toggle mf-master', for: 'mem-toggle' }, h('span', { text: tr('side_remember') }), toggle),
    h('p', { class: 'fine', text: tr('mem_why') }),
    enabled ? h('div', { class: 'section' }, h('h2', { text: tr('mem_known') }), items, form(),
      view.id ? h('button', { type: 'button', class: 'secondary mf-forget', onclick: () => act({ action: 'forget_all' }) }, tr('mem_forget_all')) : null)
      : h('p', { class: 'fine', text: tr('mem_off') }),
    h('p', { class: 'fine', text: tr('mem_marks_note') }),
  );
}

export async function open() {
  await refresh();
  formOpen = view.items.length === 0; // nothing stored yet: the form is what the person came for
  formStatus = '';
  render();
  document.getElementById('memory').showModal();
}

export async function initMemory() {
  const shared = new URLSearchParams(location.search).get('u');
  if (shared && /^[0-9a-f-]{36}$/.test(shared)) {
    setId(shared);
    localStorage.setItem(ON, '1');
  }
  for (const btn of document.querySelectorAll('.memory-open')) btn.addEventListener('click', open);
  const dialog = document.getElementById('memory');
  dialog.addEventListener('click', (e) => {
    if (e.target === dialog) dialog.close();
  });
  onLang(async () => {
    if (dialog.open) {
      await refresh();
      render();
    }
  });
}

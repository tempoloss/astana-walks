// «Память»: what the assistant remembers. The dialogue lives only in this tab. The personal profile is off until the
// user turns it on; then «Запомнить: …?» chips and «Был здесь / Понравилось» fill it, every item can be deleted, and
// «Забыть всё» deletes the file. The browser keeps only the random id of that file (and `?u=<id>` restores it).
// «Изменить вручную» is a form in plain sections (who you are, food, budget, access, the walk, which places) and one
// free text for the AI. Every switch, choice and chip applies at once (flipped on the screen first, rolled back with a
// short line when the server refuses); only the free text has a «Сохранить» of its own. The server refuses what
// contradicts itself, the form does not offer it (a child's age shows only next to «с детьми», a kind of place is
// either liked or left out).

import { api } from './api.js';
import { h, icon } from './dom.js';
import { currentLang, onLang, tr } from './i18n.js';
import { placesSection } from './places-panel.js';

const ON = 'anyq.profile.on';
const ID = 'anyq.profile.id';
const AGE_BANDS = ['0-3', '4-7', '8-12', '13+'];
const LANGUAGE_NAME = { kk: 'қазақша', ru: 'русский', en: 'English' };
let view = { id: null, items: [], form: null, categories: [], about_max: 500 };
let formOpen = false;
let draft = null; // the form's values on screen (what the controls show right now)
let typedAbout = null; // the free text as typed and not yet saved: it survives a redraw
let queue = Promise.resolve(); // the saves, one after another: each sends the form as it is when its turn comes
let statusTimer = 0;

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
  try {
    view = await api.profileAction({ id: id(), lang: currentLang(), ...action });
    setId(view.id);
    render();
    return true;
  } catch {
    return false;
  }
}

// ---- instant saving of the form

// «Сохранено» / «Не удалось сохранить»: one small line at the top of the form, the first one fades away by itself
function flash(state) {
  clearTimeout(statusTimer);
  const el = document.querySelector('#memory-root .mf-status');
  if (!el) return;
  el.dataset.state = state;
  el.textContent = tr(state === 'saved' ? 'mf_saved' : 'mf_save_fail');
  if (state === 'saved') {
    statusTimer = setTimeout(() => {
      el.dataset.state = '';
      el.textContent = '';
    }, 2000);
  }
}

// the stored list of «what I know about you» follows the form (the form's switches are some of its lines)
function paintItems() {
  const box = document.getElementById('mem-items-box');
  if (box) box.replaceChildren(itemsList());
}

// Save the form as it is on the screen. `about`: the free text to store (the stored one stays when a switch is flipped).
// The first setting ever flipped creates the profile and turns «Запоминать мои предпочтения» on. A refusal puts the
// screen back to what is stored and says so. Resolves to whether it was stored.
function commit(about) {
  const run = async () => {
    const form = { ...draft, about: about ?? view.form.about };
    try {
      view = await api.profileAction({ id: id(), lang: currentLang(), action: 'save', form });
      setId(view.id);
    } catch {
      render(); // from what is stored (the typed text stays in its field)
      flash('failed');
      return false;
    }
    if (about !== undefined) typedAbout = null;
    if (!on()) {
      localStorage.setItem(ON, '1');
      render();
    } else {
      paintItems();
    }
    flash('saved');
    return true;
  };
  queue = queue.then(run, run);
  return queue;
}

function itemsList() {
  return view.items.length
    ? h('ul', { class: 'mem-items' }, view.items.map((item) =>
      h('li', {}, h('span', { text: item.label }),
        h('button', { type: 'button', class: 'ghost icon', 'aria-label': tr('mem_forget_item', { item: item.label }), onclick: () => act({ action: 'forget', key: item.key }) }, icon('close')))))
    : h('p', { class: 'fine', text: tr('panel_empty') });
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

function kindPickers(categories) {
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
    commit();
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

// the free text: the one part of the form that is saved by its own button (a half-typed sentence is not a setting)
function aboutField(max) {
  const area = h('textarea', { class: 'mf-about', rows: 4, maxlength: max, placeholder: tr('mf_about_ph'), 'aria-describedby': 'mf-about-note' });
  area.value = typedAbout ?? view.form.about;
  const count = h('span', { class: 'mf-count', 'aria-hidden': 'true' });
  const save = h('button', { type: 'button', class: 'secondary mf-about-save', text: tr('mf_save') });
  const update = () => {
    count.textContent = tr('mf_count', { n: area.value.length, max });
    save.disabled = area.value === view.form.about;
  };
  area.addEventListener('input', () => {
    typedAbout = area.value;
    update();
  });
  save.addEventListener('click', async () => {
    save.disabled = true;
    if (await commit(area.value)) update();
  });
  update();
  return [
    h('p', { class: 'fine', text: tr('mf_about_hint') }),
    area,
    h('div', { class: 'mf-note', id: 'mf-about-note' }, icon('info'), h('span', { text: tr('mf_about_note') }), count),
    save,
  ];
}

function form() {
  if (!view.form) return null;
  draft = { ...view.form, liked: [...view.form.liked], avoid: [...view.form.avoid] };
  const set = (key) => (v) => {
    draft[key] = v;
    commit();
  };
  const ageField = segmented(tr('mf_kids_age'),
    [['', tr('mf_age_none')], ...AGE_BANDS.map((band) => [band, band.replace('-', '–')])],
    draft.kids_age_band || '', (v) => set('kids_age_band')(v || null), { tpl: 'minmax(0, 1.7fr) repeat(4, minmax(0, 1fr))' });
  ageField.hidden = !draft.with_kids;

  const el = h('form', { class: 'mf', novalidate: true },
    h('p', { class: 'mf-status', role: 'status', 'data-state': '' }),
    h('p', { class: 'fine', text: tr('mf_intro') }),
    section(tr('mf_s_who'),
      toggleRow(tr('mf_kids'), draft.with_kids, (on_) => {
        draft.with_kids = on_;
        if (!on_) draft.kids_age_band = null; // an age without «с детьми» is meaningless: never sent
        ageField.hidden = !on_;
        if (!on_) for (const b of ageField.querySelectorAll('button')) b.setAttribute('aria-checked', String(b.textContent === tr('mf_age_none')));
        commit();
      }),
      ageField,
      segmented(tr('mf_lang'),
        [['', tr('mf_lang_as_query')], ...Object.entries(LANGUAGE_NAME)], draft.language || '', (v) => set('language')(v || null), { cols: 2 })),
    section(tr('mf_s_food'),
      toggleRow(tr('mf_halal'), draft.halal, set('halal')),
      toggleRow(tr('mf_alc'), draft.no_alcohol, set('no_alcohol'))),
    section(tr('mf_s_budget'),
      segmented(tr('mf_s_budget'), ['any', 'low'].map((v) => [v, tr(`mf_b_${v}`)]), draft.budget, set('budget'), { cols: 2, bare: true })),
    section(tr('mf_s_access'),
      segmented(tr('mf_s_access'), ['none', 'stroller', 'wheelchair'].map((v) => [v, tr(`mf_m_${v}`)]), draft.mobility, set('mobility'), { bare: true }),
      h('p', { class: 'fine', text: tr('mf_access_hint') })),
    section(tr('mf_s_walk'),
      toggleRow(tr('mf_quiet'), draft.quiet, set('quiet')),
      segmented(tr('mf_pace'), ['slow', 'normal', 'fast'].map((v) => [v, tr(`mf_p_${v}`)]), draft.walk_pace, set('walk_pace')),
      segmented(tr('mf_cold'), ['low', 'normal', 'high'].map((v) => [v, tr(`mf_c_${v}`)]), draft.cold_tolerance, set('cold_tolerance'))),
    section(tr('mf_s_kinds'), kindPickers(view.categories)),
    section(tr('mf_s_about'), aboutField(view.about_max)),
  );
  el.addEventListener('submit', (e) => e.preventDefault());
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
  const forms = form(); // the settings are always on offer: flipping one turns the memory on
  root.replaceChildren(
    h('header', {}, h('h2', { text: tr('mem_title') }),
      h('button', { type: 'button', class: 'ghost icon', 'aria-label': tr('close'), onclick: () => document.getElementById('memory').close() }, icon('close'))),
    placesSection(),
    h('p', { class: 'fine', text: tr('mem_dialog_note') }),
    h('label', { class: 'mf-toggle mf-master', for: 'mem-toggle' }, h('span', { text: tr('side_remember') }), toggle),
    h('p', { class: 'fine', text: tr('mem_why') }),
    enabled ? h('div', { class: 'section' }, h('h2', { text: tr('mem_known') }), h('div', { id: 'mem-items-box' }, itemsList()), forms,
      view.id ? h('button', { type: 'button', class: 'secondary mf-forget', onclick: () => act({ action: 'forget_all' }) }, tr('mem_forget_all')) : null)
      : h('div', { class: 'section' }, h('p', { class: 'fine', text: tr('mem_off') }), forms),
    h('p', { class: 'fine', text: tr('mem_marks_note') }),
  );
}

export async function open() {
  await refresh();
  formOpen = view.items.length === 0; // nothing stored yet: the form is what the person came for
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

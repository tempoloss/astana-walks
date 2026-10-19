// «Мой вайб» (walks.vibe): the introvert ↔ extrovert choice and the facet chips apply at once, like every switch of
// «Память»; the free text is read into facets on its own «Сохранить» (a model, else a word list: walks.vibe_judge) and
// the choice and the chips then show what was read. «Искать под мой вайб» closes the panel and asks. The first-screen
// chip «Под мой вайб» asks at once when a vibe is set, and opens this block with one sentence why when none is.

import { h } from './dom.js';
import { tr } from './i18n.js';

const AXIS = ['calm', 'lively'];
let search = null; // (text) => a new search with that text: set by the first-screen chip
let typed = null; // the free text as typed and not yet saved: it survives a redraw

// ctx: {draft(), view(), commit(about, vibeText) -> Promise<bool>, why, close()}
export function vibeSection(ctx) {
  const view = ctx.view();
  const facets = view.vibe_facets || [];
  const names = Object.fromEntries(facets.map((f) => [f.key, f.name.toLowerCase()]));
  const setVibe = (vibe) => {
    ctx.draft().vibe = vibe;
    paint();
    ctx.commit();
  };
  const axisButtons = [['calm', 'vb_axis_calm'], ['', 'vb_axis_any'], ['lively', 'vb_axis_lively']].map(([pole, key]) =>
    h('button', {
      type: 'button',
      role: 'radio',
      dataset: { pole },
      text: tr(key),
      onclick: () => {
        const { calm: _c, lively: _l, ...rest } = ctx.draft().vibe;
        setVibe(pole ? { ...rest, [pole]: 1 } : rest);
      },
    }));
  const chips = facets.filter((f) => !AXIS.includes(f.key)).map(({ key, name }) =>
    h('button', {
      type: 'button',
      class: 'mf-chip',
      dataset: { facet: key },
      text: name,
      onclick: () => {
        const { [key]: had, ...rest } = ctx.draft().vibe;
        setVibe(had ? rest : { ...rest, [key]: 1 });
      },
    }));
  const area = h('textarea', { class: 'mf-about vb-text', id: 'vb-text', rows: 3, maxlength: view.vibe_text_max, placeholder: tr('vb_ph') });
  area.value = typed ?? view.form.vibe_text;
  const save = h('button', { type: 'button', class: 'secondary mf-about-save vb-save', text: tr('vb_save') });
  const read = h('p', { class: 'vb-read', role: 'status' });
  const go = h('button', { type: 'button', class: 'primary-btn vb-go', text: tr('vb_go'), onclick: () => {
    ctx.close();
    if (search) search(tr('sug_vibe_q'));
  } });
  function paint() {
    const vibe = ctx.draft().vibe;
    const pole = vibe.calm && !vibe.lively ? 'calm' : vibe.lively && !vibe.calm ? 'lively' : '';
    for (const b of axisButtons) b.setAttribute('aria-checked', String(b.dataset.pole === pole));
    for (const b of chips) b.setAttribute('aria-pressed', String(Boolean(vibe[b.dataset.facet])));
    go.hidden = !search || !Object.keys(vibe).length;
  }
  const update = () => {
    save.disabled = !area.value.trim() || area.value === ctx.view().form.vibe_text;
  };
  area.addEventListener('input', () => {
    typed = area.value;
    update();
  });
  save.addEventListener('click', async () => {
    save.disabled = true;
    save.textContent = tr('vb_reading');
    const ok = await ctx.commit(undefined, area.value);
    save.textContent = tr('vb_save');
    if (ok) {
      typed = null;
      const got = facets.map((f) => f.key).filter((k) => ctx.view().form.vibe[k]);
      ctx.draft().vibe = { ...ctx.view().form.vibe };
      paint();
      read.textContent = got.length ? tr('vb_read', { facets: got.map((k) => names[k]).join(', ') }) : tr('vb_read_none');
    }
    update();
  });
  paint();
  update();
  return h('fieldset', { class: 'mf-sec vb', id: 'vibe-sec' },
    h('legend', { text: tr('vb_title') }),
    ctx.why ? h('p', { class: 'vb-why', text: tr('vb_why') }) : null,
    h('p', { class: 'fine', text: tr('vb_intro') }),
    h('div', { class: 'mf-field' },
      h('span', { class: 'mf-label', text: tr('vb_axis') }),
      h('div', { class: 'mf-seg', role: 'radiogroup', 'aria-label': tr('vb_axis'), style: '--cols:3' }, axisButtons)),
    h('div', { class: 'mf-field', role: 'group', 'aria-label': tr('vb_likes') },
      h('span', { class: 'mf-label', text: tr('vb_likes') }),
      h('div', { class: 'mf-chips' }, chips)),
    h('div', { class: 'mf-field' },
      h('label', { class: 'mf-label', for: 'vb-text', text: tr('vb_text') }),
      area,
      h('p', { class: 'fine', text: tr('vb_note') }),
      h('p', { class: 'fine vb-on', text: tr('vb_on') })),
    save,
    read,
    go,
  );
}

// The first-screen chip «Под мой вайб», first among the examples (drawn again whenever the examples are: a new language)
export function mountVibeChip(memory, onSearch) {
  search = onSearch;
  const box = document.getElementById('starters');
  const chip = () => h('button', {
    type: 'button',
    class: 'chip',
    title: tr('sug_vibe_q'),
    dataset: { suggest: 'vibe' },
    onclick: async () => {
      if (await memory.hasVibe()) onSearch(tr('sug_vibe_q'));
      else memory.openVibe();
    },
  }, tr('sug_vibe'));
  const ensure = () => {
    if (!box.querySelector('[data-suggest="vibe"]')) box.prepend(chip());
  };
  new MutationObserver(ensure).observe(box, { childList: true });
  ensure();
}

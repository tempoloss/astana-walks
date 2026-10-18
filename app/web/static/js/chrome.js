// What the page's own panels cover of the map, measured from the real boxes (plate, panel, legend) and handed to the
// map, which keeps every fit inside the free area. Called on every render and on every resize of those boxes.
// On a phone the sheet is the one thing that moves: the camera keeps clear of its snapped height (and of the keyboard),
// and the map's credits line rides on the sheet's top edge.

import { isPhone } from './dom.js';
import * as mapView from './map.js';
import { keyboardHeight } from './viewport.js';

const EDGE = 24; // the gap between a fitted place and a panel
const LABEL_PX = 100; // a place's name sits to the right of its pin
const BAR_GAP = 8; // from the top bar to the first thing the map shows
const SIDE_GAP = 12; // a pin's 44px button stays on the screen with the label beside it
const HANDLE_ZONE = 20; // the handle's hit area reaches above the sheet: a pin keeps clear of it
const FULL_FROM = 240; // a sheet this high leaves no map to credit: the credits stand at the end of its list
let sheets = {}; // the phone's bottom sheets by the panel's id (their snapped height is what each is about to cover)

const $ = (id) => document.getElementById(id);

function visiblePanel() {
  for (const id of ['view-assistant', 'view-city']) {
    const el = $(id);
    if (!el.hidden) return el;
  }
  return null;
}

// «© OpenStreetMap · © OpenMapTiles · OpenFreeMap»; without the basemap only what is drawn: the OpenStreetMap places
function creditsLine() {
  return mapView.basemapKind() === 'online' ? '© OpenStreetMap · © OpenMapTiles · OpenFreeMap' : '© OpenStreetMap';
}

function phoneChrome(map, panel) {
  const sheet = panel && sheets[panel.id];
  const lifted = (sheet ? sheet.height() : 0) + keyboardHeight();
  const root = document.documentElement;
  root.style.setProperty('--sheet-h', `${lifted}px`);
  const attr = $('map-attr');
  attr.textContent = creditsLine();
  attr.classList.toggle('off', !panel || window.innerHeight - lifted < FULL_FROM);
  if (sheet && sheet.state === 'full' && !sheet.typing) return; // a full sheet covers the map: no fit follows it
  let bar = $('plate').getBoundingClientRect().bottom;
  const note = $('map-note');
  if (!note.hidden) bar = Math.max(bar, note.getBoundingClientRect().bottom);
  mapView.setChromePadding({
    top: Math.max(bar - map.top, 0) + BAR_GAP,
    left: SIDE_GAP,
    right: SIDE_GAP,
    bottom: lifted + HANDLE_ZONE,
  });
  $('map').style.removeProperty('--map-zoom-right');
}

export function updateChrome() {
  const map = $('map').getBoundingClientRect();
  const panel = visiblePanel();
  if (isPhone()) {
    phoneChrome(map, panel);
    return;
  }
  const plate = $('plate').getBoundingClientRect();
  const legend = $('legend').getBoundingClientRect();
  const box = panel ? panel.getBoundingClientRect() : null;
  mapView.setChromePadding({
    top: Math.max(plate.bottom - map.top, 0) + 16,
    left: EDGE,
    right: (box ? map.right - box.left : 0) + EDGE + (box ? LABEL_PX : 0),
    bottom: Math.max(map.bottom - legend.top, 0) + 12,
  });
  // the zoom buttons sit in the corner while the panel is low, and beside it once the panel reaches them
  const tall = box && box.top - map.top < 72;
  $('map').style.setProperty('--map-zoom-right', tall ? `${map.right - box.left + 12}px` : '12px');
}

// byId: {panel id: sheet}
export function initChrome(byId) {
  sheets = byId;
  const watch = new ResizeObserver(() => updateChrome());
  for (const id of ['plate', 'view-assistant', 'view-city', 'legend', 'map-note']) watch.observe($(id));
  window.addEventListener('resize', updateChrome);
}

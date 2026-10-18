// The basemap: the OpenFreeMap «positron» style recoloured to the page's tokens by paint properties (a near-white,
// monochrome map where the places and the route carry the only colour), its icons and house numbers hidden, its
// labels in the interface language. Also the plain style used without the network, and the attribution lines.

export const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
export const TILE_SOURCE = 'openmaptiles';
export const STYLE_TIMEOUT_MS = 4000;

export const PAL = {
  bg: '#f6f7f9', water: '#dde4ec', park: '#e9eee9', wood: '#e6ebe6', building: '#eceef2', buildingLine: '#e1e4e9',
  road: '#ffffff', casing: '#dfe2e8', path: '#e3e6eb', rail: '#d8dce3', boundary: '#cdd2da', aero: '#eceef2',
  label: '#8a919e', roadLabel: '#9aa1ad', halo: '#f6f7f9', district: '#eff1f4', districtLine: 'rgba(16, 24, 40, 0.22)',
};

const HIDDEN = /shield|airport|poi|housenumber/;
const LABEL_ZOOM_MAX = 12.5; // the big place names (city, state, country) fade out when the map is street-sized

function recolourLayer(layer) {
  const { id, type } = layer;
  const paint = (layer.paint ||= {});
  if (type === 'background') paint['background-color'] = PAL.bg;
  else if (type === 'fill') {
    if (id === 'water') paint['fill-color'] = PAL.water;
    else if (id === 'park') paint['fill-color'] = PAL.park;
    else if (/wood/.test(id)) paint['fill-color'] = PAL.wood;
    else if (/ice|glacier|residential|pier/.test(id)) paint['fill-color'] = PAL.bg;
    else if (id === 'building') {
      paint['fill-color'] = PAL.building;
      paint['fill-outline-color'] = PAL.buildingLine;
    } else if (/aeroway/.test(id)) paint['fill-color'] = PAL.aero;
    else if (/landuse|landcover/.test(id)) paint['fill-color'] = PAL.park;
  } else if (type === 'line') {
    if (/waterway/.test(id)) paint['line-color'] = PAL.water;
    else if (/casing/.test(id)) paint['line-color'] = PAL.casing;
    else if (/highway_path|road_pier/.test(id)) paint['line-color'] = PAL.path;
    else if (/highway|tunnel/.test(id)) paint['line-color'] = PAL.road;
    else if (/railway/.test(id)) paint['line-color'] = PAL.rail;
    else if (/boundary/.test(id)) paint['line-color'] = PAL.boundary;
    else if (/aeroway/.test(id)) paint['line-color'] = PAL.aero;
  } else if (type === 'symbol') {
    paint['text-color'] = /highway/.test(id) ? PAL.roadLabel : PAL.label;
    paint['text-halo-color'] = PAL.halo;
    paint['text-halo-width'] = 1.4;
    if (/^label_(city|town|state|country)/.test(id)) layer.maxzoom = Math.min(layer.maxzoom ?? 24, LABEL_ZOOM_MAX);
  }
}

export function recolour(style) {
  for (const layer of style.layers) {
    if (HIDDEN.test(layer.id)) {
      (layer.layout ||= {}).visibility = 'none';
      continue;
    }
    recolourLayer(layer);
  }
  return style;
}

// The name a label shows: in the interface language where OpenStreetMap has it, else the local name.
export function nameField(lang) {
  if (lang === 'en') return ['coalesce', ['get', 'name_en'], ['get', 'name:latin'], ['get', 'name']];
  return ['coalesce', ['get', `name:${lang}`], ['get', 'name']];
}

// Only symbol layers whose text-field already reads a name: road shields and refs keep their own expressions.
export function labelLayerIds(layers) {
  return layers
    .filter((l) => l.type === 'symbol' && l.layout && l.layout['text-field'] !== undefined && JSON.stringify(l.layout['text-field']).includes('"name'))
    .map((l) => l.id);
}

export function relabel(map, lang) {
  for (const id of labelLayerIds(map.getStyle().layers)) map.setLayoutProperty(id, 'text-field', nameField(lang));
}

// null when the style cannot be had in a few seconds (no network): the map is then the plain local style.
export async function onlineStyle(lang) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), STYLE_TIMEOUT_MS);
  try {
    const res = await fetch(STYLE_URL, { signal: ctl.signal });
    if (!res.ok) return null;
    const style = recolour(await res.json());
    for (const l of style.layers) {
      if (labelLayerIds([l]).length) l.layout['text-field'] = nameField(lang);
    }
    return style;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

export const DISTRICT_LAYERS = [
  { id: 'districts-fill', type: 'fill', source: 'districts', paint: { 'fill-color': PAL.district } },
  { id: 'districts-line', type: 'line', source: 'districts', paint: { 'line-color': PAL.districtLine, 'line-width': 1 } },
];

// Without the basemap: a neutral background and the district outlines served by our own server.
export function localStyle() {
  return {
    version: 8,
    sources: { districts: { type: 'geojson', data: '/api/districts' } },
    layers: [{ id: 'background', type: 'background', paint: { 'background-color': PAL.bg } }, ...DISTRICT_LAYERS],
  };
}

const OSM = 'https://www.openstreetmap.org/copyright';
const CONTRIBUTORS = {
  kk: '© OpenStreetMap қатысушылары',
  ru: '© участники OpenStreetMap',
  en: '© OpenStreetMap contributors',
};

// What the legend row names under the map: the basemap's makers (online) and the OpenStreetMap data (ODbL) either way.
export function attributionLines(lang, kind) {
  const osm = [
    { text: CONTRIBUTORS[lang] || CONTRIBUTORS.en, href: OSM },
    { text: 'ODbL', href: 'https://opendatacommons.org/licenses/odbl/1-0/' },
  ];
  if (kind !== 'online') return osm;
  return [
    { text: 'OpenFreeMap', href: 'https://openfreemap.org' },
    { text: '© OpenMapTiles', href: 'https://openmaptiles.org/' },
    ...osm,
  ];
}

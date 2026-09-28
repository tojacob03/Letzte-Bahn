/* Letzte Bahn – helpers shared by all pages. Plain JavaScript, no build step. */
(function () {
  'use strict';

  // Data lives next to the page. For previews, a trusted data URL can be passed as ?data=
  const DATA_DIR = (() => {
    const override = new URLSearchParams(window.location.search).get('data');
    const trusted = [
      'https://raw.githack.com/tojacob03/Letzte-Bahn/',
      'https://cdn.jsdelivr.net/gh/tojacob03/Letzte-Bahn@',
    ];
    if (override && trusted.some((prefix) => override.startsWith(prefix))) {
      return override.endsWith('/') ? override : `${override}/`;
    }
    return 'data/';
  })();

  const nf0 = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const pct0 = new Intl.NumberFormat('de-DE', { style: 'percent', maximumFractionDigits: 0 });
  const dateLong = new Intl.DateTimeFormat('de-DE', { day: 'numeric', month: 'long', year: 'numeric' });

  // One night-blue ramp for every map metric: light = well connected, dark = poorly
  // connected ("je dunkler, desto abgehängter"). WORST = not reachable in the time limit.
  const RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95'];
  const WORST = '#0d366b';
  const FIRST_DARK_CLASS = 3;

  const SCALES = {
    time: {
      stops: [15, 30, 45, 60, 90],
      higherIsBetter: false,
      labels: ['bis 15 Min.', '16–30 Min.', '31–45 Min.', '46–60 Min.', '61–90 Min.', '91–120 Min.'],
      worst: 'länger als 2 Std. oder gar nicht',
    },
    population: {
      stops: [5000, 20000, 50000, 100000, 250000],
      higherIsBetter: true,
      labels: ['mehr als 250.000', '100.001–250.000', '50.001–100.000', '20.001–50.000',
        '5.001–20.000', 'bis 5.000'],
      worst: null,
    },
    ratio: {
      stops: [1.5, 2, 3, 4, 6],
      higherIsBetter: false,
      labels: ['bis 1,5-mal', '1,5- bis 2-mal', '2- bis 3-mal', '3- bis 4-mal', '4- bis 6-mal',
        'mehr als 6-mal'],
      worst: 'mit Bus und Bahn nicht in 2 Std.',
    },
    share: {
      stops: [0.1, 0.2, 0.4, 0.6, 0.8],
      higherIsBetter: true,
      labels: ['mehr als 80 %', '61–80 %', '41–60 %', '21–40 %', '11–20 %', 'bis 10 %'],
      worst: null,
    },
  };

  let maxTripMinutes = 120;

  function setMeta(meta) {
    maxTripMinutes = (meta.routing && meta.routing.max_trip_minutes) || 120;
  }

  async function getJSON(name, options = {}) {
    const response = await fetch(DATA_DIR + name, { cache: 'no-cache' });
    if (!response.ok) {
      if (options.optional) return null;
      throw new Error(`${name} konnte nicht geladen werden (HTTP ${response.status}).`);
    }
    return response.json();
  }

  function classOf(scale, value) {
    if (value === null || value === undefined || Number.isNaN(value)) return null;
    let index = 0;
    while (index < scale.stops.length && value > scale.stops[index]) index += 1;
    return scale.higherIsBetter ? scale.stops.length - index : index;
  }

  function colorOf(scale, value) {
    const index = classOf(scale, value);
    return index === null ? WORST : RAMP[index];
  }

  // MapLibre expression that mirrors classOf(); missing values get the WORST colour.
  function colorExpression(scale, key) {
    const value = ['to-number', ['get', key], 0];
    const expression = ['case', ['==', ['get', key], null], WORST];
    scale.stops.forEach((stop, index) => {
      const cls = scale.higherIsBetter ? scale.stops.length - index : index;
      expression.push(['<=', value, stop], RAMP[cls]);
    });
    expression.push(RAMP[scale.higherIsBetter ? 0 : scale.stops.length]);
    return expression;
  }

  function formatValue(kind, value) {
    const missing = value === null || value === undefined || Number.isNaN(value);
    if (kind === 'time') {
      return missing ? `über ${nf0.format(maxTripMinutes / 60)} Std.` : `${nf0.format(value)} Min.`;
    }
    if (kind === 'ratio') return missing ? 'nicht erreichbar' : `${nf1.format(value)}-mal`;
    if (kind === 'share') return missing ? '–' : pct0.format(value);
    if (kind === 'population') return missing ? '–' : nf0.format(value);
    return missing ? '–' : String(value);
  }

  function formatNumber(value) {
    return value === null || value === undefined ? '–' : nf0.format(value);
  }

  function formatShare(value) {
    return value === null || value === undefined ? '–' : pct0.format(value);
  }

  function formatDecimal(value) {
    return value === null || value === undefined ? '–' : nf1.format(value);
  }

  function formatDate(value) {
    if (!value) return '–';
    const date = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T12:00:00`) : new Date(value);
    return Number.isNaN(date.getTime()) ? value : dateLong.format(date);
  }

  function metricCatalog(meta) {
    const metrics = [];
    for (const category of meta.categories) {
      metrics.push({
        id: `t:${category.id}`,
        group: 'Reisezeit zum nächsten Ziel',
        label: category.label,
        kind: 'time',
        category: category.id,
        key: (windowId) => `t_${windowId}_${category.id}`,
        carKey: `c_${category.id}`,
      });
    }
    for (const threshold of meta.thresholds) {
      metrics.push({
        id: `p:${threshold}`,
        group: 'Menschen in Reichweite',
        label: `in ${threshold} Minuten`,
        kind: 'population',
        threshold,
        key: (windowId) => `p${threshold}_${windowId}`,
        carKey: `pc${threshold}`,
      });
    }
    for (const category of meta.categories) {
      metrics.push({
        id: `r:${category.id}`,
        group: 'Bus und Bahn im Vergleich zum Auto',
        label: category.label,
        kind: 'ratio',
        category: category.id,
        key: (windowId) => `r_${windowId}_${category.id}`,
        carKey: null,
      });
    }
    return metrics;
  }

  function describe(metric) {
    if (metric.kind === 'time') return `Reisezeit zum nächsten Ziel: ${metric.label}`;
    if (metric.kind === 'population') return `Menschen, die man ${metric.label} erreicht`;
    return `${metric.label}: wie viel länger als mit dem Auto`;
  }

  function windowLabel(meta, windowId) {
    const found = meta.windows.find((slot) => slot.id === windowId);
    return found ? found.label : windowId;
  }

  function el(tag, attributes = {}, children = []) {
    return build(document.createElement(tag), attributes, children);
  }

  function svg(tag, attributes = {}, children = []) {
    return build(document.createElementNS('http://www.w3.org/2000/svg', tag), attributes, children);
  }

  function build(node, attributes, children) {
    for (const [key, value] of Object.entries(attributes)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'class') node.setAttribute('class', value);
      else if (key === 'text') node.textContent = value;
      else if (key.startsWith('on') && typeof value === 'function') {
        node.addEventListener(key.slice(2), value);
      } else node.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of [].concat(children)) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }

  function bounds(geojson) {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    const visit = (coordinates) => {
      if (typeof coordinates[0] === 'number') {
        const [x, y] = coordinates;
        minX = Math.min(minX, x);
        minY = Math.min(minY, y);
        maxX = Math.max(maxX, x);
        maxY = Math.max(maxY, y);
        return;
      }
      for (const item of coordinates) visit(item);
    };
    const features = geojson.type === 'FeatureCollection' ? geojson.features : [geojson];
    for (const feature of features) visit(feature.geometry.coordinates);
    return [[minX, minY], [maxX, maxY]];
  }

  // 45° hatching for "not reachable", drawn tone-on-tone on top of the WORST colour.
  function hatchImage() {
    const size = 16;
    const data = new Uint8ClampedArray(size * size * 4);
    for (let y = 0; y < size; y += 1) {
      for (let x = 0; x < size; x += 1) {
        if ((x + y) % 8 < 2) {
          const offset = (y * size + x) * 4;
          data[offset] = 0x9e;
          data[offset + 1] = 0xc5;
          data[offset + 2] = 0xf4;
          data[offset + 3] = 170;
        }
      }
    }
    return { width: size, height: size, data };
  }

  function renderDataStand(meta) {
    const text = `Fahrplan von gtfs.de vom ${formatDate(meta.feed && meta.feed.last_modified)}, `
      + `ausgewertet für ${formatDate(meta.service_dates.weekday)} (Werktag) und `
      + `${formatDate(meta.service_dates.sunday)} (Sonntag).`;
    for (const node of document.querySelectorAll('[data-stand]')) node.textContent = text;
  }

  function showNoData(container) {
    container.replaceChildren(
      el('h2', { text: 'Noch keine Daten' }),
      el('p', {
        text: 'Die Pipeline rechnet gerade den ersten Fahrplanstand. Sobald sie fertig ist, '
          + 'erscheinen hier Karte und Zahlen.',
      }),
    );
  }

  function showProblem(container, error) {
    container.replaceChildren(
      el('h2', { text: 'Daten konnten nicht geladen werden' }),
      el('p', { text: `${error.message} Bitte lade die Seite neu.` }),
    );
  }

  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  window.Atlas = {
    RAMP, WORST, FIRST_DARK_CLASS, SCALES,
    setMeta, getJSON, classOf, colorOf, colorExpression, formatValue, formatNumber,
    formatShare, formatDecimal, formatDate, metricCatalog, describe, windowLabel, el, svg,
    bounds, hatchImage, renderDataStand, showNoData, showProblem, prefersReducedMotion,
  };
}());

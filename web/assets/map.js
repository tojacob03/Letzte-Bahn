/* Letzte Bahn – interactive map (index.html). */
(function () {
  'use strict';

  const A = window.Atlas;
  const STYLE_URL = 'https://tiles.openfreemap.org/styles/positron';
  const state = { metric: 't:gp', windowId: null, level: 'raster', selected: null, sort: 'name' };
  const store = { meta: null, munis: null, region: null, change: null, cells: null };
  const muniIndex = new Map();
  const cellIndex = new Map();
  const tooltip = document.getElementById('map-tooltip');
  let catalog = [];
  let map = null;
  let cellsRequest = null;

  init().catch((error) => {
    console.error(error);
    A.showProblem(document.getElementById('place'), error);
  });

  async function init() {
    try {
      store.meta = await A.getJSON('meta.json');
    } catch (error) {
      A.showNoData(document.getElementById('place'));
      document.body.classList.add('no-data');
      return;
    }
    A.setMeta(store.meta);
    const [munis, region, change] = await Promise.all([
      A.getJSON('municipalities.geojson'),
      A.getJSON('region.json'),
      store.meta.change ? A.getJSON('change.json', { optional: true }) : null,
    ]);
    Object.assign(store, { munis, region, change });
    for (const feature of munis.features) muniIndex.set(feature.properties.ags, feature.properties);
    catalog = A.metricCatalog(store.meta);
    state.windowId = store.meta.windows[0].id;
    const pendingCell = readHash();
    buildControls();
    A.renderDataStand(store.meta);
    buildMap(pendingCell);
    renderAll();
  }

  // ---------------------------------------------------------------- state & URL

  function currentMetric() {
    return catalog.find((metric) => metric.id === state.metric) || catalog[0];
  }

  function readHash() {
    const params = new URLSearchParams(window.location.hash.slice(1));
    const metric = params.get('kennzahl');
    if (metric && catalog.some((item) => item.id === metric)) state.metric = metric;
    const windowId = params.get('zeit');
    if (windowId && store.meta.windows.some((slot) => slot.id === windowId)) state.windowId = windowId;
    const level = params.get('ebene');
    if (level === 'raster' || level === 'gemeinden') state.level = level;
    const ags = params.get('ort');
    if (ags && muniIndex.has(ags)) state.selected = { type: 'muni', ags };
    return params.get('zelle');
  }

  function writeHash() {
    const params = new URLSearchParams({
      kennzahl: state.metric,
      zeit: state.windowId,
      ebene: state.level,
    });
    if (state.selected) {
      params.set('ort', state.selected.ags);
      if (state.selected.type === 'cell') params.set('zelle', state.selected.id);
    }
    window.history.replaceState(null, '', `#${params.toString()}`);
  }

  function renderAll() {
    updateMap();
    highlight();
    renderLegend();
    renderPlace();
    renderTable();
    writeHash();
  }

  // ---------------------------------------------------------------- controls

  function buildControls() {
    const select = document.getElementById('metric');
    const groups = new Map();
    for (const metric of catalog) {
      if (!groups.has(metric.group)) {
        const group = A.el('optgroup', { label: metric.group });
        groups.set(metric.group, group);
        select.append(group);
      }
      groups.get(metric.group).append(A.el('option', { value: metric.id, text: metric.label }));
    }
    select.value = state.metric;
    select.addEventListener('change', () => {
      state.metric = select.value;
      renderAll();
    });

    radioGroup(
      document.getElementById('window-options'),
      'zeit',
      store.meta.windows.map((slot) => ({ value: slot.id, label: slot.label })),
      state.windowId,
      (value) => {
        state.windowId = value;
        renderAll();
      },
    );
    radioGroup(
      document.getElementById('level-options'),
      'ebene',
      [
        { value: 'raster', label: `Raster (${store.meta.grid_cell_size_m} m)` },
        { value: 'gemeinden', label: 'Gemeinden' },
      ],
      state.level,
      (value) => {
        state.level = value;
        if (value === 'raster' && map) ensureCells().then(renderAll);
        else renderAll();
      },
    );

    const names = [...muniIndex.values()].sort((a, b) => a.name.localeCompare(b.name, 'de'));
    const list = document.getElementById('place-list');
    for (const props of names) list.append(A.el('option', { value: props.name }));
    const input = document.getElementById('place-search');
    const status = document.getElementById('search-status');
    const find = (event) => {
      if (event) event.preventDefault();
      const query = input.value.trim().toLocaleLowerCase('de');
      if (!query) return;
      const hit = names.find((props) => props.name.toLocaleLowerCase('de') === query)
        || names.find((props) => props.name.toLocaleLowerCase('de').startsWith(query))
        || names.find((props) => props.name.toLocaleLowerCase('de').includes(query));
      if (hit) {
        status.textContent = '';
        selectMuni(hit.ags, { fly: true });
      } else {
        status.textContent = `„${input.value}“ liegt nicht im Gebiet ${store.meta.region.name}.`;
      }
    };
    document.getElementById('search-form').addEventListener('submit', find);
    input.addEventListener('change', find);
  }

  function radioGroup(container, name, options, current, onChange) {
    container.replaceChildren();
    for (const option of options) {
      const id = `${name}-${option.value}`;
      const input = A.el('input', {
        type: 'radio',
        name,
        id,
        value: option.value,
        checked: option.value === current,
      });
      input.addEventListener('change', () => {
        if (input.checked) onChange(option.value);
      });
      container.append(A.el('label', { class: 'segment', for: id }, [
        input,
        A.el('span', { text: option.label }),
      ]));
    }
  }

  // ---------------------------------------------------------------- map

  function firstSymbolLayer() {
    const layer = map.getStyle().layers.find((item) => item.type === 'symbol');
    return layer ? layer.id : undefined;
  }

  function buildMap(pendingCell) {
    map = new maplibregl.Map({
      container: 'map',
      style: STYLE_URL,
      bounds: A.bounds(store.munis),
      fitBoundsOptions: { padding: 24 },
      attributionControl: { compact: true },
      dragRotate: false,
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left');
    map.on('load', async () => {
      map.addImage('hatch', A.hatchImage(), { pixelRatio: 2 });
      const before = firstSymbolLayer();
      map.addSource('munis', { type: 'geojson', data: store.munis });
      map.addLayer({
        id: 'muni-fill',
        type: 'fill',
        source: 'munis',
        paint: { 'fill-color': 'rgba(0,0,0,0)', 'fill-opacity': 0.84 },
      }, before);
      map.addLayer({
        id: 'muni-hatch',
        type: 'fill',
        source: 'munis',
        filter: ['==', ['get', 'ags'], ''],
        paint: { 'fill-pattern': 'hatch' },
      }, before);
      map.addLayer({
        id: 'muni-line',
        type: 'line',
        source: 'munis',
        paint: {
          'line-color': '#15233f',
          'line-opacity': 0.45,
          'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.5, 13, 1.6],
        },
      }, before);
      map.addLayer({
        id: 'muni-selected',
        type: 'line',
        source: 'munis',
        filter: ['==', ['get', 'ags'], ''],
        paint: { 'line-color': '#f2c200', 'line-width': 4 },
      });
      bindLayerEvents('muni-fill', 'muni');
      renderAll();
      if (state.level === 'raster') await ensureCells();
      if (pendingCell && cellIndex.has(pendingCell)) {
        const props = cellIndex.get(pendingCell);
        state.selected = { type: 'cell', id: pendingCell, ags: props.ags };
      }
      renderAll();
      if (state.selected && state.selected.type === 'muni') flyToMuni(state.selected.ags);
      map.once('idle', () => {
        window.atlasReady = true;
      });
    });
  }

  function ensureCells() {
    if (!cellsRequest) {
      setNote('Das Raster wird geladen …');
      cellsRequest = A.getJSON('cells.geojson').then((cells) => {
        store.cells = cells;
        for (const feature of cells.features) {
          addRatios(feature.properties);
          cellIndex.set(feature.properties.id, feature.properties);
        }
        map.addSource('cells', { type: 'geojson', data: cells });
        map.addLayer({
          id: 'cell-fill',
          type: 'fill',
          source: 'cells',
          paint: { 'fill-color': 'rgba(0,0,0,0)', 'fill-opacity': 0.84 },
        }, 'muni-line');
        map.addLayer({
          id: 'cell-hatch',
          type: 'fill',
          source: 'cells',
          filter: ['==', ['get', 'id'], ''],
          paint: { 'fill-pattern': 'hatch' },
        }, 'muni-line');
        map.addLayer({
          id: 'cell-selected',
          type: 'line',
          source: 'cells',
          filter: ['==', ['get', 'id'], ''],
          paint: { 'line-color': '#f2c200', 'line-width': 3 },
        }, 'muni-selected');
        bindLayerEvents('cell-fill', 'cell');
        setNote('');
      }).catch((error) => {
        setNote(`Raster nicht verfügbar: ${error.message}`);
      });
    }
    return cellsRequest;
  }

  // Cells carry travel times; the public transport / car ratio is derived here.
  function addRatios(props) {
    for (const slot of store.meta.windows) {
      for (const category of store.meta.categories) {
        const pt = props[`t_${slot.id}_${category.id}`];
        const car = props[`c_${category.id}`];
        props[`r_${slot.id}_${category.id}`] = pt === null || pt === undefined
          || car === null || car === undefined
          ? null
          : Math.round((pt / Math.max(car, 1)) * 1000) / 1000;
      }
    }
  }

  function setNote(text) {
    const note = document.getElementById('map-note');
    note.textContent = text;
    note.hidden = !text;
  }

  function setVisible(layer, visible) {
    if (map.getLayer(layer)) {
      map.setLayoutProperty(layer, 'visibility', visible ? 'visible' : 'none');
    }
  }

  function updateMap() {
    if (!map || !map.getLayer('muni-fill')) return;
    const metric = currentMetric();
    const key = metric.key(state.windowId);
    const color = A.colorExpression(A.SCALES[metric.kind], key);
    const missing = ['==', ['get', key], null];
    const raster = state.level === 'raster' && Boolean(map.getLayer('cell-fill'));
    map.setPaintProperty('muni-fill', 'fill-color', color);
    map.setFilter('muni-hatch', missing);
    setVisible('muni-fill', !raster);
    setVisible('muni-hatch', !raster);
    if (map.getLayer('cell-fill')) {
      map.setPaintProperty('cell-fill', 'fill-color', color);
      map.setFilter('cell-hatch', missing);
      setVisible('cell-fill', raster);
      setVisible('cell-hatch', raster);
      setVisible('cell-selected', raster);
    }
  }

  function bindLayerEvents(layer, kind) {
    map.on('mousemove', layer, (event) => {
      const feature = event.features && event.features[0];
      if (!feature) return;
      map.getCanvas().style.cursor = 'pointer';
      showTooltip(event.point, kind, feature.properties);
    });
    map.on('mouseleave', layer, () => {
      map.getCanvas().style.cursor = '';
      tooltip.hidden = true;
    });
    map.on('click', layer, (event) => {
      const feature = event.features && event.features[0];
      if (!feature) return;
      if (kind === 'cell') selectCell(feature.properties.id);
      else selectMuni(feature.properties.ags, { fly: false });
    });
  }

  function showTooltip(point, kind, featureProps) {
    const props = kind === 'cell'
      ? cellIndex.get(featureProps.id)
      : muniIndex.get(featureProps.ags);
    if (!props) return;
    const metric = currentMetric();
    const muni = muniIndex.get(props.ags);
    const place = kind === 'cell'
      ? `${store.meta.grid_cell_size_m}-m-Quadrat in ${muni ? muni.name : 'der Region'}, `
        + `${A.formatNumber(props.pop)} Einw.`
      : `${props.name}, ${A.formatNumber(props.pop)} Einw.`;
    tooltip.replaceChildren(
      A.el('strong', {
        class: 'tooltip-value',
        text: A.formatValue(metric.kind, props[metric.key(state.windowId)]),
      }),
      A.el('span', { class: 'tooltip-place', text: place }),
    );
    tooltip.hidden = false;
    const width = tooltip.offsetWidth;
    const container = map.getContainer().clientWidth;
    const x = point.x + 16 + width > container ? point.x - width - 12 : point.x + 16;
    tooltip.style.transform = `translate(${Math.max(4, x)}px, ${point.y + 12}px)`;
  }

  function highlight() {
    if (!map || !map.getLayer('muni-selected')) return;
    const ags = state.selected ? state.selected.ags : '';
    map.setFilter('muni-selected', ['==', ['get', 'ags'], ags]);
    if (map.getLayer('cell-selected')) {
      const id = state.selected && state.selected.type === 'cell' ? state.selected.id : '';
      map.setFilter('cell-selected', ['==', ['get', 'id'], id]);
    }
  }

  function selectMuni(ags, { fly }) {
    state.selected = { type: 'muni', ags };
    if (fly) flyToMuni(ags);
    renderAll();
    document.getElementById('place').focus({ preventScroll: true });
  }

  function selectCell(id) {
    const props = cellIndex.get(id);
    if (!props) return;
    state.selected = { type: 'cell', id, ags: props.ags };
    renderAll();
  }

  function flyToMuni(ags) {
    const feature = store.munis.features.find((item) => item.properties.ags === ags);
    if (!feature || !map) return;
    map.fitBounds(A.bounds(feature), {
      padding: 60,
      maxZoom: 12.5,
      duration: A.prefersReducedMotion() ? 0 : 900,
    });
  }

  // ---------------------------------------------------------------- legend

  function renderLegend() {
    const metric = currentMetric();
    const scale = A.SCALES[metric.kind];
    const items = scale.labels.map((label, index) => legendItem(A.RAMP[index], label, false));
    if (scale.worst) items.push(legendItem(A.WORST, scale.worst, true));
    let basis = `je ${store.meta.grid_cell_size_m}-m-Quadrat`;
    if (state.level === 'gemeinden') {
      basis = metric.kind === 'population' ? 'Durchschnitt der Einwohner' : 'Median der Einwohner';
    }
    document.getElementById('legend').replaceChildren(
      A.el('p', { class: 'legend-title', text: A.describe(metric) }),
      A.el('p', {
        class: 'legend-sub',
        text: `${A.windowLabel(store.meta, state.windowId)}, ${basis}`,
      }),
      A.el('ul', { class: 'legend-items' }, items),
      A.el('p', { class: 'legend-note', text: 'Je dunkler, desto schlechter angebunden.' }),
    );
  }

  function legendItem(color, label, hatched) {
    return A.el('li', {}, [
      A.el('span', {
        class: hatched ? 'swatch swatch-hatched' : 'swatch',
        style: `background-color: ${color}`,
        'aria-hidden': 'true',
      }),
      A.el('span', { text: label }),
    ]);
  }

  // ---------------------------------------------------------------- place panel

  function renderPlace() {
    const root = document.getElementById('place');
    const muni = state.selected ? muniIndex.get(state.selected.ags) : null;
    const isCell = Boolean(state.selected && state.selected.type === 'cell');
    const props = isCell ? cellIndex.get(state.selected.id) : muni;
    if (!muni || !props) {
      root.replaceChildren(...regionSummary());
      return;
    }
    const size = store.meta.grid_cell_size_m;
    const heading = isCell ? `Ein Quadrat in ${muni.name}` : muni.name;
    const subline = isCell
      ? `${A.formatNumber(props.pop)} Einwohner auf ${size} × ${size} Metern`
      : `${muni.kreis}, ${A.formatNumber(muni.pop)} Einwohner`;
    root.replaceChildren(
      A.el('div', { class: 'place-head' }, [
        A.el('h2', { text: heading }),
        A.el('p', { class: 'place-sub', text: subline }),
        A.el('button', {
          type: 'button',
          class: 'text-button',
          text: 'Auswahl aufheben',
          onclick: () => {
            state.selected = null;
            renderAll();
          },
        }),
      ]),
      timetable(props, isCell),
      carComparison(props, isCell),
      changeNote(muni),
      neighbours(muni),
    );
  }

  function referenceThreshold() {
    const metric = currentMetric();
    if (metric.kind === 'population') return metric.threshold;
    const thresholds = store.meta.thresholds;
    return thresholds.includes(45) ? 45 : thresholds[Math.floor(thresholds.length / 2)];
  }

  function timetable(props, isCell) {
    const windows = store.meta.windows;
    const threshold = referenceThreshold();
    const header = A.el('tr', {}, [
      A.el('th', { scope: 'col', text: 'Nächstes Ziel' }),
      ...windows.map((slot) => A.el('th', { scope: 'col', text: slot.label })),
      A.el('th', { scope: 'col', text: 'Auto' }),
    ]);
    const rows = store.meta.categories.map((category) => A.el('tr', {}, [
      A.el('th', { scope: 'row', text: category.label }),
      ...windows.map((slot) => valueCell('time', props[`t_${slot.id}_${category.id}`])),
      valueCell('time', props[`c_${category.id}`], true),
    ]));
    const reach = A.el('tr', { class: 'reach' }, [
      A.el('th', { scope: 'row', text: `Menschen in ${threshold} Min.` }),
      ...windows.map((slot) => valueCell('population', props[`p${threshold}_${slot.id}`])),
      valueCell('population', props[`pc${threshold}`], true),
    ]);
    const caption = isCell
      ? 'Minuten mit Bus, Bahn und zu Fuß ab diesem Quadrat, Median über alle Abfahrten im '
        + 'Zeitfenster. Schraffiert: länger als 2 Stunden oder nicht erreichbar.'
      : 'Minuten mit Bus, Bahn und zu Fuß, Median der Einwohner (die Hälfte braucht länger). '
        + 'Schraffiert: länger als 2 Stunden oder nicht erreichbar.';
    return A.el('figure', { class: 'timetable-wrap' }, [
      A.el('figcaption', { text: caption }),
      A.el('table', { class: 'timetable' }, [
        A.el('thead', {}, header),
        A.el('tbody', {}, [...rows, reach]),
      ]),
    ]);
  }

  function valueCell(kind, value, isCar = false) {
    const missing = value === null || value === undefined;
    // Minutes are named in the caption, so the cells stay narrow: numbers only.
    const text = kind === 'time' ? (missing ? '–' : A.formatNumber(value)) : A.formatValue(kind, value);
    const cell = A.el('td', { class: isCar ? 'value car' : 'value', text });
    if (missing && kind === 'time') cell.title = 'länger als 2 Stunden oder nicht erreichbar';
    if (isCar) return cell;
    const cls = A.classOf(A.SCALES[kind], value);
    cell.style.backgroundColor = cls === null ? A.WORST : A.RAMP[cls];
    if (cls === null || cls >= A.FIRST_DARK_CLASS) cell.classList.add('dark');
    if (cls === null) cell.classList.add('unreachable');
    return cell;
  }

  function carComparison(props, isCell) {
    const metric = currentMetric();
    const windowText = A.windowLabel(store.meta, state.windowId);
    const typical = isCell ? '' : 'Für den mittleren Einwohner gilt: ';
    if (metric.kind === 'population') {
      const pt = props[metric.key(state.windowId)];
      const car = props[metric.carKey];
      return A.el('p', {
        class: 'car-note',
        text: `${typical}In ${metric.threshold} Minuten erreicht man ${windowText} mit Bus und `
          + `Bahn ${A.formatNumber(pt)} Menschen, mit dem Auto ${A.formatNumber(car)}.`,
      });
    }
    const pt = props[`t_${state.windowId}_${metric.category}`];
    const car = props[`c_${metric.category}`];
    const ratio = props[`r_${state.windowId}_${metric.category}`];
    let text;
    if (pt === null || pt === undefined) {
      text = `${typical}${windowText} ist mit Bus und Bahn kein Ziel der Kategorie `
        + `„${metric.label}“ innerhalb von zwei Stunden erreichbar; mit dem Auto sind es `
        + `${A.formatValue('time', car)}.`;
    } else {
      text = `${typical}Zum nächsten Ziel der Kategorie „${metric.label}“ dauert es `
        + `${windowText} mit Bus und Bahn ${A.formatValue('time', pt)}, mit dem Auto `
        + `${A.formatValue('time', car)}`
        + (ratio === null || ratio === undefined ? '.' : `, also ${A.formatValue('ratio', ratio)} so lange.`);
    }
    return A.el('p', { class: 'car-note', text });
  }

  function changeNote(muni) {
    if (!store.change || !store.change.municipalities) return null;
    const metric = currentMetric();
    if (metric.kind === 'ratio') return null;
    const delta = (store.change.municipalities[muni.ags] || {})[metric.key(state.windowId)];
    if (delta === null || delta === undefined) return null;
    const previousDate = store.change.previous_snapshot.split('_').pop();
    let text = 'unverändert';
    if (delta !== 0 && metric.kind === 'time') {
      text = `${A.formatNumber(Math.abs(delta))} Min. ${delta < 0 ? 'schneller' : 'langsamer'}`;
    } else if (delta !== 0) {
      text = `${delta > 0 ? 'plus' : 'minus'} ${A.formatNumber(Math.abs(delta))} Menschen`;
    }
    const caveat = store.change.comparable
      ? ''
      : ' Die Methodik hat sich seitdem geändert; der Vergleich ist nur eingeschränkt aussagekräftig.';
    return A.el('p', {
      class: 'change-note',
      text: `Gegenüber dem Fahrplanstand vom ${A.formatDate(previousDate)}: ${text}.${caveat}`,
    });
  }

  function regionValue(metric) {
    if (metric.kind === 'population') {
      const row = store.region.reachability.find((item) => item.window_id === state.windowId
        && item.threshold_min === metric.threshold);
      return row ? row.median_reachable_population_pt : null;
    }
    const row = store.region.accessibility.find((item) => item.window_id === state.windowId
      && item.category === metric.category);
    if (!row) return null;
    return metric.kind === 'time' ? row.median_pt_minutes : row.median_pt_car_ratio;
  }

  function neighbours(muni) {
    const metric = currentMetric();
    const key = metric.key(state.windowId);
    const rows = [muni, ...(muni.nb || []).map((ags) => muniIndex.get(ags)).filter(Boolean)]
      .map((props) => ({
        name: props.name,
        ags: props.ags,
        value: props[key],
        selected: props.ags === muni.ags,
      }));
    const lowerIsBetter = metric.kind !== 'population';
    const missingRank = lowerIsBetter ? Infinity : -Infinity;
    rows.sort((a, b) => {
      const va = a.value === null || a.value === undefined ? missingRank : a.value;
      const vb = b.value === null || b.value === undefined ? missingRank : b.value;
      if (va === vb) return 0;
      return lowerIsBetter ? (va < vb ? -1 : 1) : (va > vb ? -1 : 1);
    });
    const regional = regionValue(metric);
    const values = rows.map((row) => row.value).filter((value) => value !== null && value !== undefined);
    if (regional !== null && regional !== undefined) values.push(regional);
    const max = Math.max(1, ...values);
    const items = rows.map((row) => compareRow(
      row.name, row.value, max, metric.kind, row.selected,
      () => selectMuni(row.ags, { fly: true }),
    ));
    if (regional !== null && regional !== undefined) {
      items.push(compareRow(
        `${store.meta.region.name} insgesamt (Median)`, regional, max, metric.kind, false, null, true,
      ));
    }
    return A.el('section', { class: 'compare', 'aria-label': 'Vergleich mit den Nachbargemeinden' }, [
      A.el('h3', { text: 'Im Vergleich mit den Nachbarn' }),
      A.el('p', {
        class: 'compare-sub',
        text: `${A.describe(metric)}, ${A.windowLabel(store.meta, state.windowId)}`,
      }),
      A.el('ol', { class: 'compare-list' }, items),
    ]);
  }

  function compareRow(name, value, max, kind, selected, onSelect, reference = false) {
    const missing = value === null || value === undefined;
    const width = missing ? 100 : Math.max(2, (value / max) * 100);
    const label = onSelect && !selected
      ? A.el('button', { type: 'button', class: 'compare-name text-button', text: name, onclick: onSelect })
      : A.el('span', { class: 'compare-name', text: name });
    let barClass = 'compare-bar';
    if (selected) barClass += ' is-selected';
    if (reference) barClass += ' is-reference';
    if (missing) barClass += ' is-missing';
    return A.el('li', { class: selected ? 'compare-row is-selected' : 'compare-row' }, [
      label,
      A.el('span', { class: 'compare-track', 'aria-hidden': 'true' }, [
        A.el('span', { class: barClass, style: `width: ${width}%` }),
      ]),
      A.el('span', { class: 'compare-value', text: A.formatValue(kind, value) }),
    ]);
  }

  function regionSummary() {
    const metric = currentMetric();
    const windowText = A.windowLabel(store.meta, state.windowId);
    const regionName = store.meta.region.name;
    const parts = [
      A.el('h2', { text: `${regionName} insgesamt` }),
      A.el('p', {
        class: 'hint',
        text: 'Klick auf die Karte oder such deinen Ort. Dann siehst du hier, wie lange es von '
          + 'dort zu Hausarzt, Supermarkt, Schule und Bahnhof dauert und wie der Ort gegenüber '
          + 'den Nachbarn und dem Auto abschneidet.',
      }),
    ];
    if (metric.kind === 'population') {
      const row = store.region.reachability.find((item) => item.window_id === state.windowId
        && item.threshold_min === metric.threshold);
      if (row) {
        parts.push(A.el('p', {
          class: 'summary',
          text: `${windowText} erreicht der mittlere Einwohner mit Bus und Bahn in `
            + `${metric.threshold} Minuten ${A.formatNumber(row.median_reachable_population_pt)} `
            + `Menschen, mit dem Auto ${A.formatNumber(row.median_reachable_population_car)}.`,
        }));
      }
    } else {
      const row = store.region.accessibility.find((item) => item.window_id === state.windowId
        && item.category === metric.category);
      if (row && metric.kind === 'time') {
        parts.push(A.el('p', {
          class: 'summary',
          text: `${windowText} erreichen ${A.formatShare(row.share_within_30)} der Menschen das `
            + `nächste Ziel der Kategorie „${metric.label}“ in 30 Minuten mit Bus und Bahn, `
            + `${A.formatShare(row.share_within_60)} in einer Stunde. Für `
            + `${A.formatShare(row.share_unreachable)} ist es in zwei Stunden nicht erreichbar.`,
        }));
      } else if (row) {
        parts.push(A.el('p', {
          class: 'summary',
          text: `${windowText} dauert der Weg zum nächsten Ziel der Kategorie „${metric.label}“ `
            + `für den mittleren Einwohner ${A.formatValue('ratio', row.median_pt_car_ratio)} so `
            + 'lange wie mit dem Auto.',
        }));
      }
    }
    parts.push(A.el('p', {}, [
      A.el('a', { href: 'analyse.html', text: 'Die wichtigsten Befunde in der Analyse lesen' }),
    ]));
    return parts;
  }

  // ---------------------------------------------------------------- table view

  function renderTable() {
    const container = document.getElementById('muni-table');
    if (!container) return;
    const metric = currentMetric();
    const columns = [
      { id: 'name', label: 'Gemeinde', value: (p) => p.name, text: true },
      { id: 'kreis', label: 'Landkreis', value: (p) => p.kreis, text: true },
      { id: 'pop', label: 'Einwohner', value: (p) => p.pop, kind: 'population' },
      ...store.meta.windows.map((slot) => ({
        id: slot.id,
        label: slot.label,
        value: (p) => p[metric.key(slot.id)],
        kind: metric.kind,
      })),
    ];
    if (metric.carKey) {
      columns.push({
        id: 'car',
        label: 'Auto',
        value: (p) => p[metric.carKey],
        kind: metric.kind === 'population' ? 'population' : 'time',
      });
    }
    const column = columns.find((item) => item.id === state.sort) || columns[0];
    const descending = column.kind === 'population';
    const rows = [...muniIndex.values()].sort((a, b) => {
      const va = column.value(a);
      const vb = column.value(b);
      if (column.text) return String(va ?? '').localeCompare(String(vb ?? ''), 'de');
      const missingA = va === null || va === undefined;
      const missingB = vb === null || vb === undefined;
      if (missingA || missingB) return Number(missingA) - Number(missingB);
      return descending ? vb - va : va - vb;
    });
    const header = A.el('tr', {}, columns.map((item) => A.el('th', {
      scope: 'col',
      'aria-sort': item.id === column.id ? (descending ? 'descending' : 'ascending') : null,
    }, [
      A.el('button', {
        type: 'button',
        class: 'sort-button',
        text: item.label,
        onclick: () => {
          state.sort = item.id;
          renderTable();
        },
      }),
    ])));
    const body = rows.map((props) => A.el('tr', {}, columns.map((item) => {
      const value = item.value(props);
      if (item.id === 'name') {
        return A.el('th', { scope: 'row' }, [
          A.el('button', {
            type: 'button',
            class: 'text-button',
            text: value,
            onclick: () => selectMuni(props.ags, { fly: true }),
          }),
        ]);
      }
      if (item.text) return A.el('td', { text: value || '–' });
      return A.el('td', { class: 'num', text: A.formatValue(item.kind, value) });
    })));
    const basis = metric.kind === 'population' ? 'Durchschnitt' : 'Median';
    container.replaceChildren(
      A.el('p', {
        class: 'table-caption',
        text: `${A.describe(metric)} (${basis} der Einwohner je Gemeinde). Ein Klick auf eine `
          + 'Spaltenüberschrift sortiert die Tabelle.',
      }),
      A.el('div', { class: 'table-scroll' }, [
        A.el('table', { class: 'data-table' }, [A.el('thead', {}, header), A.el('tbody', {}, body)]),
      ]),
    );
  }
}());

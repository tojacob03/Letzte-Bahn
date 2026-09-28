/* Letzte Bahn – analysis page: findings computed by the pipeline (fct_findings). */
(function () {
  'use strict';

  const A = window.Atlas;
  const W = { am: 'wd_am', pm: 'wd_pm', su: 'su_am' };
  const SERIES = { am: '#2a78d6', pm: '#eb6834', car: '#9aa3b1' };

  init().catch((error) => {
    console.error(error);
    A.showProblem(document.getElementById('findings'), error);
  });

  async function init() {
    const root = document.getElementById('findings');
    let meta;
    try {
      meta = await A.getJSON('meta.json');
    } catch (error) {
      A.showNoData(root);
      return;
    }
    A.setMeta(meta);
    const [findings, region, munis] = await Promise.all([
      A.getJSON('findings.json'),
      A.getJSON('region.json'),
      A.getJSON('municipalities.geojson'),
    ]);
    A.renderDataStand(meta);
    const context = {
      meta,
      findings,
      region,
      munis: munis.features.map((feature) => feature.properties),
      label: (id) => A.windowLabel(meta, id),
    };
    document.getElementById('region-name').textContent = meta.region.name;
    root.replaceChildren(
      doctorsInTheEvening(context),
      sundayRadius(context),
      carComparison(context),
      overview(context),
      municipalGap(context),
    );
    window.atlasReady = true;
  }

  function get(context, finding, key) {
    const entry = context.findings[finding] || {};
    return entry[key] === undefined ? null : entry[key];
  }

  function section(id, title, paragraphs, figure) {
    return A.el('section', { class: 'finding', id }, [
      A.el('h2', { text: title }),
      ...paragraphs.filter(Boolean).map((text) => A.el('p', { text })),
      figure,
    ]);
  }

  function accessRow(context, windowId, category) {
    return context.region.accessibility.find((row) => row.window_id === windowId
      && row.category === category) || {};
  }

  // ---------------------------------------------------------------- 1: doctors at night

  function doctorsInTheEvening(context) {
    const below = get(context, 'gp_evening_60', 'municipalities_below_half');
    const total = get(context, 'gp_evening_60', 'municipalities_total');
    const withoutAm = get(context, 'gp_evening_60', `population_share_without_${W.am}`);
    const withoutPm = get(context, 'gp_evening_60', `population_share_without_${W.pm}`);
    const withoutSu = get(context, 'gp_evening_60', `population_share_without_${W.su}`);
    const title = below === 0
      ? 'Auch abends erreicht in jeder Gemeinde die Mehrheit eine Hausarztpraxis in einer Stunde'
      : `In ${A.formatNumber(below)} von ${A.formatNumber(total)} Gemeinden kommt abends weniger `
        + 'als die Hälfte der Menschen in einer Stunde zu einer Hausarztpraxis';
    const rows = context.munis
      .map((props) => ({
        name: props.name,
        am: props[`s60_${W.am}_gp`],
        pm: props[`s60_${W.pm}_gp`],
      }))
      .filter((row) => row.am !== null && row.am !== undefined)
      .sort((a, b) => (a.pm ?? 0) - (b.pm ?? 0) || a.name.localeCompare(b.name, 'de'));
    return section('hausarzt', title, [
      `Werktags zwischen 20 und 22 Uhr kommen ${A.formatShare(withoutPm)} der Menschen im `
        + `Gebiet ${context.meta.region.name} nicht innerhalb von 60 Minuten mit Bus und Bahn zu `
        + `einer Hausarztpraxis. Morgens zwischen 7 und 9 Uhr sind es ${A.formatShare(withoutAm)}, `
        + `sonntags vormittags ${A.formatShare(withoutSu)}.`,
      'Gemessen wird die Verbindung, nicht die Sprechstunde: Abends hat kaum eine Praxis offen. '
        + 'Die Zahl zeigt, wie dünn der Takt nach Feierabend wird. Wer ohne Auto lebt, kommt in '
        + 'dieser Zeit auch zu allen anderen Zielen im nächsten Ort schlecht hin.',
    ], dumbbell(rows, context));
  }

  function dumbbell(rows, context) {
    const width = 720;
    const rowHeight = 17;
    const labelWidth = 178;
    const top = 30;
    const right = 24;
    const plotWidth = width - labelWidth - right;
    const height = top + rows.length * rowHeight + 8;
    const x = (value) => labelWidth + value * plotWidth;
    const chart = A.svg('svg', {
      viewBox: `0 0 ${width} ${height}`,
      class: 'chart',
      role: 'img',
      'aria-label': 'Anteil der Einwohner je Gemeinde, die eine Hausarztpraxis in 60 Minuten '
        + 'erreichen, morgens und abends',
    });
    for (const tick of [0, 0.25, 0.5, 0.75, 1]) {
      chart.append(A.svg('line', {
        x1: x(tick), x2: x(tick), y1: top - 6, y2: height - 4,
        class: tick === 0.5 ? 'grid grid-strong' : 'grid',
      }));
      chart.append(A.svg('text', {
        x: x(tick), y: top - 12, class: 'axis-label', 'text-anchor': 'middle',
        text: A.formatShare(tick),
      }));
    }
    rows.forEach((row, index) => {
      const y = top + index * rowHeight + rowHeight / 2;
      const group = A.svg('g', { class: 'dumbbell-row', tabindex: '0' });
      group.append(A.svg('title', {
        text: `${row.name}: ${A.formatShare(row.am)} morgens, ${A.formatShare(row.pm)} abends`,
      }));
      group.append(A.svg('rect', {
        x: 0, y: y - rowHeight / 2, width, height: rowHeight, class: 'row-hit',
      }));
      group.append(A.svg('text', {
        x: labelWidth - 10, y: y + 4, class: 'row-label', 'text-anchor': 'end', text: row.name,
      }));
      const pm = row.pm ?? 0;
      group.append(A.svg('line', { x1: x(pm), x2: x(row.am), y1: y, y2: y, class: 'connector' }));
      group.append(A.svg('circle', { cx: x(row.am), cy: y, r: 4.5, fill: SERIES.am, class: 'dot' }));
      group.append(A.svg('circle', { cx: x(pm), cy: y, r: 4.5, fill: SERIES.pm, class: 'dot' }));
      chart.append(group);
    });
    return figure(
      [legendKey(SERIES.am, context.label(W.am)), legendKey(SERIES.pm, context.label(W.pm))],
      chart,
      'Anteil der Einwohner, die in 60 Minuten eine Hausarztpraxis erreichen. Jede Zeile ist eine '
        + 'Gemeinde, sortiert nach dem Abendwert. Die kräftigere Linie markiert die Hälfte.',
      table(
        ['Gemeinde', context.label(W.am), context.label(W.pm)],
        rows.map((row) => [row.name, A.formatShare(row.am), A.formatShare(row.pm)]),
      ),
    );
  }

  // ---------------------------------------------------------------- 2: Sunday radius

  function sundayRadius(context) {
    const am = get(context, 'reach_45', `median_${W.am}`);
    const pm = get(context, 'reach_45', `median_${W.pm}`);
    const su = get(context, 'reach_45', `median_${W.su}`);
    const car = get(context, 'reach_45', 'car_median');
    const drop = am ? 1 - su / am : null;
    const title = drop !== null && drop > 0
      ? `Sonntags erreicht man in 45 Minuten ${A.formatShare(drop)} weniger Menschen als an einem `
        + 'Werktagmorgen'
      : 'Sonntags erreicht man in 45 Minuten etwa so viele Menschen wie werktags';
    const rows = [
      { label: context.label(W.am), value: am, color: SERIES.am },
      { label: context.label(W.pm), value: pm, color: SERIES.am },
      { label: context.label(W.su), value: su, color: SERIES.am },
      { label: 'Mit dem Auto', value: car, color: SERIES.car },
    ];
    return section('sonntag', title, [
      'Wie viele Menschen man in 45 Minuten erreicht, steht hier für die Chancen, die ein Ort '
        + 'bietet: Arbeit, Freunde, Vereine. Offene Arbeitsplatzdaten auf so feinem Raster gibt es '
        + 'nicht, die Bevölkerung ist der ehrlichste verfügbare Ersatz.',
      `Der mittlere Einwohner erreicht werktags morgens ${A.formatNumber(am)} Menschen, abends `
        + `${A.formatNumber(pm)} und sonntags ${A.formatNumber(su)}. Mit dem Auto wären es `
        + `${A.formatNumber(car)}.`,
    ], barChart(rows, (value) => A.formatNumber(value),
      'Median der erreichbaren Einwohner in 45 Minuten; alle Einwohner der Region zählen gleich.'));
  }

  // ---------------------------------------------------------------- 3: versus the car

  function carComparison(context) {
    const ratio = get(context, 'pt_car_ratio_supermarket', `median_ratio_${W.am}`);
    const over3 = get(context, 'pt_car_ratio_supermarket', `share_over_3_${W.am}`);
    const title = ratio === null
      ? 'Der Weg zum Supermarkt dauert mit Bus und Bahn oft länger als zwei Stunden'
      : `Zum Supermarkt braucht man mit Bus und Bahn ${A.formatValue('ratio', ratio)} so lange wie `
        + 'mit dem Auto';
    const rows = context.meta.categories.map((category) => ({
      label: category.label,
      value: accessRow(context, W.am, category.id).median_pt_car_ratio ?? null,
      color: SERIES.am,
    }));
    return section('auto', title, [
      `Das gilt für den mittleren Einwohner werktags morgens. Für ${A.formatShare(over3)} der `
        + 'Menschen dauert es mehr als dreimal so lange oder ist in zwei Stunden gar nicht möglich.',
      'Die Autozeiten sind reine Fahrzeiten bei freier Straße, ohne Stau und Parkplatzsuche. Sie '
        + 'fallen also eher zu günstig für das Auto aus; der echte Abstand ist kleiner.',
    ], barChart(rows, (value) => A.formatValue('ratio', value),
      'Median des Verhältnisses Reisezeit mit Bus und Bahn zu Reisezeit mit dem Auto, werktags 7 '
        + 'bis 9 Uhr. Die senkrechte Linie markiert „so schnell wie das Auto“.', 1));
  }

  // ---------------------------------------------------------------- 4: overview table

  function overview(context) {
    const stationAm = get(context, 'rail_station_30', `population_share_within_${W.am}`);
    const stationPm = get(context, 'rail_station_30', `population_share_within_${W.pm}`);
    const hospitalPm = get(context, 'hospital_60', `population_share_without_${W.pm}`);
    const hospitalAm = get(context, 'hospital_60', `population_share_without_${W.am}`);
    const windows = context.meta.windows;
    const header = ['Nächstes Ziel', ...windows.map((slot) => slot.label)];
    const body = context.meta.categories.map((category) => [
      category.label,
      ...windows.map((slot) => accessRow(context, slot.id, category.id).share_within_30 ?? null),
    ]);
    return section('ueberblick', 'Wer was in 30 Minuten erreicht', [
      `Morgens erreichen ${A.formatShare(stationAm)} der Menschen in einer halben Stunde einen `
        + `Bahnhof, an dem in diesem Zeitfenster auch ein Zug fährt, abends ${A.formatShare(stationPm)}. `
        + `Ohne Krankenhaus in einer Stunde sind morgens ${A.formatShare(hospitalAm)}, abends `
        + `${A.formatShare(hospitalPm)} der Menschen.`,
    ], heatTable(header, body));
  }

  function heatTable(header, body) {
    const scale = A.SCALES.share;
    const rows = body.map(([label, ...values]) => A.el('tr', {}, [
      A.el('th', { scope: 'row', text: label }),
      ...values.map((value) => {
        const cls = A.classOf(scale, value);
        const cell = A.el('td', { class: 'value', text: A.formatShare(value) });
        cell.style.backgroundColor = cls === null ? A.WORST : A.RAMP[cls];
        if (cls === null || cls >= A.FIRST_DARK_CLASS) cell.classList.add('dark');
        return cell;
      }),
    ]));
    return A.el('figure', { class: 'figure' }, [
      A.el('table', { class: 'timetable heat' }, [
        A.el('thead', {}, A.el('tr', {}, header.map((text) => A.el('th', { scope: 'col', text })))),
        A.el('tbody', {}, rows),
      ]),
      A.el('figcaption', {
        text: 'Anteil der Einwohner, die das nächste Ziel in 30 Minuten mit Bus, Bahn und zu Fuß '
          + 'erreichen. Je dunkler, desto weniger.',
      }),
    ]);
  }

  // ---------------------------------------------------------------- 5: municipal gap

  function municipalGap(context) {
    const best = get(context, 'municipal_gap_45', 'best');
    const worst = get(context, 'municipal_gap_45', 'worst');
    const bestName = get(context, 'municipal_gap_45', 'best_label');
    const worstName = get(context, 'municipal_gap_45', 'worst_label');
    const factor = best && worst ? best / worst : null;
    const title = factor
      ? `In ${bestName} erreicht man ${A.formatDecimal(factor).replace(',0', '')}-mal so viele `
        + `Menschen wie in ${worstName}`
      : 'Zwischen den Gemeinden liegen große Unterschiede';
    const rows = [
      { label: bestName, value: best, color: SERIES.am },
      { label: worstName, value: worst, color: SERIES.am },
    ];
    return section('spanne', title, [
      `Durchschnittlich erreichbare Einwohner in 45 Minuten, werktags morgens: ${A.formatNumber(best)} `
        + `in ${bestName}, ${A.formatNumber(worst)} in ${worstName}. Die Karte zeigt jede Gemeinde `
        + 'im direkten Vergleich mit ihren Nachbarn.',
    ], barChart(rows, (value) => A.formatNumber(value),
      'Durchschnitt der erreichbaren Einwohner in 45 Minuten, beste und schwächste Gemeinde.'));
  }

  // ---------------------------------------------------------------- shared chart parts

  function barChart(rows, format, caption, reference = null) {
    const width = 720;
    const labelWidth = 210;
    const valueWidth = 110;
    const barHeight = 18;
    const gap = 12;
    const top = 8;
    const plotWidth = width - labelWidth - valueWidth;
    const values = rows.map((row) => row.value).filter((value) => value !== null && value !== undefined);
    const max = Math.max(reference || 0, ...values, 1e-9);
    const height = top + rows.length * (barHeight + gap);
    const x = (value) => labelWidth + (value / max) * plotWidth;
    const chart = A.svg('svg', {
      viewBox: `0 0 ${width} ${height}`, class: 'chart', role: 'img', 'aria-label': caption,
    });
    chart.append(A.svg('line', {
      x1: labelWidth, x2: labelWidth, y1: 0, y2: height, class: 'baseline',
    }));
    rows.forEach((row, index) => {
      const y = top + index * (barHeight + gap);
      const group = A.svg('g', { tabindex: '0' });
      group.append(A.svg('title', { text: `${row.label}: ${format(row.value)}` }));
      group.append(A.svg('rect', {
        x: 0, y: y - gap / 2, width, height: barHeight + gap, class: 'row-hit',
      }));
      group.append(A.svg('text', {
        x: labelWidth - 10, y: y + barHeight / 2 + 5, class: 'row-label', 'text-anchor': 'end',
        text: row.label,
      }));
      if (row.value !== null && row.value !== undefined) {
        const end = Math.max(x(row.value), labelWidth + 3);
        group.append(A.svg('path', {
          d: roundedBar(labelWidth, y, end - labelWidth, barHeight), fill: row.color,
        }));
        group.append(A.svg('text', {
          x: end + 8, y: y + barHeight / 2 + 5, class: 'value-label', text: format(row.value),
        }));
      } else {
        group.append(A.svg('text', {
          x: labelWidth + 8, y: y + barHeight / 2 + 5, class: 'value-label', text: 'nicht erreichbar',
        }));
      }
      chart.append(group);
    });
    if (reference !== null) {
      chart.append(A.svg('line', {
        x1: x(reference), x2: x(reference), y1: 0, y2: height, class: 'grid grid-strong',
      }));
    }
    return figure(
      [],
      chart,
      caption,
      table(['', 'Wert'], rows.map((row) => [row.label, format(row.value)])),
    );
  }

  // Bar with a 4px rounded data end and a square baseline end.
  function roundedBar(x, y, width, height) {
    const r = Math.min(4, width / 2, height / 2);
    return `M${x},${y}H${x + width - r}Q${x + width},${y} ${x + width},${y + r}`
      + `V${y + height - r}Q${x + width},${y + height} ${x + width - r},${y + height}H${x}Z`;
  }

  function legendKey(color, label) {
    return A.el('span', { class: 'key' }, [
      A.el('span', { class: 'key-dot', style: `background-color: ${color}`, 'aria-hidden': 'true' }),
      A.el('span', { text: label }),
    ]);
  }

  function figure(keys, chart, caption, dataTable) {
    return A.el('figure', { class: 'figure' }, [
      keys.length ? A.el('div', { class: 'keys' }, keys) : null,
      chart,
      A.el('figcaption', { text: caption }),
      A.el('details', { class: 'table-toggle' }, [
        A.el('summary', { text: 'Werte als Tabelle' }),
        dataTable,
      ]),
    ]);
  }

  function table(header, rows) {
    return A.el('div', { class: 'table-scroll' }, [
      A.el('table', { class: 'data-table' }, [
        A.el('thead', {}, A.el('tr', {}, header.map((text) => A.el('th', { scope: 'col', text })))),
        A.el('tbody', {}, rows.map((cells) => A.el('tr', {}, cells.map((text, index) => (
          index === 0 ? A.el('th', { scope: 'row', text }) : A.el('td', { class: 'num', text })
        ))))),
      ]),
    ]);
  }
}());

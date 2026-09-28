/* Letzte Bahn – methodology page: facts of the current run from meta.json. */
(function () {
  'use strict';

  const A = window.Atlas;

  A.getJSON('meta.json').then((meta) => {
    A.setMeta(meta);
    A.renderDataStand(meta);
    const counts = meta.counts || {};
    const pois = counts.pois || {};
    const facts = [
      ['Region', meta.region.name],
      ['Gemeinden', A.formatNumber(counts.municipalities)],
      ['Einwohner (Zensus 2022, Rastersumme)', A.formatNumber(counts.population_region)],
      [`Bewohnte ${meta.grid_cell_size_m}-m-Quadrate als Startpunkte`, A.formatNumber(counts.origin_cells)],
      ['Analysierter Werktag', A.formatDate(meta.service_dates.weekday)],
      ['Analysierter Sonntag', A.formatDate(meta.service_dates.sunday)],
      ...meta.categories.map((category) => [`Ziele: ${category.label}`, A.formatNumber(pois[category.id])]),
      ['Davon eindeutig als Hausarzt gekennzeichnet', A.formatNumber(counts.gp_strict)],
    ];
    const list = document.getElementById('run-facts');
    list.replaceChildren(...facts.flatMap(([term, value]) => [
      A.el('dt', { text: term }),
      A.el('dd', { text: value }),
    ]));
  }).catch(() => {
    const list = document.getElementById('run-facts');
    list.replaceChildren(A.el('dd', { text: 'Noch kein Lauf veröffentlicht.' }));
  });
}());

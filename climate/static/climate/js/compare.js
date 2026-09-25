/* Compare: up to four regions' series on one chart, aligned by year. */
(function () {
  "use strict";

  const C = window.Climate;
  const $ = (id) => document.getElementById(id);
  const form = $("controls");
  const picks = $("region-picks");
  const MAX = Number(picks.dataset.max);
  const inputs = {
    parameter: $("parameter"),
    period: $("period"),
    year_from: $("year_from"),
    year_to: $("year_to"),
  };
  const results = $("results");
  const setSummary = C.filtersSheet();
  const table = { column: 0, descending: true, expanded: false, caption: "" };

  // Regions in the order they were picked, and each one's colour slot (1-4). A region keeps its
  // slot until it's unticked, so removing one never repaints the others.
  let regions = JSON.parse($("initial-regions").textContent);
  const slots = new Map();
  let chart = null;
  let current = null;
  let requestId = 0;

  function assignSlots() {
    for (const code of [...slots.keys()]) if (!regions.includes(code)) slots.delete(code);
    for (const code of regions) {
      if (slots.has(code)) continue;
      const used = new Set(slots.values());
      let slot = 1;
      while (used.has(slot)) slot += 1;
      slots.set(code, slot);
    }
  }

  function syncCheckboxes() {
    const full = regions.length >= MAX;
    for (const box of picks.querySelectorAll("input[type=checkbox]")) {
      box.checked = regions.includes(box.value);
      box.disabled = full && !box.checked;
    }
    $("regions-hint").hidden = !full;
  }

  // --- loading ----------------------------------------------------------------------------

  async function load() {
    const years = C.readYears(inputs.year_from, inputs.year_to, $("years-error"));
    if (!years.ok) return;
    assignSlots();
    syncCheckboxes();
    const params = {
      regions: regions.join(","),
      parameter: inputs.parameter.value,
      period: inputs.period.value,
      year_from: years.year_from,
      year_to: years.year_to,
    };
    C.writeQuery(params);
    const measure = inputs.parameter.selectedOptions[0].textContent.trim();
    const period = inputs.period.selectedOptions[0].textContent.trim();
    setSummary(
      `${regions.length} region${regions.length === 1 ? "" : "s"} · ${measure} · ${period}`,
    );

    if (!regions.length) {
      $("series-title").textContent = "Compare regions";
      $("series-unit").textContent = "";
      $("series-note").hidden = true;
      showStatus("Pick at least one region to compare.", false);
      return;
    }
    const id = ++requestId;
    results.setAttribute("aria-busy", "true");
    try {
      const data = await C.api(
        "compare/",
        Object.fromEntries(Object.entries(params).filter(([, v]) => v !== "")),
      );
      if (id !== requestId) return;
      current = data;
      render();
    } catch (error) {
      if (id !== requestId) return;
      showStatus(C.apiMessage(error) || C.COPY.error, true);
    } finally {
      if (id === requestId) results.setAttribute("aria-busy", "false");
    }
  }

  // --- rendering --------------------------------------------------------------------------

  function showStatus(message, isError) {
    C.showStatus({ message, isError, retry: load, hide: ["chart-wrap", "legend", "table-wrap"] });
  }

  function render() {
    const data = current;
    const first = data.years[0];
    const last = data.years.at(-1);
    const names = data.regions.map((r) => r.name).join(", ");
    $("series-title").textContent = C.titleFor(data, first, last);
    $("series-unit").textContent = `(${data.unit})`;
    const note = C.winterNote(data.period);
    $("series-note").textContent = note;
    $("series-note").hidden = !note;
    $("announce").textContent = `Comparing ${names}.`;

    if (!data.years.length) {
      showStatus(C.COPY.empty, false);
      return;
    }
    $("status").hidden = true;
    for (const id of ["chart-wrap", "legend", "table-wrap"]) $(id).hidden = false;
    results.classList.add("has-data");
    renderLegend();
    renderChart();
    renderRows();
  }

  const colorOf = (code) => C.css(`--series-${slots.get(code)}`);

  function renderLegend() {
    const legend = $("legend");
    legend.textContent = "";
    for (const region of current.regions) {
      const item = document.createElement("li");
      const key = document.createElement("span");
      key.className = "key";
      key.style.color = colorOf(region.code); // the mark carries the colour, the text stays ink
      key.setAttribute("aria-hidden", "true");
      item.append(key, document.createTextNode(region.name));
      legend.append(item);
    }
  }

  function renderChart() {
    const data = current;
    const datasets = data.regions.map((region) => ({
      label: region.name,
      data: data.years.map((year, i) => ({ x: year, y: data.values[region.code][i] })),
      borderColor: colorOf(region.code),
      backgroundColor: colorOf(region.code),
      borderWidth: 2,
      pointRadius: 0,
      pointHoverRadius: 4,
      spanGaps: false,
    }));
    if (chart) chart.destroy();
    // The HTML legend above the chart replaces Chart.js's own.
    chart = new Chart($("chart"), {
      type: "line",
      data: { datasets },
      options: C.chartOptions(data.unit, {
        decimals: C.decimalsFor(data.parameter, data.period),
        xMin: data.years[0],
        xMax: data.years.at(-1),
      }),
      plugins: [C.crosshair],
    });
    $("chart").setAttribute(
      "aria-label",
      `Line chart comparing ${data.regions.map((r) => r.name).join(", ")} in ${data.unit}. The same values are in the table below.`,
    );
  }

  function renderRows() {
    const data = current;
    const rows = data.years.map((year, i) => [
      year,
      ...data.regions.map((r) => data.values[r.code][i]),
    ]);
    table.caption = `${C.titleFor(data)} by region, in ${data.unit}`;
    C.renderTable({
      table: $("data-table"),
      moreButton: $("table-more"),
      caption: $("table-caption"),
      columns: [
        { label: "Year", text: (row) => String(row[0]), sortValue: (row) => row[0] },
        ...data.regions.map((region, index) => ({
          label: region.name,
          numeric: true,
          text: (row) =>
            row[index + 1] === null
              ? "–"
              : C.formatNumber(row[index + 1], C.decimalsFor(data.parameter, data.period)),
          sortValue: (row) => row[index + 1],
        })),
      ],
      rows,
      state: table,
    });
  }

  // --- wiring -----------------------------------------------------------------------------

  const query = C.readQuery();
  for (const key of ["year_from", "year_to"]) inputs[key].value = query.get(key) || "";
  regions = regions.slice(0, MAX);

  picks.addEventListener("change", (event) => {
    const box = event.target;
    if (box.checked && !regions.includes(box.value)) regions.push(box.value);
    if (!box.checked) regions = regions.filter((code) => code !== box.value);
    table.column = 0; // a column may have gone
    load();
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    load();
  });
  for (const key of Object.keys(inputs)) inputs[key].addEventListener("change", load);
  C.bindTable($("data-table"), $("table-more"), table, renderRows);
  C.onSchemeChange(() => {
    if (!current || !current.years.length) return;
    renderLegend();
    renderChart();
  });
  load();
})();

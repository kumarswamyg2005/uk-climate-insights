/* Explorer: one region x measure x period as stripes, a line chart, stats and a table. */
(function () {
  "use strict";

  const C = window.Climate;
  const $ = (id) => document.getElementById(id);
  const form = $("controls");
  const inputs = {
    region: $("region"),
    parameter: $("parameter"),
    period: $("period"),
    year_from: $("year_from"),
    year_to: $("year_to"),
    rolling: $("rolling"),
  };
  const results = $("results");
  const setSummary = C.filtersSheet();
  const table = { column: 0, descending: true, expanded: false, caption: "" };

  let chart = null;
  let current = null; // {series, summary} of the last successful load
  let requestId = 0;

  // --- state <-> URL ----------------------------------------------------------------------

  function restoreFromUrl() {
    const query = C.readQuery();
    for (const key of ["year_from", "year_to"]) inputs[key].value = query.get(key) || "";
    inputs.rolling.checked = query.get("rolling") === "1";
  }

  function selection(years) {
    return {
      region: inputs.region.value,
      parameter: inputs.parameter.value,
      period: inputs.period.value,
      year_from: years.year_from,
      year_to: years.year_to,
    };
  }

  // --- loading ----------------------------------------------------------------------------

  async function load() {
    const years = C.readYears(inputs.year_from, inputs.year_to, $("years-error"));
    if (!years.ok) return;
    const params = selection(years);
    C.writeQuery({ ...params, rolling: inputs.rolling.checked ? "1" : "" });
    updateLinks(params);
    setSummary([params.region, params.parameter, params.period].map(labelOf).join(" · "));

    const id = ++requestId;
    results.setAttribute("aria-busy", "true");
    const query = Object.fromEntries(Object.entries(params).filter(([, v]) => v !== ""));
    try {
      const [series, summary] = await Promise.all([
        C.api("series/", query),
        C.api("summary/", query),
      ]);
      if (id !== requestId) return; // a newer selection has been made since
      current = { series, summary };
      render();
    } catch (error) {
      if (id !== requestId) return;
      showStatus(C.apiMessage(error) || C.COPY.error, true);
    } finally {
      if (id === requestId) results.setAttribute("aria-busy", "false");
    }
  }

  function labelOf(value) {
    const option = form.querySelector(`option[value="${CSS.escape(value)}"]`);
    return option ? option.textContent.trim() : value;
  }

  function updateLinks(params) {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== ""),
    ).toString();
    $("csv-link").href = `/api/v1/series.csv?${query}`;
    const compare = new URLSearchParams({
      regions: params.region,
      parameter: params.parameter,
      period: params.period,
    });
    $("compare-link").href = `/compare/?${compare}`;
  }

  // --- rendering --------------------------------------------------------------------------

  function showStatus(message, isError) {
    const status = $("status");
    status.textContent = message;
    status.classList.toggle("is-error", !!isError);
    if (isError) {
      const retry = document.createElement("button");
      retry.type = "button";
      retry.className = "button";
      retry.textContent = "Try again";
      retry.addEventListener("click", load);
      status.append(document.createElement("br"), retry);
    }
    status.hidden = false;
    for (const id of ["chart-wrap", "stats", "table-wrap"]) $(id).hidden = true;
    results.classList.remove("has-data");
    $("csv-link").setAttribute("aria-disabled", "true");
  }

  function render() {
    const { series, summary } = current;
    const points = series.points;
    const first = points.length ? points[0][0] : null;
    const last = points.length ? points[points.length - 1][0] : null;

    $("series-title").textContent = C.titleFor(series, first, last);
    $("series-unit").textContent = `(${series.unit})`;
    const note = C.winterNote(series.period);
    $("series-note").textContent = note;
    $("series-note").hidden = !note;
    $("announce").textContent = `Showing ${C.titleFor(series, first, last)}.`;

    renderStripes(series, first, last);
    if (!points.length) {
      showStatus(C.COPY.empty, false);
      return;
    }
    $("status").hidden = true;
    for (const id of ["chart-wrap", "stats", "table-wrap"]) $(id).hidden = false;
    results.classList.add("has-data");
    $("csv-link").removeAttribute("aria-disabled");

    renderChart(series);
    renderStats(series, summary);
    renderRows();
  }

  function renderStripes(series, first, last) {
    const stripes = $("stripes");
    const [front, back] = stripes.querySelectorAll(".stripes-layer");
    const values = series.points.map(([, v]) => v);
    back.style.backgroundImage = values.length
      ? C.stripesGradient(C.stripeColors(series.parameter, values))
      : "none";
    // Cross-fade: the back layer becomes the front one (200 ms, off for reduced motion).
    back.classList.add("is-front");
    front.classList.remove("is-front");
    $("stripes-start").textContent = first || "";
    $("stripes-end").textContent = last || "";
    $("stripes-key").textContent = values.length ? C.stripeKey(series.parameter) : "";
    stripes.setAttribute(
      "aria-label",
      values.length
        ? `Climate stripes for ${C.titleFor(series, first, last)}: one stripe per year. ${C.stripeKey(series.parameter)}. The table below lists every value.`
        : "No stripes: no values for this selection.",
    );
  }

  function renderChart(series) {
    const unit = series.unit;
    const data = series.points.map(([x, y]) => ({ x, y }));
    const datasets = [
      {
        label: series.region_name,
        data,
        borderColor: C.css("--signal"),
        backgroundColor: C.css("--signal"),
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
      },
    ];
    if (inputs.rolling.checked) {
      datasets.push({
        label: "10-year rolling mean",
        data: C.rollingMean(series.points).map(([x, y]) => ({ x, y })),
        borderColor: C.css("--slate"),
        backgroundColor: C.css("--slate"),
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        pointHoverRadius: 0,
      });
    }
    if (chart) chart.destroy();
    chart = new Chart($("chart"), {
      type: "line",
      data: { datasets },
      options: C.chartOptions(unit, {
        legend: datasets.length > 1,
        decimals: C.decimalsFor(series.parameter, series.period),
        xMin: series.points[0][0],
        xMax: series.points.at(-1)[0],
      }),
      plugins: [C.crosshair],
    });
    $("chart").setAttribute(
      "aria-label",
      `Line chart of ${C.titleFor(series, series.points[0][0], series.points.at(-1)[0])} in ${unit}. The same values are in the table below.`,
    );
  }

  function renderStats(series, summary) {
    const unit = series.unit;
    const dp = C.decimalsFor(series.parameter, series.period);
    const [highLabel, lowLabel] = C.EXTREME_LABELS[series.parameter];
    const years = (extreme) => {
      const [firstYear, ...others] = extreme.years;
      return others.length
        ? `${firstYear} and ${others.length} other year${others.length > 1 ? "s" : ""}`
        : `${firstYear}`;
    };
    const rows = [
      [highLabel, `${years(summary.max)} · ${C.formatValue(summary.max.value, unit, dp)}`],
      [lowLabel, `${years(summary.min)} · ${C.formatValue(summary.min.value, unit, dp)}`],
      ["Average", C.formatValue(summary.mean, unit, dp)],
      ["Latest", `${summary.latest.year} · ${C.formatValue(summary.latest.value, unit, dp)}`],
      [
        "Trend",
        summary.trend_per_decade === null
          ? "Needs two or more years"
          : `${C.formatSigned(summary.trend_per_decade, unit)} per decade`,
      ],
      ["Years with data", String(summary.count)],
    ];
    const stats = $("stats");
    stats.textContent = "";
    for (const [label, value] of rows) {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = value;
      row.append(dt, dd);
      stats.append(row);
    }
  }

  function renderRows() {
    const { series } = current;
    table.caption = `Values for ${C.titleFor(series)}, in ${series.unit}`;
    C.renderTable({
      table: $("data-table"),
      moreButton: $("table-more"),
      caption: $("table-caption"),
      columns: [
        { label: "Year", text: (p) => String(p[0]), sortValue: (p) => p[0] },
        {
          label: `Value (${series.unit})`,
          numeric: true,
          text: (p) => C.formatNumber(p[1], C.decimalsFor(series.parameter, series.period)),
          sortValue: (p) => p[1],
        },
      ],
      rows: series.points,
      state: table,
    });
  }

  /** Hovering the stripes names the year under the pointer. The table has every value too. */
  function bindStripesHover() {
    const stripes = $("stripes");
    const tip = $("stripes-tip");
    stripes.addEventListener("pointermove", (event) => {
      if (!current || !current.series.points.length) return;
      const { points, unit, parameter, period } = current.series;
      const box = stripes.getBoundingClientRect();
      const x = event.clientX - box.left;
      const index = Math.min(
        points.length - 1,
        Math.max(0, Math.floor((x / box.width) * points.length)),
      );
      const [year, value] = points[index];
      tip.textContent = `${year} \u00b7 ${C.formatValue(value, unit, C.decimalsFor(parameter, period))}`;
      tip.style.left = `${Math.min(Math.max(x, 64), box.width - 64)}px`;
      tip.hidden = false;
    });
    stripes.addEventListener("pointerleave", () => {
      tip.hidden = true;
    });
  }

  // --- wiring -----------------------------------------------------------------------------

  restoreFromUrl();
  bindStripesHover();
  C.bindTable($("data-table"), $("table-more"), table, renderRows);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    load();
  });
  for (const key of ["region", "parameter", "period"]) inputs[key].addEventListener("change", load);
  for (const key of ["year_from", "year_to"]) inputs[key].addEventListener("change", load);
  inputs.rolling.addEventListener("change", () => {
    C.writeQuery({
      ...Object.fromEntries(C.readQuery()),
      rolling: inputs.rolling.checked ? "1" : "",
    });
    if (current && current.series.points.length) renderChart(current.series);
  });
  C.onSchemeChange(() => current && current.series.points.length && renderChart(current.series));
  load();
})();

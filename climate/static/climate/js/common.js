/* Shared helpers for the explorer and compare pages. Plain script (no build step), loaded with defer. */
(function () {
  "use strict";

  const Climate = (window.Climate = {});

  // --- API --------------------------------------------------------------------------------

  Climate.api = async function (path, params) {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    const response = await fetch(`/api/v1/${path}${query}`, {
      headers: { Accept: "application/json" },
    });
    let body = null;
    try {
      body = await response.json();
    } catch (_) {
      // Not JSON (e.g. a proxy error page). The status code is enough.
    }
    if (!response.ok) {
      const error = new Error(`HTTP ${response.status}`);
      error.status = response.status;
      error.body = body;
      throw error;
    }
    return body;
  };

  /** First human-readable message from a DRF error body, e.g. {"year_from": ["..."]}. */
  Climate.apiMessage = function (error) {
    const body = error && error.body;
    if (!body || typeof body !== "object") return null;
    if (typeof body.detail === "string") return body.detail;
    const first = Object.values(body)[0];
    return Array.isArray(first) ? String(first[0]) : null;
  };

  Climate.COPY = {
    empty: "No values for this range. Widen the years or pick another period.",
    error: "Couldn't load the series. Check your connection and try again.",
  };

  // --- formatting -------------------------------------------------------------------------

  const formatters = new Map();
  /** Fixed decimals when given (so table columns align), otherwise up to 2. */
  Climate.formatNumber = function (value, decimals) {
    const key = decimals === undefined ? "auto" : decimals;
    if (!formatters.has(key)) {
      formatters.set(
        key,
        new Intl.NumberFormat(
          "en-GB",
          decimals === undefined
            ? { maximumFractionDigits: 2 }
            : { minimumFractionDigits: decimals, maximumFractionDigits: decimals },
        ),
      );
    }
    return formatters.get(key).format(value);
  };
  Climate.formatValue = (value, unit, decimals) =>
    `${Climate.formatNumber(value, decimals)} ${unit}`;
  Climate.formatSigned = (value, unit) =>
    `${value > 0 ? "+" : value < 0 ? "\u2212" : "\u00b1"}${Climate.formatNumber(Math.abs(value), 2)} ${unit}`;
  /** The files' own precision: temperature seasons and years have 2 decimals, everything else 1. */
  Climate.decimalsFor = (parameter, period) =>
    parameter.startsWith("T") && ["win", "spr", "sum", "aut", "ann"].includes(period) ? 2 : 1;
  Climate.formatDate = (iso) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

  /** "Winter (Dec-Feb)" -> "Winter"; "Max temperature" -> "max temperature". */
  Climate.titleFor = function (data, first, last) {
    const period = data.period_name.split(" (")[0];
    const measure = data.parameter_name.charAt(0).toLowerCase() + data.parameter_name.slice(1);
    const where = data.region_name ? `, ${data.region_name}` : "";
    const when = first ? `, ${first}–${last}` : "";
    return `${period} ${measure}${where}${when}`;
  };

  Climate.winterNote = (period) =>
    period === "win"
      ? "Winter spans two years: winter 2026 is December 2025 to February 2026."
      : "";

  Climate.EXTREME_LABELS = {
    Tmax: ["Warmest", "Coldest"],
    Tmin: ["Warmest", "Coldest"],
    Tmean: ["Warmest", "Coldest"],
    Rainfall: ["Wettest", "Driest"],
    Sunshine: ["Sunniest", "Dullest"],
    Raindays1mm: ["Most rain days", "Fewest rain days"],
    AirFrost: ["Most frost days", "Fewest frost days"],
  };

  // --- URL state --------------------------------------------------------------------------

  Climate.readQuery = () => new URLSearchParams(window.location.search);

  /** Mirror the current selection into the URL so any view can be shared. */
  Climate.writeQuery = function (params) {
    const clean = Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== false);
    const query = new URLSearchParams(clean).toString();
    history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  };

  /** Validate the two year inputs. Returns {ok, year_from, year_to}; shows the error inline. */
  Climate.readYears = function (fromInput, toInput, errorEl) {
    const parse = (input) => {
      const raw = input.value.trim();
      if (raw === "") return { ok: true, value: "" };
      const n = Number(raw);
      return { ok: Number.isInteger(n) && n >= 1800 && n <= 2100, value: n };
    };
    const from = parse(fromInput);
    const to = parse(toInput);
    let message = "";
    if (!from.ok || !to.ok) message = "Years must be whole numbers between 1800 and 2100.";
    else if (from.value !== "" && to.value !== "" && from.value > to.value)
      message = "The first year can't be after the last year.";
    errorEl.textContent = message;
    errorEl.hidden = !message;
    fromInput.setAttribute("aria-invalid", String(!!message));
    toInput.setAttribute("aria-invalid", String(!!message));
    return { ok: !message, year_from: from.value, year_to: to.value };
  };

  // --- climate stripes --------------------------------------------------------------------

  // Diverging scales from DESIGN.md. They're for data only, never for UI chrome.
  const SCALES = {
    temperature: ["#08306B", "#6BAED6", "#F0F0F0", "#FC9272", "#67000D"],
    rain: ["#8C510A", "#F6E8C3", "#C7EAE5", "#01665E"],
    sun: ["#3F3F3F", "#FEE391", "#EC7014"],
  };
  // [scale, direction]: more frost days means colder, so air frost runs the temperature scale backwards.
  const PARAMETER_SCALES = {
    Tmax: ["temperature", 1],
    Tmin: ["temperature", 1],
    Tmean: ["temperature", 1],
    Rainfall: ["rain", 1],
    Raindays1mm: ["rain", 1],
    Sunshine: ["sun", 1],
    AirFrost: ["temperature", -1],
  };
  Climate.STRIPE_KEYS = {
    temperature: "Blue years were colder than average, red years warmer",
    rain: "Brown years were drier than average, green years wetter",
    sun: "Grey years were duller than average, orange years sunnier",
    AirFrost: "Blue years had more frost days than average, red years fewer",
    Raindays1mm: "Brown years had fewer rain days than average, green years more",
  };

  const hexToRgb = (hex) => {
    const n = parseInt(hex.slice(1), 16);
    return [n >> 16, (n >> 8) & 255, n & 255];
  };

  function interpolate(stops, position) {
    const x = Math.min(Math.max(position, 0), 1) * (stops.length - 1);
    const i = Math.min(Math.floor(x), stops.length - 2);
    const [a, b, t] = [hexToRgb(stops[i]), hexToRgb(stops[i + 1]), x - i];
    return `rgb(${a.map((c, k) => Math.round(c + (b[k] - c) * t)).join(",")})`;
  }

  /** One colour per value, by its deviation from the series mean. +/-2.5 SD spans the scale. */
  Climate.stripeColors = function (parameter, values) {
    const [scale, direction] = PARAMETER_SCALES[parameter];
    const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
    const variance = values.reduce((sum, v) => sum + (v - mean) ** 2, 0) / values.length;
    const spread = 5 * Math.sqrt(variance) || 1; // all-equal series (e.g. July frost) stay neutral
    return values.map((v) => interpolate(SCALES[scale], 0.5 + (direction * (v - mean)) / spread));
  };

  Climate.stripeKey = (parameter) =>
    Climate.STRIPE_KEYS[parameter] || Climate.STRIPE_KEYS[PARAMETER_SCALES[parameter][0]];

  Climate.stripesGradient = function (colors) {
    const width = 100 / colors.length;
    const stops = colors.map(
      (c, i) => `${c} ${(i * width).toFixed(3)}% ${((i + 1) * width).toFixed(3)}%`,
    );
    return `linear-gradient(to right, ${stops.join(", ")})`;
  };

  // --- rolling mean -----------------------------------------------------------------------

  /** Trailing mean of this year and the previous size-1 years; null until a full window exists. */
  Climate.rollingMean = function (points, size = 10) {
    return points.map(([year], i) => {
      if (i < size - 1) return [year, null];
      const window = points.slice(i - size + 1, i + 1);
      if (window[0][0] !== year - size + 1) return [year, null]; // a gap in the years
      return [year, window.reduce((sum, [, v]) => sum + v, 0) / size];
    });
  };

  // --- Chart.js ---------------------------------------------------------------------------

  Climate.css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  Climate.withAlpha = function (hex, alpha) {
    const [r, g, b] = hexToRgb(hex);
    return `rgba(${r},${g},${b},${alpha})`;
  };

  /** Vertical hairline at the hovered year: readers aim at a year, not at a 1.5px line. */
  Climate.crosshair = {
    id: "crosshair",
    afterDatasetsDraw(chart) {
      const active = chart.tooltip && chart.tooltip.getActiveElements();
      if (!active || !active.length) return;
      const { ctx, chartArea } = chart;
      ctx.save();
      ctx.strokeStyle = Climate.withAlpha(Climate.css("--slate"), 0.6);
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(active[0].element.x, chartArea.top);
      ctx.lineTo(active[0].element.x, chartArea.bottom);
      ctx.stroke();
      ctx.restore();
    },
  };

  /** Shared axis, grid, tooltip and font settings, read from the current colour scheme. */
  Climate.chartOptions = function (unit, { legend = false, decimals, xMin, xMax } = {}) {
    const slate = Climate.css("--slate");
    const ink = Climate.css("--ink");
    const grid = Climate.withAlpha(slate, 0.2);
    const font = { family: Climate.css("--font-body"), size: 13 };
    return {
      animation: false, // DESIGN.md allows one motion only: the stripes cross-fade
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: {
          type: "linear",
          min: xMin, // the data's first and last year, not a rounded-out range
          max: xMax,
          grid: { color: grid },
          border: { color: grid },
          ticks: { color: slate, font, precision: 0, callback: (v) => String(v) },
        },
        y: {
          grid: { color: grid },
          border: { display: false },
          ticks: { color: slate, font },
          title: { display: true, text: unit, color: slate, font },
        },
      },
      plugins: {
        legend: {
          display: legend,
          align: "start",
          labels: { color: ink, font, boxWidth: 18, boxHeight: 0, useBorderRadius: false },
        },
        tooltip: {
          backgroundColor: Climate.css("--paper"),
          borderColor: Climate.css("--rule"),
          borderWidth: 1,
          titleColor: ink,
          bodyColor: ink,
          titleFont: { ...font, weight: "700" },
          bodyFont: font,
          padding: 10,
          boxWidth: 12,
          boxHeight: 2,
          callbacks: {
            title: (items) => String(items[0].parsed.x),
            label: (item) =>
              item.parsed.y === null
                ? `${item.dataset.label}: no value`
                : `${Climate.formatValue(item.parsed.y, unit, decimals)}  ${item.dataset.label}`,
          },
        },
      },
    };
  };

  Climate.onSchemeChange = (callback) =>
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", callback);

  // --- page chrome ------------------------------------------------------------------------

  /** Mobile: the controls collapse into a sheet under a one-line summary button. */
  Climate.filtersSheet = function () {
    const toggle = document.getElementById("filters-toggle");
    const controls = document.getElementById("controls");
    const summary = document.getElementById("filters-summary");
    if (!toggle) return () => {};
    toggle.addEventListener("click", () => {
      const open = controls.classList.toggle("is-open");
      toggle.setAttribute("aria-expanded", String(open));
    });
    return (text) => {
      summary.textContent = text;
    };
  };

  /** A sortable, expandable table. columns: [{label, value(row) -> text, numeric}]. */
  Climate.renderTable = function ({ table, moreButton, caption, columns, rows, state }) {
    const PAGE = 20;
    const head = table.tHead;
    const body = table.tBodies[0];
    if (!head.rows.length || head.rows[0].cells.length !== columns.length) {
      head.textContent = "";
      const tr = head.insertRow();
      columns.forEach((col, index) => {
        const th = document.createElement("th");
        th.scope = "col";
        if (col.numeric) th.className = "num";
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.sort = String(index);
        button.textContent = col.label;
        th.append(button);
        tr.append(th);
      });
    } else {
      columns.forEach((col, index) => {
        const button = head.rows[0].cells[index].querySelector("button");
        button.dataset.sort = String(index);
        button.textContent = col.label;
      });
    }
    [...head.rows[0].cells].forEach((th, index) => {
      if (index === state.column)
        th.setAttribute("aria-sort", state.descending ? "descending" : "ascending");
      else th.removeAttribute("aria-sort");
    });

    const key = columns[state.column].sortValue;
    const sorted = [...rows].sort((a, b) => {
      const [x, y] = [key(a), key(b)];
      if (x === null) return 1; // blanks last either way
      if (y === null) return -1;
      return state.descending ? y - x : x - y;
    });
    const visible = state.expanded ? sorted : sorted.slice(0, PAGE);

    body.textContent = "";
    for (const row of visible) {
      const tr = body.insertRow();
      for (const col of columns) {
        const td = tr.insertCell();
        if (col.numeric) td.className = "num";
        td.textContent = col.text(row);
      }
    }
    caption.textContent = state.caption || "";
    moreButton.hidden = sorted.length <= PAGE;
    moreButton.textContent = state.expanded
      ? "Show fewer years"
      : `Show all ${sorted.length} years`;
  };

  /** Wire sort buttons and "show all" once; the state object is shared with the page. */
  Climate.bindTable = function (table, moreButton, state, rerender) {
    table.tHead.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-sort]");
      if (!button) return;
      const column = Number(button.dataset.sort);
      state.descending = column === state.column ? !state.descending : true;
      state.column = column;
      rerender();
    });
    moreButton.addEventListener("click", () => {
      state.expanded = !state.expanded;
      rerender();
    });
  };

  /** Footer: when the Met Office last updated the data, and when it was loaded here. */
  async function showDataUpdated() {
    const el = document.getElementById("data-updated");
    if (!el) return;
    try {
      const run = await fetch(el.dataset.endpoint, { headers: { Accept: "application/json" } });
      if (!run.ok) return; // nothing ingested yet: say nothing rather than something wrong
      const data = await run.json();
      el.textContent = data.source_updated_at
        ? `Met Office data last updated ${Climate.formatDate(data.source_updated_at)}, loaded here ${Climate.formatDate(data.finished_at)}.`
        : `Data loaded ${Climate.formatDate(data.finished_at)}.`;
    } catch (_) {
      // The footer note is optional; never let it break the page.
    }
  }

  document.addEventListener("DOMContentLoaded", showDataUpdated);
})();

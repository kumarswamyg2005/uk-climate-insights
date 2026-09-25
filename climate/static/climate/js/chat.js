/* Chat panel: POST /api/v1/chat/, show the answer and, collapsed, the exact data it used. */
(function () {
  "use strict";

  const C = window.Climate;
  const form = document.getElementById("chat-form");
  if (!form) return;
  const input = document.getElementById("chat-input");
  const submit = document.getElementById("chat-submit");
  const log = document.getElementById("chat-log");
  const history = []; // recent turns, sent back so follow-up questions have context
  const MAX_HISTORY = 6;

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text; // model output is text, never HTML
    return node;
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    const item = el("li");
    const answer = el("p", "chat-answer is-pending", "Looking that up…");
    item.append(el("p", "chat-question", message), answer);
    log.prepend(item);
    submit.disabled = true;
    input.value = "";

    try {
      const response = await fetch("/api/v1/chat/", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message, history: history.slice(-MAX_HISTORY) }),
      });
      const body = await response.json().catch(() => null);
      if (!response.ok)
        throw Object.assign(new Error(`HTTP ${response.status}`), {
          status: response.status,
          body,
        });

      answer.className = "chat-answer";
      answer.textContent = body.answer;
      history.push(
        { role: "user", content: message },
        { role: "assistant", content: body.answer.slice(0, 1000) },
      );
      if (body.tool_calls.length) item.append(dataUsed(body));
    } catch (error) {
      answer.className = "chat-answer is-error";
      answer.textContent = messageFor(error);
      input.value = message; // keep the question so it can be sent again
    } finally {
      submit.disabled = false;
      input.focus();
    }
  });

  function messageFor(error) {
    if (error.status === 429)
      return "That's a lot of questions in a minute. Wait a moment and ask again.";
    if (error.status === 400 || error.status === 503) {
      return (
        C.apiMessage(error) ||
        "The chat service isn't configured right now. The charts and API still work."
      );
    }
    return "Couldn't reach the chat service. Check your connection and try again.";
  }

  // --- "Data used" ------------------------------------------------------------------------

  function rowCount(result) {
    if (Array.isArray(result)) return result.length;
    if (result.rows) return result.rows.length;
    if (result.points) return result.points.length;
    if (result.years && result.values)
      return result.years.length * Object.keys(result.values).length;
    return 1; // a summary is one row of statistics
  }

  function dataUsed(body) {
    const details = el("details", "chat-data");
    const rows = body.data.reduce((sum, d) => sum + rowCount(d.result), 0);
    const tools = [...new Set(body.tool_calls.map((call) => call.name))].join(", ");
    details.append(el("summary", "", `Data used (${rows} row${rows === 1 ? "" : "s"}, ${tools})`));

    for (const d of body.data) {
      const args = Object.entries(d.args)
        .map(([key, value]) => `${key}=${Array.isArray(value) ? value.join(",") : value}`)
        .join(", ");
      details.append(el("h3", "", `${d.tool}(${args})`), renderResult(d.result));
    }
    const rejected = body.tool_calls.length - body.data.length;
    if (rejected > 0) {
      details.append(
        el(
          "p",
          "hint",
          `${rejected} call${rejected === 1 ? " was" : "s were"} rejected by validation and retried.`,
        ),
      );
    }
    return details;
  }

  function table(headers, rows) {
    const t = el("table", "data-table");
    const head = t.createTHead().insertRow();
    headers.forEach((h, i) => {
      const th = el("th", i ? "num" : "", h);
      th.scope = "col";
      head.append(th);
    });
    const tbody = t.createTBody();
    for (const row of rows) {
      const tr = tbody.insertRow();
      row.forEach((cell, i) => {
        const td = tr.insertCell();
        if (i) td.className = "num";
        td.textContent = cell === null ? "–" : String(cell);
      });
    }
    return t;
  }

  function renderResult(result) {
    const unit = result.unit ? ` (${result.unit})` : "";
    if (result.rows)
      return table(
        ["Year", `Value${unit}`],
        result.rows.map((r) => [r.year, r.value]),
      );
    if (result.points) return table(["Year", `Value${unit}`], result.points);
    if (result.years && result.values) {
      const codes = Object.keys(result.values);
      return table(
        ["Year", ...result.regions.map((r) => r.name)],
        result.years.map((year, i) => [year, ...codes.map((code) => result.values[code][i])]),
      );
    }
    return el("pre", "", JSON.stringify(result, null, 2)); // a summary or a lookup list
  }
})();

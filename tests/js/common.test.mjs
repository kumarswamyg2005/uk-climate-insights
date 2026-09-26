// Unit tests for the pure helpers in climate/static/climate/js/common.js.
// Run with: node --test tests/js/*.test.mjs   (Node built-in runner, no dependencies)
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

// common.js is a browser script that attaches window.Climate; give it just enough of a window.
const sandbox = { document: { addEventListener() {} }, Intl, console };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(
  readFileSync(new URL("../../climate/static/climate/js/common.js", import.meta.url), "utf8"),
  sandbox,
);
const C = sandbox.Climate;
const plain = (value) => JSON.parse(JSON.stringify(value)); // objects from the sandbox realm

test("rolling mean starts after a full 10-year window", () => {
  const points = Array.from({ length: 12 }, (_, i) => [2000 + i, i]); // values 0..11
  const rolling = C.rollingMean(points);
  assert.equal(rolling[8][1], null);
  assert.deepEqual(plain(rolling[9]), [2009, 4.5]); // mean of 0..9
  assert.deepEqual(plain(rolling[11]), [2011, 6.5]); // mean of 2..11
});

test("rolling mean does not bridge a gap in the years", () => {
  const points = [...Array.from({ length: 10 }, (_, i) => [1990 + i, 1]), [2005, 1]];
  assert.equal(C.rollingMean(points)[10][1], null);
});

test("stripes: the mean is neutral grey, extremes reach the ends of the scale", () => {
  const colors = C.stripeColors("Tmean", [0, 10, 20, 10, 10, 10, 10, 10, 10, 10]);
  assert.equal(colors[1], "rgb(240,240,240)"); // exactly the mean -> #F0F0F0 midpoint
  const hot = C.stripeColors("Tmean", [...Array(99).fill(0), 1000]).at(-1);
  assert.equal(hot, "rgb(103,0,13)"); // clamped at the warm end, #67000D
});

test("stripes: more frost days are drawn cold, not warm", () => {
  const [low, , high] = C.stripeColors("AirFrost", [0, 50, 100]);
  const blue = ([r, , b]) => b > r;
  const rgb = (c) => c.match(/\d+/g).map(Number);
  assert.ok(blue(rgb(high)), `many frost days should be blue, got ${high}`);
  assert.ok(!blue(rgb(low)), `few frost days should be red, got ${low}`);
});

test("stripes: an all-equal series stays neutral instead of dividing by zero", () => {
  assert.deepEqual(plain(C.stripeColors("AirFrost", [0, 0, 0])), Array(3).fill("rgb(240,240,240)"));
});

test("stripes gradient has one hard-edged band per value", () => {
  const gradient = C.stripesGradient(["red", "blue"]);
  assert.equal(gradient, "linear-gradient(to right, red 0.000% 50.000%, blue 50.000% 100.000%)");
});

test("decimals follow the source files", () => {
  assert.equal(C.decimalsFor("Tmax", "ann"), 2);
  assert.equal(C.decimalsFor("Tmean", "win"), 2);
  assert.equal(C.decimalsFor("Tmax", "jan"), 1);
  assert.equal(C.decimalsFor("Rainfall", "ann"), 1);
});

test("number formatting", () => {
  assert.equal(C.formatNumber(1891.8, 1), "1,891.8");
  assert.equal(C.formatNumber(10.1, 2), "10.10");
  assert.equal(C.formatValue(-0.45, "°C", 2), "-0.45 °C");
  assert.equal(C.formatSigned(0.097, "°C"), "+0.10 °C");
  assert.equal(C.formatSigned(-1.5, "mm"), "−1.50 mm");
  assert.equal(C.formatSigned(0, "days"), "±0.00 days");
});

test("titles read naturally for seasons and measures", () => {
  const data = {
    period_name: "Winter (Dec-Feb)",
    parameter_name: "Max temperature",
    region_name: "Wales",
  };
  assert.equal(C.titleFor(data, 1885, 2026), "Winter max temperature, Wales, 1885–2026");
  assert.equal(C.titleFor({ ...data, region_name: undefined }), "Winter max temperature");
  assert.match(C.winterNote("win"), /December 2025 to February 2026/);
  assert.equal(C.winterNote("ann"), "");
});

function yearInputs(from, to) {
  const input = (value) => ({
    value,
    attributes: {},
    setAttribute(k, v) {
      this.attributes[k] = v;
    },
  });
  return [input(from), input(to), { textContent: "", hidden: true }];
}

test("year inputs: blank means 'all years', valid ranges pass", () => {
  assert.deepEqual(plain(C.readYears(...yearInputs("", ""))), {
    ok: true,
    year_from: "",
    year_to: "",
  });
  assert.deepEqual(plain(C.readYears(...yearInputs("1990", "2000"))), {
    ok: true,
    year_from: 1990,
    year_to: 2000,
  });
});

test("year inputs: reversed, fractional and out-of-range years are rejected inline", () => {
  for (const [from, to, message] of [
    ["2000", "1990", "can't be after"],
    ["1990.5", "", "whole numbers"],
    ["1066", "", "between 1800 and 2100"],
  ]) {
    const [a, b, error] = yearInputs(from, to);
    assert.equal(C.readYears(a, b, error).ok, false);
    assert.match(error.textContent, new RegExp(message));
    assert.equal(error.hidden, false);
    assert.equal(a.attributes["aria-invalid"], "true");
  }
});

test("API error messages are taken from DRF's error bodies", () => {
  assert.equal(C.apiMessage({ body: { detail: "Busy." } }), "Busy.");
  assert.equal(C.apiMessage({ body: { region: ['Unknown region "X".'] } }), 'Unknown region "X".');
  assert.equal(C.apiMessage({ body: null }), null);
  assert.equal(C.apiMessage(new Error("network")), null);
});

test("every measure has labels for its highest and lowest years", () => {
  for (const code of ["Tmax", "Tmin", "Tmean", "Sunshine", "Rainfall", "Raindays1mm", "AirFrost"]) {
    assert.equal(C.EXTREME_LABELS[code].length, 2, code);
    assert.ok(C.stripeKey(code).length > 20, code);
  }
});

"""Browser tests: a real Chromium against Django's live test server, with real Met Office data.

Excluded from the default run (they need a browser). Run them with:
    python -m playwright install chromium     # once
    pytest -m e2e
"""

import re

import pytest
from playwright.sync_api import Page, expect

from climate.chat import llm
from climate.ingest import run_ingest

from ..conftest import fixture_text, serve
from ..test_chat import WETTEST, FakeLLM, call, say

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


@pytest.fixture
def data(metoffice):
    """Real files: Tmax for UK and Wales (compare needs two), Rainfall for Scotland."""
    serve(metoffice, "Tmax", "UK", body=fixture_text("Tmax_UK.txt"))
    serve(metoffice, "Tmax", "Wales", body=fixture_text("Tmax_UK.txt"))
    serve(metoffice, "Rainfall", "Scotland", body=fixture_text("Rainfall_Scotland.txt"))
    run_ingest(["UK", "Wales"], ["Tmax"])
    run_ingest(["Scotland"], ["Rainfall"])


@pytest.fixture
def errors(page: Page):
    """Collects console errors and failed requests; each test asserts there were none."""
    seen = []
    page.on("console", lambda m: m.type == "error" and seen.append(m.text))
    page.on("pageerror", lambda e: seen.append(str(e)))
    return seen


def test_explorer_draws_stripes_chart_stats_and_table(page: Page, live_server, data, errors):
    page.goto(f"{live_server.url}/?region=UK&parameter=Tmax&period=ann")

    expect(page.locator("#series-title")).to_have_text(
        "Annual max temperature, UK, 1884\N{EN DASH}2025"
    )
    expect(page.locator("#chart-wrap")).to_be_visible()
    stripes = page.locator(".stripes-layer.is-front")
    expect(stripes).to_have_css("background-image", re.compile("linear-gradient"))
    expect(page.locator("#stats")).to_contain_text("Warmest")
    expect(page.locator("#stats")).to_contain_text("2025 \N{MIDDLE DOT} 14.01 \N{DEGREE SIGN}C")
    expect(page.locator("#data-table tbody tr")).to_have_count(20)

    page.get_by_role("button", name="Show all 142 years").click()
    expect(page.locator("#data-table tbody tr")).to_have_count(142)
    assert errors == []


def test_changing_the_selection_updates_the_url_and_the_chart(
    page: Page, live_server, data, errors
):
    page.goto(f"{live_server.url}/?region=UK&parameter=Tmax&period=ann")
    expect(page.locator("#chart-wrap")).to_be_visible()

    page.select_option("#region", "Scotland")
    page.select_option("#parameter", "Rainfall")

    expect(page.locator("#series-title")).to_have_text(
        "Annual rainfall, Scotland, 1836\N{EN DASH}2025"
    )
    expect(page).to_have_url(re.compile(r"region=Scotland&parameter=Rainfall&period=ann"))
    expect(page.locator("#csv-link")).to_have_attribute(
        "href", re.compile(r"series\.csv\?region=Scotland&parameter=Rainfall")
    )
    assert errors == []


def test_table_sorts_by_value(page: Page, live_server, data):
    page.goto(f"{live_server.url}/?region=Scotland&parameter=Rainfall&period=ann")
    page.get_by_role("button", name="Value (mm)").click()  # first click sorts high to low
    expect(page.locator("#data-table tbody tr").first).to_contain_text("1990")
    expect(page.locator("#data-table th").nth(1)).to_have_attribute("aria-sort", "descending")


def test_bad_years_show_an_inline_error_and_empty_ranges_say_so(page: Page, live_server, data):
    page.goto(f"{live_server.url}/?region=UK&parameter=Tmax&period=ann")
    page.fill("#year_from", "2000")
    page.fill("#year_to", "1990")
    page.press("#year_to", "Tab")
    expect(page.locator("#years-error")).to_have_text(
        "The first year can't be after the last year."
    )

    page.fill("#year_from", "1700")
    page.fill("#year_to", "")
    page.press("#year_to", "Tab")
    expect(page.locator("#years-error")).to_contain_text("between 1800 and 2100")

    page.fill("#year_from", "1800")
    page.fill("#year_to", "1850")
    page.press("#year_to", "Tab")
    expect(page.locator("#status")).to_have_text(
        "No values for this range. Widen the years or pick another period."
    )


def test_compare_keeps_each_regions_colour_when_another_is_removed(
    page: Page, live_server, data, errors
):
    page.goto(f"{live_server.url}/compare/?regions=UK,Wales,Scotland&parameter=Tmax&period=ann")
    legend = page.locator("#legend li")
    expect(legend).to_have_count(3)

    def colours():
        return {
            item.inner_text(): item.locator(".key").evaluate("k => getComputedStyle(k).color")
            for item in legend.all()
        }

    before = colours()
    page.get_by_label("Wales", exact=True).uncheck()
    expect(legend).to_have_count(2)
    after = colours()
    assert after == {name: before[name] for name in ("UK", "Scotland")}
    assert errors == []


def test_chat_shows_the_answer_and_the_data_it_used(page: Page, live_server, data, monkeypatch):
    # The live server runs in this process, so the fake LLM stands in for Groq there too.
    fake = FakeLLM(call("get_extreme", **WETTEST, limit=1), say("1990 was the wettest year."))
    monkeypatch.setattr(llm, "default_client", lambda: fake)

    page.goto(f"{live_server.url}/")
    page.fill("#chat-input", "Which was the wettest year in Scotland?")
    page.get_by_role("button", name="Ask").click()

    expect(page.locator(".chat-answer")).to_have_text("1990 was the wettest year.")
    page.get_by_text("Data used (1 row, get_extreme)").click()
    expect(page.locator(".chat-data table tbody tr")).to_have_text(re.compile(r"1990\s*1891\.8"))


def test_chat_unavailable_message(page: Page, live_server, settings):
    settings.GROQ_API_KEY = ""
    page.goto(f"{live_server.url}/")
    page.fill("#chat-input", "Anything")
    page.press("#chat-input", "Enter")
    expect(page.locator(".chat-answer")).to_have_text(
        "The chat service isn't configured right now. The charts and API still work."
    )


def test_mobile_controls_open_from_the_summary_bar(page: Page, live_server, data):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server.url}/?region=UK&parameter=Tmax&period=ann")
    toggle = page.locator("#filters-toggle")
    expect(page.locator("#controls")).to_be_hidden()
    expect(toggle).to_contain_text("UK \N{MIDDLE DOT} Max temperature \N{MIDDLE DOT} Annual")

    toggle.click()
    expect(page.locator("#controls")).to_be_visible()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")

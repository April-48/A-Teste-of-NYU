"""Optional browser QA: pip install playwright; python check_browser.py.

Requires Chrome and a running app at http://127.0.0.1:8050.
Clicks actual rendered chart marks; saves the two submission screenshots.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8050")
        page.wait_for_selector("#scatter .scatterlayer .point", timeout=10000)
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")
        expect(page.locator("#metrics")).to_contain_text("31,360")
        # The graph's actual rendered bounds must remain inside its section.
        assert page.evaluate("""() => [...document.querySelectorAll('.panel')].every(panel => {
          const g=panel.querySelector('.dash-graph').getBoundingClientRect();
          const p=panel.getBoundingClientRect(); return g.bottom <= p.bottom + 1;
        })"""), "A plot overflows its section"
        page.screenshot(path=str(ROOT / "screenshots/01-default.jpg"), full_page=True)

        # Bar selection must update the other two views without removing context.
        page.locator("#bar .barlayer .point").nth(1).click()
        expect(page.locator("#selection")).to_have_text("All NYC · Chinese")
        assert page.locator("#scatter .point").count() > 10
        # The selected Chinese point can initiate the reverse interaction after Reset.
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")
        page.locator("#scatter .scatterlayer .point").first.click()
        expect(page.locator("#selection")).to_have_text("All NYC · American")
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")

        def cell(borough, cuisine, click=True):
            point = page.locator("#heatmap .js-plotly-plot").evaluate("""(g, [borough,cuisine]) => {
              const r=g.getBoundingClientRect(), x=g._fullLayout.xaxis, y=g._fullLayout.yaxis;
              return {x:r.x+x._offset+x.d2p(cuisine), y:r.y+y._offset+y.d2p(borough)};
            }""", [borough, cuisine])
            page.mouse.move(point["x"], point["y"])
            if click:
                page.mouse.click(point["x"], point["y"])

        cell("Brooklyn", "Chinese", click=False)
        expect(page.locator("#heatmap .hoverlayer")).to_contain_text("Share of borough")
        expect(page.locator("#heatmap .hoverlayer")).to_contain_text("Brooklyn")
        cell("Brooklyn", "Chinese")
        expect(page.locator("#selection")).to_have_text("Brooklyn · Chinese")
        expect(page.locator("#borough")).to_contain_text("Brooklyn")
        expect(page.locator("#metrics")).to_contain_text("8,021")
        expect(page.locator("#bar-scope")).to_contain_text("Brooklyn")
        expect(page.locator("#scatter-scope")).to_contain_text("Brooklyn")
        page.wait_for_function("""() => document.querySelector('#scatter .js-plotly-plot').data.some(t => t.text?.includes('Chinese') && t.marker.line.color === '#111111')""")
        assert page.locator("#bar .js-plotly-plot").evaluate("g => g.data[0].marker.color.includes('#355e6a')")
        assert page.locator("#heatmap .js-plotly-plot").evaluate("g => g.layout.shapes.length === 10")
        expect(page.locator("#missing-note")).to_contain_text("992")
        expect(page.locator("#scatter")).to_contain_text("Brooklyn overall · 90.2%")
        selected = page.locator("#scatter .scatterlayer .trace").last.locator(".point").first
        bounds = selected.bounding_box()
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        expect(page.locator("#scatter .hoverlayer")).to_contain_text("Rated (A/B/C)")
        expect(page.locator("#scatter .hoverlayer")).to_contain_text("Chinese")
        bounds = page.locator("#bar .barlayer .point").first.bounding_box()
        page.mouse.move(bounds["x"] + bounds["width"] / 2, bounds["y"] + bounds["height"] / 2)
        expect(page.locator("#bar .hoverlayer")).to_contain_text("Restaurants:")
        page.mouse.move(20, 20)
        page.screenshot(path=str(ROOT / "screenshots/02-brooklyn-chinese.jpg"), full_page=True)

        cell("Brooklyn", "Italian")
        expect(page.locator("#selection")).to_have_text("Brooklyn · Italian")
        expect(page.locator("#bar")).to_contain_text("Selected cuisine · Rank 11")
        page.locator("#bar .barlayer .point").nth(4).click()
        expect(page.locator("#selection")).to_have_text("Brooklyn · Caribbean")
        expect(page.locator("#heatmap-title")).to_contain_text("+ selected")
        page.get_by_role("checkbox", name="At least 10 graded restaurants").check()
        expect(page.locator("#sample-status")).to_contain_text("24 cuisines hidden")
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")
        expect(page.get_by_role("checkbox", name="At least 10 graded restaurants")).not_to_be_checked()
        expect(page.locator("#metrics")).to_contain_text("31,360")
        # Reclicking the same cell after Reset must work (stale clickData regression).
        cell("Brooklyn", "Chinese")
        expect(page.locator("#selection")).to_have_text("Brooklyn · Chinese")
        counts = {"Bronx": "2,637", "Brooklyn": "8,021", "Manhattan": "12,576", "Queens": "7,005", "Staten Island": "1,121"}
        for borough, count in counts.items():
            page.locator("#borough").click()
            page.get_by_role("option", name=borough, exact=True).click()
            expect(page.locator("#selection")).to_have_text(f"{borough} · All cuisines")
            expect(page.locator("#metrics")).to_contain_text(count)
            expect(page.locator("#scatter-scope")).to_contain_text(borough)
        page.get_by_role("button", name="Reset", exact=True).click()
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")
        page.reload()
        expect(page.locator("#selection")).to_have_text("All NYC · All cuisines")
        page.set_viewport_size({"width": 390, "height": 844})
        # Plotly resizes asynchronously after the viewport changes.
        page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth", timeout=7000)
        page.locator("#heatmap").scroll_into_view_if_needed()
        assert page.locator("#heatmap .heatmaplayer").is_visible()
        assert not errors, errors
        browser.close()
        print("PASS: initial render, all 5 boroughs, all three chart clicks, highlights, Top 10 additions, sample filter, all hovers, Reset, repeated selection, reload, narrow layout. No browser errors.")


if __name__ == "__main__":
    run()

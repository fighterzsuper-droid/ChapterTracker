"""End-to-end Study Board smoke test in a real headless Chromium browser.

Required environment: running Flask app on http://127.0.0.1:5000 with
HUB_ACCESS_PASSWORD=browser-test-password, HUB_ALLOW_HTTP=1.
"""
import time
from playwright.sync_api import sync_playwright

APP = "http://127.0.0.1:5000"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(APP + "/login", wait_until="domcontentloaded")
    page.locator("#password").fill("browser-test-password")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url(APP + "/")
    page.goto(APP + "/study-board?subject=AA&chapter=7", wait_until="domcontentloaded")
    page.locator(".board-root").wait_for(state="visible", timeout=15000)
    print("Reached Study Board after private login")
    success = False
    message = ""
    deadline = time.monotonic() + 80
    while time.monotonic() < deadline:
        page.wait_for_timeout(3000)
        message = page.locator("#board-sheet-status").inner_text()
        print("Spreadsheet status:", message)
        if "Opened" in message or "ready" in message.lower():
            if page.locator("#board-sheet-editor").evaluate("(el) => el.children.length > 0"):
                success = True
                break
        if "failed" in message.lower() or "error" in message.lower():
            break
    print("Page errors:", errors[:12])
    print("Sheet status:", message)
    print("Globals:", page.evaluate("({presets:!!window.UniverPresets,core:!!window.UniverCore,corePreset:!!window.UniverPresetSheetsCore,locale:!!window.UniverPresetSheetsCoreEnUS})"))
    if not success:
        page.screenshot(path="/tmp/jay-board-error.png", full_page=True)
        raise AssertionError("Univer spreadsheet did not mount: " + message)
    # The PDF pane, split handle, upload controls, and workbook grid coexist.
    assert page.locator("#board-pdf-scroll").is_visible()
    assert page.locator("#board-split-handle").is_visible()
    assert page.locator("#board-sheet-editor").is_visible()
    page.locator("[data-layout=pdf]").click()
    assert page.locator(".board-pane-pdf").is_visible()
    page.locator("[data-layout=sheet]").click()
    assert page.locator(".board-pane-sheet").is_visible()
    page.locator("[data-layout=split]").click()
    print("Browser smoke test: private login, editor and view toggles passed")
    browser.close()

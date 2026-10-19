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
        if "failed" in message.lower() or "error" in message.lower() or "[redi]" in message.lower():
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
    # Expand the entire workspace: the PDF and spreadsheet must grow together.
    regular_height = page.locator(".board-stage").bounding_box()["height"]
    page.locator("#board-expand-view").click()
    assert "board-expanded" in (page.locator(".board-root").get_attribute("class") or "")
    assert page.locator("#board-expand-view").get_attribute("aria-pressed") == "true"
    assert page.locator(".board-library").is_hidden()
    expanded_height = page.locator(".board-stage").bounding_box()["height"]
    assert expanded_height > regular_height + 20, (regular_height, expanded_height)
    assert page.locator("#board-sheet-editor").is_visible()
    assert page.locator("#board-pdf-scroll").is_visible()

    # In expanded mode, the Library can be restored without shrinking panels
    # to their pre-expanded height.
    page.locator("#board-toggle-library").click()
    assert page.locator(".board-library").is_visible()
    page.locator("#board-toggle-library").click()
    assert page.locator(".board-library").is_hidden()
    page.locator("#board-expand-view").click()
    assert "board-expanded" not in (page.locator(".board-root").get_attribute("class") or "")
    assert page.locator(".board-library").is_visible()
    assert page.locator(".board-stage").get_attribute("data-layout") == "split"

    # Expand either panel, then restore with the same button or Escape.
    page.locator("#board-expand-reader").click()
    assert "board-expanded" in (page.locator(".board-root").get_attribute("class") or "")
    assert page.locator(".board-stage").get_attribute("data-layout") == "pdf"
    assert page.locator(".board-pane-sheet").is_hidden()
    page.locator("#board-expand-reader").click()
    assert page.locator(".board-stage").get_attribute("data-layout") == "split"
    assert page.locator(".board-pane-sheet").is_visible()

    page.locator("#board-expand-sheet").click()
    assert page.locator(".board-stage").get_attribute("data-layout") == "sheet"
    assert page.locator(".board-pane-pdf").is_hidden()
    page.keyboard.press("Escape")
    assert page.locator(".board-stage").get_attribute("data-layout") == "split"
    assert "board-expanded" not in (page.locator(".board-root").get_attribute("class") or "")
    assert page.locator("#board-sheet-editor").evaluate("(el) => el.children.length > 0")

    # Resizing the divider is keyboard accessible and persists the preference.
    page.locator("#board-split-handle").focus()
    page.keyboard.press("ArrowRight")
    width = page.locator("#board-split-handle").get_attribute("aria-valuenow")
    assert float(width) > 50
    assert page.evaluate("localStorage.getItem('jay-board-reader-width')") == width
    print("Expansion/restore, library visibility, keyboard escape and splitter persistence passed")
    print("Browser smoke test: private login, editor and view toggles passed")
    # Verify an actual XLSX can be imported into the in-app workbook model.
    import base64
    excel64 = page.evaluate("""() => {
      const source = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(source, XLSX.utils.aoa_to_sheet([
        ["Topic", "Hours"], ["Audit planning", 2], ["Evidence", 3],
        ["Total", {f:"SUM(B2:B3)", v:5}]
      ]), "Revision");
      return XLSX.write(source, {bookType:"xlsx", type:"base64"});
    }""")
    page.locator("#board-import-xlsx").set_input_files({
        "name": "revision.xlsx",
        "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "buffer": base64.b64decode(excel64),
    })
    page.wait_for_timeout(4500)
    import_status = page.locator("#board-sheet-status").inner_text()
    print("After XLSX import:", import_status)
    assert "imported" in import_status.lower() or "opened" in import_status.lower(), import_status
    with page.expect_download(timeout=20000) as received:
        page.locator("#board-export-xlsx").click()
    download = received.value
    assert download.suggested_filename.endswith(".xlsx")

    # Build a tiny valid PDF in memory and check that PDF.js can render it.
    stream = b"BT /F1 20 Tf 72 710 Td (Jay PDF Study Board) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    contents = bytearray(b"%PDF-1.4\n")
    starts = [0]
    for i, obj in enumerate(objects, 1):
        starts.append(len(contents))
        contents.extend(str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    xref_at = len(contents)
    contents.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in starts[1:]:
        contents.extend(f"{offset:010} 00000 n \n".encode())
    contents.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" +
                    str(xref_at).encode() + b"\n%%EOF")
    page.locator("#board-upload").set_input_files({
        "name": "study-page.pdf", "mimeType": "application/pdf", "buffer": bytes(contents)
    })
    page.locator(".board-pdf-page canvas").first.wait_for(state="visible", timeout=35000)
    page.locator("[data-pdf-zoom-in]").click()
    assert page.locator("#board-pdf-zoom").input_value() != "fit"
    print("Verified XLSX import/export, PDF rendering and PDF zoom")
    browser.close()

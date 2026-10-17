"""Verify pinned public browser dependencies are downloadable for Study Board.

Runs in CI; does not transmit any private files or passwords.
"""
from urllib.request import Request, urlopen

URLS = [
    "https://unpkg.com/react@18.3.1/umd/react.production.min.js",
    "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js",
    "https://unpkg.com/rxjs@7.8.1/dist/bundles/rxjs.umd.min.js",
    "https://unpkg.com/echarts@5.6.0/dist/echarts.min.js",
    "https://unpkg.com/@univerjs/presets@0.25.1/lib/umd/index.js",
    "https://unpkg.com/@univerjs/core@0.25.1/lib/umd/index.js",
    "https://unpkg.com/@univerjs/preset-sheets-core@0.25.1/lib/umd/index.js",
    "https://unpkg.com/@univerjs/preset-sheets-core@0.25.1/lib/umd/locales/en-US.js",
    "https://unpkg.com/@univerjs/preset-sheets-core@0.25.1/lib/index.css",
    "https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js",
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs",
    "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs",
]

for url in URLS:
    with urlopen(Request(url, headers={"User-Agent": "JayStudyHub-DependencyCheck/1"}), timeout=16) as response:
        if response.status != 200:
            raise RuntimeError(str(response.status) + " " + url)
        prefix = response.read(128)
        if not prefix:
            raise RuntimeError("No content: " + url)
        print(response.status, response.headers.get("Content-Length", "?"), url)

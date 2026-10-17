/* Jay Study Board — private documents, notes, Univer Sheets and XLSX round-trip.
   Browser editor is Excel-like, not Microsoft Excel: VBA, Power Query, and complex
   XLSX features may not import/export losslessly. */
(async function () {
  "use strict";
  const root = document.querySelector(".board-root");
  if (!root) return;

  const el = id => document.getElementById(id);
  const q = selector => document.querySelector(selector);
  let subject = root.dataset.subject, chapter = root.dataset.chapter;
  let files = [], workbooks = [], selectedDoc = null, selectedWorkbook = null;
  let pdf = null, univer = null, univerAPI = null, workbookFacade = null;
  let workbookSnapshot = "", noteLastText = "", currentFileType = null;
  let savingWorkbook = false, loadingWorkbook = false, savingNote = false;
  let statusTimer = 0;

  function status(message, error = false) {
    const display = q("[data-board-status]");
    display.textContent = message;
    display.style.color = error ? "#ffadad" : "";
  }
  function sheetStatus(message, error = false) {
    const display = el("board-sheet-status");
    display.textContent = message;
    display.style.color = error ? "#ffadad" : "";
  }
  function errorMessage(e) {
    return e?.message || "Unexpected problem";
  }
  async function requestJSON(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", cache: "no-store", ...options });
    const isJSON = response.headers.get("content-type")?.includes("application/json");
    const data = isJSON ? await response.json() : {};
    if (!response.ok) throw Error(data.error || ("Request failed (" + response.status + ")"));
    return data;
  }
  function sendJSON(method, url, data) {
    return requestJSON(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }
  function params() {
    return "?subject=" + encodeURIComponent(subject) + "&chapter=" + encodeURIComponent(chapter);
  }
  function contextRedirect() {
    location.assign("/study-board" + params());
  }
  function chapterOptions() {
    const chapterSelect = el("board-chapter");
    chapterSelect.replaceChildren();
    const tx = [
      "1A", "1B", "1C", "1D", "1E", "1F", "1G", "1H", "1I",
      ...Array.from({length: 17}, (_, i) => String(i + 2))
    ];
    const aa = Array.from({length: 15}, (_, i) => String(i + 1));
    for (const key of subject === "AA" ? aa : tx) {
      const opt = document.createElement("option");
      opt.value = key;
      opt.textContent = "Chapter " + key;
      chapterSelect.appendChild(opt);
    }
    chapterSelect.value = chapter;
    if (!chapterSelect.value) {
      chapter = subject === "AA" ? "1" : "1A";
      chapterSelect.value = chapter;
    }
  }

  function fileType(file) {
    const value = file.filename.toLowerCase();
    return value.endsWith(".pdf") ? "PDF" :
      value.endsWith(".md") || value.endsWith(".txt") ? "Note" : "File";
  }
  function fileButton(item, type) {
    const outer = document.createElement("div");
    outer.className = "board-file" + (
      (type === "document" && selectedDoc?.id === item.id) ||
      (type === "workbook" && selectedWorkbook?.id === item.id) ? " active" : "");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "board-file-select";
    const strong = document.createElement("strong");
    strong.textContent = item.name;
    const small = document.createElement("small");
    small.textContent = type === "workbook" ? "Editable workbook" : fileType(item);
    button.append(strong, small);
    button.addEventListener("click", async () => {
      try {
        if (type === "workbook") await openWorkbook(item.id);
        else await openDocument(item);
      } catch (e) { status(errorMessage(e), true); }
    });
    outer.append(button);
    if (type === "document" && !item.builtin) {
      const remove = document.createElement("button");
      remove.className = "board-file-remove";
      remove.type = "button";
      remove.title = "Remove file";
      remove.textContent = "×";
      remove.addEventListener("click", async () => {
        if (!confirm("Permanently delete " + item.name + " from this chapter?")) return;
        try {
          await requestJSON("/api/study-board/documents/" + item.id, { method: "DELETE" });
          if (selectedDoc?.id === item.id) {
            selectedDoc = null; currentFileType = null;
            showPDF();
            pdf?.close();
          }
          await refreshLists();
          status("File deleted");
        } catch (e) { status(errorMessage(e), true); }
      });
      outer.append(remove);
    }
    return outer;
  }
  function renderLists() {
    const docList = el("board-documents"), workbookList = el("board-workbooks");
    docList.replaceChildren(...files.map(file => fileButton(file, "document")));
    workbookList.replaceChildren(...workbooks.map(file => fileButton(file, "workbook")));
    if (!files.length) {
      const notice = document.createElement("p");
      notice.className = "muted"; notice.textContent = "No PDFs or notes yet.";
      docList.append(notice);
    }
    if (!workbooks.length) {
      const notice = document.createElement("p");
      notice.className = "muted"; notice.textContent = "No workbooks yet.";
      workbookList.append(notice);
    }
    el("board-file-count").textContent = (files.length + workbooks.length) + " files";
  }
  async function refreshLists() {
    const [docs, booklist] = await Promise.all([
      requestJSON("/api/study-board/documents" + params()),
      requestJSON("/api/study-board/workbooks" + params()),
    ]);
    files = docs.documents;
    workbooks = booklist.workbooks;
    renderLists();
  }

  function showPDF() {
    el("board-note-editor").hidden = true;
    q(".board-reader-scroll").hidden = false;
    q(".board-reader-find").hidden = false;
  }
  function showNote() {
    q(".board-reader-scroll").hidden = true;
    q(".board-reader-find").hidden = true;
    el("board-note-editor").hidden = false;
  }
  async function openDocument(item) {
    if (selectedDoc && !selectedDoc.builtin && currentFileType === "Note" &&
        el("board-note-text").value !== noteLastText) await saveNote();
    selectedDoc = item;
    currentFileType = fileType(item);
    el("board-pdf-title").textContent = item.name;
    if (currentFileType === "PDF") {
      showPDF();
      if (!pdf) {
        const mod = await import("/static/pdf_viewer.js");
        pdf = new mod.StudyPDF(el("board-pdf-scroll"), message => {
          el("board-pdf-message").textContent = message;
        });
      }
      await pdf.open(item.view_url, item.name);
    } else if (currentFileType === "Note") {
      pdf?.close();
      const response = await fetch(item.view_url, { credentials: "same-origin" });
      if (!response.ok) throw Error("Couldn't load note");
      const text = await response.text();
      noteLastText = text;
      el("board-note-text").value = text;
      el("board-note-text").readOnly = Boolean(item.builtin);
      el("board-save-note").hidden = Boolean(item.builtin);
      el("board-note-status").textContent = item.builtin ? "Existing TX notes · read-only" : "Ready to edit";
      showNote();
    } else {
      status("Spreadsheet files: use Import Excel to open as an editable workbook");
      window.open(item.view_url + "?download=1", "_blank", "noopener");
    }
    renderLists();
  }
  async function saveNote() {
    if (!selectedDoc || selectedDoc.builtin || currentFileType !== "Note" || savingNote) return;
    savingNote = true;
    el("board-note-status").textContent = "Saving note…";
    try {
      const text = el("board-note-text").value;
      await sendJSON("PUT", "/api/study-board/notes/" + selectedDoc.id, { text });
      noteLastText = text;
      el("board-note-status").textContent = "Saved to Study Board";
    } catch (e) {
      el("board-note-status").textContent = "Could not save: " + errorMessage(e);
      throw e;
    } finally { savingNote = false; }
  }

  async function createNote() {
    const name = prompt("Name your chapter notes:", "Chapter " + chapter + " notes");
    if (name === null) return;
    const result = await sendJSON("POST", "/api/study-board/notes", {
      subject, chapter, name: name.trim() || "My chapter notes",
      text: "# Chapter " + chapter + " notes\n\n"
    });
    await refreshLists();
    await openDocument(result.document);
    status("New note created");
  }

  function freshSnapshot(name) {
    return {
      id: "study-" + (crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2)),
      name: name,
      sheets: {
        "sheet-1": { id: "sheet-1", name: "Sheet1", rowCount: 200, columnCount: 30, cellData: {} }
      },
      sheetOrder: ["sheet-1"]
    };
  }
  function fromExcel(file, name) {
    if (!window.XLSX) throw Error("Excel import library did not load");
    const parsed = XLSX.read(file, { type: "array", cellFormula: true, cellStyles: true });
    const workbook = freshSnapshot(name);
    workbook.sheets = {}; workbook.sheetOrder = [];
    parsed.SheetNames.forEach((sheetName, index) => {
      const source = parsed.Sheets[sheetName];
      const sid = "sheet-" + (index + 1);
      const cells = {};
      let maxRow = 0, maxColumn = 0;
      for (const [address, cell] of Object.entries(source)) {
        if (address.startsWith("!")) continue;
        const { r, c } = XLSX.utils.decode_cell(address);
        if (r > 25000 || c > 1000) continue;
        cells[r] ||= {};
        const saved = {};
        if (cell.v !== undefined) saved.v = cell.v;
        if (cell.f) saved.f = "=" + cell.f;
        if (cell.t === "n") saved.t = 2;
        else if (cell.t === "s") saved.t = 1;
        cells[r][c] = saved;
        maxRow = Math.max(maxRow, r);
        maxColumn = Math.max(maxColumn, c);
      }
      workbook.sheets[sid] = {
        id: sid, name: sheetName,
        rowCount: Math.max(200, maxRow + 40),
        columnCount: Math.max(30, maxColumn + 10),
        cellData: cells
      };
      workbook.sheetOrder.push(sid);
    });
    if (!workbook.sheetOrder.length) return freshSnapshot(name);
    return workbook;
  }
  function toExcel(snapshot) {
    if (!window.XLSX) throw Error("Excel export library did not load");
    const book = XLSX.utils.book_new();
    let count = 0;
    const sheets = snapshot.sheets || {};
    const sheetIds = snapshot.sheetOrder || Object.keys(sheets);
    for (const id of sheetIds) {
      const sheet = sheets[id];
      if (!sheet) continue;
      const converted = {};
      let maxRow = 0, maxCol = 0;
      for (const [row, cols] of Object.entries(sheet.cellData || {})) {
        for (const [column, cell] of Object.entries(cols || {})) {
          if (!cell || (cell.v === undefined && !cell.f)) continue;
          const address = XLSX.utils.encode_cell({ r: Number(row), c: Number(column) });
          const record = {};
          if (cell.v !== undefined && cell.v !== null) {
            record.v = cell.v;
            record.t = typeof cell.v === "number" ? "n" :
              typeof cell.v === "boolean" ? "b" : "s";
          }
          if (typeof cell.f === "string" && cell.f) {
            record.f = cell.f.startsWith("=") ? cell.f.slice(1) : cell.f;
            if (!record.t) { record.t = "n"; record.v = 0; }
          }
          if (record.t) converted[address] = record;
          maxRow = Math.max(maxRow, Number(row));
          maxCol = Math.max(maxCol, Number(column));
        }
      }
      converted["!ref"] = XLSX.utils.encode_range({s:{r:0,c:0},e:{r:maxRow,c:maxCol}});
      const safe = (sheet.name || "Sheet" + (++count)).replace(/[\/\\:?*[\]]/g, "").slice(0,31);
      XLSX.utils.book_append_sheet(book, converted, safe || "Sheet" + ++count);
    }
    return book;
  }

  function initEditor() {
    if (univerAPI) return;
    if (!window.UniverPresets || !window.UniverCore ||
        !window.UniverPresetSheetsCore || !window.UniverPresetSheetsCoreEnUS) {
      throw Error("Spreadsheet packages failed to load. Check your connection or content blocker.");
    }
    const { createUniver } = window.UniverPresets;
    const { LocaleType, mergeLocales } = window.UniverCore;
    const { UniverSheetsCorePreset } = window.UniverPresetSheetsCore;
    const result = createUniver({
      locale: LocaleType.EN_US,
      locales: {
        [LocaleType.EN_US]: mergeLocales(window.UniverPresetSheetsCoreEnUS)
      },
      presets: [UniverSheetsCorePreset({
        container: el("board-sheet-editor"),
        ribbonType: "classic",
        footer: { sheetBar: true, statisticBar: true, zoomSlider: true },
      })],
    });
    univer = result.univer;
    univerAPI = result.univerAPI;
    sheetStatus("Spreadsheet editor ready. Workbooks auto-save every 20 seconds.");
  }
  function currentSnapshot() {
    if (!univerAPI) return null;
    const active = workbookFacade || univerAPI.getActiveWorkbook();
    return active?.save() || null;
  }

  async function newWorkbook() {
    const name = prompt("Name your new spreadsheet:", "Chapter " + chapter + " workbook");
    if (name === null) return;
    initEditor();
    await maybeSaveWorkbook();
    const snapshot = freshSnapshot(name.trim() || "Study workbook");
    const data = await sendJSON("POST", "/api/study-board/workbooks", {
      subject, chapter, name: snapshot.name, snapshot
    });
    await refreshLists();
    await openWorkbook(data.workbook.id);
    status("New workbook created");
  }
  async function maybeSaveWorkbook() {
    if (selectedWorkbook && workbookFacade && !savingWorkbook && !loadingWorkbook) {
      const content = JSON.stringify(currentSnapshot());
      if (content !== workbookSnapshot) await saveWorkbook();
    }
  }
  async function openWorkbook(id) {
    initEditor();
    if (selectedWorkbook?.id === id) return;
    await maybeSaveWorkbook();
    loadingWorkbook = true;
    try {
      const data = await requestJSON("/api/study-board/workbooks/" + id);
      const item = data.workbook;
      if (workbookFacade) univerAPI.disposeUnit(workbookFacade.getId());
      workbookFacade = univerAPI.createWorkbook(item.snapshot);
      selectedWorkbook = item;
      workbookSnapshot = JSON.stringify(item.snapshot);
      el("board-workbook-title").value = item.name;
      sheetStatus("Opened " + item.name + " · version " + item.revision);
      renderLists();
    } finally { loadingWorkbook = false; }
  }
  async function saveWorkbook() {
    if (!selectedWorkbook || !workbookFacade || savingWorkbook || loadingWorkbook) return;
    savingWorkbook = true;
    sheetStatus("Saving workbook…");
    try {
      const snapshot = currentSnapshot();
      if (!snapshot) throw Error("No active workbook");
      const name = el("board-workbook-title").value.trim() || "Study workbook";
      const result = await sendJSON("PUT",
        "/api/study-board/workbooks/" + selectedWorkbook.id, {
          snapshot, name, revision: selectedWorkbook.revision
        });
      selectedWorkbook = result.workbook;
      workbookSnapshot = JSON.stringify(snapshot);
      sheetStatus("Saved · " + new Date().toLocaleTimeString("en-GB") + " · version " +
        selectedWorkbook.revision);
      await refreshLists();
    } catch (e) {
      sheetStatus("Save failed: " + errorMessage(e), true);
      throw e;
    } finally { savingWorkbook = false; }
  }
  async function importWorkbook(file) {
    if (file.size > 30 * 1024 * 1024) throw Error("Workbook exceeds 30 MB limit");
    initEditor();
    await maybeSaveWorkbook();
    sheetStatus("Importing " + file.name + "…");
    const bytes = await file.arrayBuffer();
    const raw = fromExcel(bytes, file.name.replace(/\.(xlsx|xls|csv)$/i, ""));
    const data = await sendJSON("POST", "/api/study-board/workbooks", {
      subject, chapter, name: raw.name, snapshot: raw
    });
    await refreshLists();
    await openWorkbook(data.workbook.id);
    sheetStatus("Imported workbook. Check formulas and formatting before relying on results.");
  }
  function exportWorkbook() {
    const snapshot = currentSnapshot();
    if (!snapshot) throw Error("Open a workbook first");
    const xlsx = toExcel(snapshot);
    const name = (el("board-workbook-title").value.trim() || "Jay_Study_Workbook")
      .replace(/[<>:"/\\|?*]/g, "_");
    XLSX.writeFile(xlsx, name + ".xlsx");
    sheetStatus("XLSX exported. Complex formats/macros may not be preserved.");
  }
  async function uploadDocument(file) {
    if (!file) return;
    status("Uploading " + file.name + "…");
    const form = new FormData();
    form.append("subject", subject);
    form.append("chapter", chapter);
    form.append("file", file, file.name);
    const data = await requestJSON("/api/study-board/documents", { method: "POST", body: form });
    await refreshLists();
    await openDocument(data.document);
    status(file.name + " added to chapter " + chapter);
  }
  function setLayout(which) {
    const stage = q("[data-board-stage]");
    stage.dataset.layout = which;
    q("[data-layout=split]").setAttribute("aria-pressed", String(which === "split"));
    q("[data-layout=pdf]").setAttribute("aria-pressed", String(which === "pdf"));
    q("[data-layout=sheet]").setAttribute("aria-pressed", String(which === "sheet"));
    setTimeout(() => {
      if (pdf?.zoomMode === "fit") pdf.updateZoom();
      window.dispatchEvent(new Event("resize"));
    }, 80);
  }
  function wireSplit() {
    const handle = el("board-split-handle"), stage = q("[data-board-stage]");
    let pointer = null;
    function setPercentage(value) {
      const percent = Math.max(22, Math.min(78, value));
      stage.style.setProperty("--reader-percent", percent + "%");
      handle.setAttribute("aria-valuenow", String(Math.round(percent)));
    }
    function move(event) {
      if (pointer === null || event.pointerId !== pointer) return;
      const box = stage.getBoundingClientRect();
      setPercentage((event.clientX - box.left) / box.width * 100);
    }
    handle.addEventListener("pointerdown", event => {
      if (window.matchMedia("(max-width:830px)").matches) return;
      pointer = event.pointerId;
      handle.setPointerCapture(pointer);
    });
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", () => { pointer = null; });
    handle.addEventListener("pointercancel", () => { pointer = null; });
    handle.addEventListener("keydown", event => {
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
        event.preventDefault();
        const present = parseFloat(stage.style.getPropertyValue("--reader-percent") || "50");
        setPercentage(present + (event.key === "ArrowLeft" ? -5 : 5));
      }
    });
  }

  function wire() {
    el("board-subject").addEventListener("change", event => {
      subject = event.target.value; chapter = subject === "AA" ? "1" : "1A"; contextRedirect();
    });
    el("board-chapter").addEventListener("change", event => {
      chapter = event.target.value; contextRedirect();
    });
    for (const button of document.querySelectorAll("[data-layout]")) {
      button.addEventListener("click", () => setLayout(button.dataset.layout));
    }
    el("board-upload").addEventListener("change", async event => {
      try { await uploadDocument(event.target.files[0]); }
      catch (e) { status(errorMessage(e), true); }
      finally { event.target.value = ""; }
    });
    el("board-import-xlsx").addEventListener("change", async event => {
      try { if (event.target.files[0]) await importWorkbook(event.target.files[0]); }
      catch (e) { sheetStatus(errorMessage(e), true); }
      finally { event.target.value = ""; }
    });
    el("board-new-note").addEventListener("click", () => createNote().catch(e => status(errorMessage(e), true)));
    el("board-new-workbook").addEventListener("click", () => newWorkbook().catch(e => sheetStatus(errorMessage(e), true)));
    el("board-save-note").addEventListener("click", () => saveNote().catch(e => status(errorMessage(e), true)));
    el("board-save-workbook").addEventListener("click", () => saveWorkbook().catch(e => sheetStatus(errorMessage(e), true)));
    el("board-export-xlsx").addEventListener("click", () => {
      try { exportWorkbook(); } catch (e) { sheetStatus(errorMessage(e), true); }
    });
    el("board-note-text").addEventListener("input", () => {
      el("board-note-status").textContent = "Unsaved note changes";
    });
    el("board-workbook-title").addEventListener("input", () => sheetStatus("Workbook name changed — save to keep it"));
    q("[data-pdf-prev]").addEventListener("click", () => pdf?.goTo(pdf.currentPage - 1));
    q("[data-pdf-next]").addEventListener("click", () => pdf?.goTo(pdf.currentPage + 1));
    q("[data-pdf-page]").addEventListener("change", event => pdf?.goTo(event.target.value));
    el("board-pdf-zoom").addEventListener("change", event => pdf?.setZoom(event.target.value));
    q("[data-pdf-rotate]").addEventListener("click", () => pdf?.rotate());
    q("[data-pdf-download]").addEventListener("click", () => {
      if (selectedDoc) window.open(selectedDoc.view_url + "?download=1", "_blank", "noopener");
    });
    el("board-find-button").addEventListener("click", () => pdf?.find(el("board-search-pdf").value));
    el("board-search-pdf").addEventListener("keydown", event => {
      if (event.key === "Enter") { event.preventDefault(); pdf?.find(event.target.value); }
    });
    document.addEventListener("keydown", event => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (currentFileType === "Note" && document.activeElement === el("board-note-text"))
          saveNote().catch(e => status(errorMessage(e), true));
        else saveWorkbook().catch(e => sheetStatus(errorMessage(e), true));
      }
    });
    setInterval(async () => {
      if (document.visibilityState !== "visible") return;
      try {
        await maybeSaveWorkbook();
        if (selectedDoc && !selectedDoc.builtin && currentFileType === "Note" &&
            el("board-note-text").value !== noteLastText) await saveNote();
      } catch (_) {/* Visible error statuses already shown */ }
    }, 20000);
    window.addEventListener("pagehide", () => {
      // Browser navigation may interrupt fetch; explicit Save and periodic autosave
      // are the durable pathways. Unload cannot guarantee writes complete.
      if (univer) univer.dispose();
    });
    wireSplit();
  }

  try {
    chapterOptions();
    el("board-subject").value = subject;
    wire();
    const mod = await import("/static/pdf_viewer.js");
    pdf = new mod.StudyPDF(el("board-pdf-scroll"), text => {
      el("board-pdf-message").textContent = text;
    });
    await refreshLists();
    try {
      initEditor();
      if (workbooks.length) await openWorkbook(workbooks[0].id);
      else {
        // Start with a blank workbook and save it immediately to the private
        // server, so there is no data loss when the browser reloads.
        const name = "Chapter " + chapter + " workbook";
        const result = await sendJSON("POST", "/api/study-board/workbooks", {
          subject, chapter, name, snapshot: freshSnapshot(name)
        });
        await refreshLists();
        await openWorkbook(result.workbook.id);
      }
    } catch (e) { sheetStatus(errorMessage(e), true); }
    if (files.some(f => f.filename.toLowerCase().endsWith(".pdf"))) {
      await openDocument(files.find(f => f.filename.toLowerCase().endsWith(".pdf")));
    }
    status("Study Board ready · Chapter " + chapter);
  } catch (e) { status("Study Board could not initialize: " + errorMessage(e), true); }
})();

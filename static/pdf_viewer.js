/* PDF.js chapter reader: continuous scrolling, zoom, rotation, search, page navigation.
   Render pages close to the viewport only so long Kaplan textbooks remain usable. */
import * as pdfjs from "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs";
pdfjs.GlobalWorkerOptions.workerSrc =
  "https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs";

export class StudyPDF {
  constructor(scroller, report) {
    this.scroller = scroller;
    this.report = report;
    this.document = null;
    this.loading = null;
    this.pages = [];
    this.currentPage = 1;
    this.totalPages = 0;
    this.zoomMode = "fit";
    this.rotation = 0;
    this.firstPageWidth = 612;
    this.firstPageHeight = 792;
    this.generation = 0;
    this.rendered = new Map();
    this.textCache = new Map();
    this.observer = null;
    this.resizeObserver = new ResizeObserver(() => {
      if (this.zoomMode === "fit" && this.document) this.updateZoom();
    });
    this.resizeObserver.observe(scroller);
    this.scroller.addEventListener("scroll", () => this.updateActivePage(), { passive: true });
  }

  setStatus(message) { this.report(message); }
  width() {
    return Math.max(180, this.scroller.clientWidth - 34);
  }
  scale() {
    if (this.zoomMode === "fit") return this.width() / this.firstPageWidth;
    return Number(this.zoomMode) || 1;
  }
  updateActivePage() {
    if (!this.pages.length) return;
    const viewport = this.scroller.getBoundingClientRect();
    const targetY = viewport.top + 75;
    let closest = this.currentPage, distance = Infinity;
    for (let i = 0; i < this.pages.length; i++) {
      const el = this.pages[i];
      const rect = el.getBoundingClientRect();
      if (rect.bottom < viewport.top - 150 || rect.top > viewport.bottom + 150) continue;
      const d = Math.abs(rect.top - targetY);
      if (d < distance) { distance = d; closest = i + 1; }
    }
    this.currentPage = closest;
    const label = document.querySelector("[data-pdf-page]");
    if (label && document.activeElement !== label) label.value = String(closest);
  }
  async open(url, label) {
    this.generation++;
    const generation = this.generation;
    this.disposeDocument();
    this.setStatus("Loading " + label + "…");
    this.scroller.replaceChildren();
    try {
      const task = pdfjs.getDocument({ url, withCredentials: true });
      this.loading = task;
      const pdf = await task.promise;
      if (generation !== this.generation) { await pdf.destroy(); return; }
      this.document = pdf;
      this.totalPages = pdf.numPages;
      this.rotation = 0;
      this.textCache.clear();
      const first = await pdf.getPage(1);
      const viewport = first.getViewport({ scale: 1, rotation: this.rotation });
      this.firstPageWidth = viewport.width;
      this.firstPageHeight = viewport.height;
      this.pages = Array.from({ length: pdf.numPages }, (_, i) => {
        const shell = document.createElement("section");
        shell.className = "board-pdf-page";
        shell.dataset.page = String(i + 1);
        shell.setAttribute("aria-label", "PDF page " + (i + 1));
        const placeholder = document.createElement("div");
        placeholder.className = "board-pdf-placeholder";
        placeholder.textContent = "Page " + (i + 1);
        shell.appendChild(placeholder);
        return shell;
      });
      this.scroller.replaceChildren(...this.pages);
      const max = document.querySelector("[data-pdf-total]");
      if (max) max.textContent = String(pdf.numPages);
      this.currentPage = 1;
      this.updateZoom();
      this.observe();
      this.goTo(1);
      this.setStatus(label + " · " + pdf.numPages + " pages");
    } catch (e) {
      if (generation !== this.generation) return;
      this.setStatus("Could not open PDF. Check the uploaded file and network.");
      this.scroller.textContent = "PDF viewer error: " + (e?.message || "Unknown error");
    }
  }
  disposeDocument() {
    if (this.observer) this.observer.disconnect();
    this.observer = null;
    for (const item of this.rendered.values()) item.task?.cancel();
    this.rendered.clear();
    if (this.loading) { try { this.loading.destroy(); } catch (_) {} }
    this.loading = null;
    this.document = null;
    this.pages = [];
    this.totalPages = 0;
    this.textCache.clear();
  }
  close() {
    this.generation++;
    this.disposeDocument();
    this.scroller.innerHTML = '<div class="board-empty-reader">Select a PDF from the chapter library to read here.</div>';
    const max = document.querySelector("[data-pdf-total]");
    if (max) max.textContent = "0";
    this.setStatus("No PDF selected");
  }
  observe() {
    if (this.observer) this.observer.disconnect();
    this.observer = new IntersectionObserver(entries => {
      for (const entry of entries) {
        const n = Number(entry.target.dataset.page);
        if (entry.isIntersecting) this.renderPage(n);
        else if (this.rendered.size > 10) this.unrenderPage(n);
      }
    }, { root: this.scroller, rootMargin: "800px 0px" });
    this.pages.forEach(page => this.observer.observe(page));
  }
  async renderPage(n) {
    if (!this.document || !this.pages[n - 1] || this.rendered.has(n)) return;
    const generation = this.generation;
    const holder = this.pages[n - 1];
    const state = { task: null };
    this.rendered.set(n, state);
    try {
      const pdfPage = await this.document.getPage(n);
      if (generation !== this.generation || !holder.isConnected) return;
      const viewport = pdfPage.getViewport({ scale: this.scale(), rotation: this.rotation });
      holder.style.width = Math.round(viewport.width) + "px";
      holder.style.height = Math.round(viewport.height) + "px";
      const canvas = document.createElement("canvas");
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.ceil(viewport.width * ratio);
      canvas.height = Math.ceil(viewport.height * ratio);
      canvas.style.width = Math.round(viewport.width) + "px";
      canvas.style.height = Math.round(viewport.height) + "px";
      const ctx = canvas.getContext("2d", { alpha: false });
      const task = pdfPage.render({
        canvasContext: ctx,
        viewport,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null
      });
      state.task = task;
      await task.promise;
      if (generation !== this.generation) return;
      holder.replaceChildren(canvas);
    } catch (e) {
      if (e?.name !== "RenderingCancelledException" && generation === this.generation) {
        holder.textContent = "Unable to display page " + n;
      }
    } finally {
      if (generation !== this.generation || !holder.contains(holder.querySelector("canvas"))) {
        this.rendered.delete(n);
      }
    }
  }
  unrenderPage(n) {
    const entry = this.rendered.get(n);
    if (!entry) return;
    entry.task?.cancel();
    const holder = this.pages[n - 1];
    if (holder) {
      const placeholder = document.createElement("div");
      placeholder.className = "board-pdf-placeholder";
      placeholder.textContent = "Page " + n;
      holder.replaceChildren(placeholder);
    }
    this.rendered.delete(n);
  }
  updateZoom() {
    const factor = this.scale();
    for (let i = 0; i < this.pages.length; i++) {
      const el = this.pages[i];
      el.style.width = Math.round(this.firstPageWidth * factor) + "px";
      el.style.height = Math.round(this.firstPageHeight * factor) + "px";
    }
    for (const n of Array.from(this.rendered.keys())) this.unrenderPage(n);
    this.observe();
  }
  setZoom(value) {
    this.zoomMode = value;
    if (this.document) this.updateZoom();
  }
  rotate() {
    if (!this.document) return;
    this.rotation = (this.rotation + 90) % 360;
    [this.firstPageWidth, this.firstPageHeight] =
      [this.firstPageHeight, this.firstPageWidth];
    this.updateZoom();
  }
  goTo(n) {
    const index = Math.max(1, Math.min(this.totalPages, Number(n) || 1));
    if (!this.pages[index - 1]) return;
    this.pages[index - 1].scrollIntoView({ block: "start", behavior: "smooth" });
    this.currentPage = index;
    const input = document.querySelector("[data-pdf-page]");
    if (input) input.value = String(index);
    this.renderPage(index);
  }
  async find(phrase) {
    if (!this.document || !phrase.trim()) return;
    const needle = phrase.toLowerCase().trim();
    const generation = this.generation;
    this.setStatus("Searching PDF for “" + phrase + "”…");
    for (let offset = 1; offset <= this.totalPages; offset++) {
      if (generation !== this.generation) return;
      const n = ((this.currentPage + offset - 1) % this.totalPages) + 1;
      let text = this.textCache.get(n);
      if (text === undefined) {
        try {
          const page = await this.document.getPage(n);
          const content = await page.getTextContent();
          text = content.items.map(item => item.str || "").join(" ").toLowerCase();
          if (this.textCache.size > 60) this.textCache.clear();
          this.textCache.set(n, text);
        } catch (_) { text = ""; }
      }
      if (text.includes(needle)) {
        this.goTo(n);
        this.setStatus("Found on page " + n + ". Search again for the next match.");
        return;
      }
    }
    this.setStatus("No matching text found. Scanned/image-only PDFs may not be searchable.");
  }
}

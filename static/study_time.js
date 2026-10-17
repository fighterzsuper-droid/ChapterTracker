/* Focus-only study clock. Merely reading counts; clicks/typing are not required.
   The server owns all credited seconds. This file never sends elapsed time. */
(function () {
  "use strict";

  // Statistics viewing is not studying. Avoid inflating totals while browsing charts.
  if (location.pathname === "/self-overview") return;
  const subject = location.pathname.startsWith("/tx/") ? "TX" : "AA";
  const HEARTBEAT_MS = 10000;
  function makeId() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  }

  // Unique per DOCUMENT, not sessionStorage: duplicated browser tabs must never
  // share the same identity or close one another's time lease.
  const tabId = makeId();
  let sequence = 0;
  function nextSequence() {
    sequence += 1;
    return sequence;
  }

  const element = document.createElement("section");
  element.className = "study-clock";
  element.setAttribute("aria-label", "Focused-tab study time");
  element.innerHTML =
    '<div class="study-clock-label"><span class="study-dot" aria-hidden="true"></span>' +
    '<div><strong>Focused study clock <small>(' + subject + ')</small></strong>' +
    '<span class="study-clock-status" aria-live="polite">Connecting…</span></div></div>' +
    '<div class="study-clock-numbers">' +
    '<div><span>Today</span><strong data-study-today>--:--:--</strong></div>' +
    '<div><span>Last 7 days</span><strong data-study-week>--:--:--</strong></div>' +
    '<div><span>All time</span><strong data-study-total>--:--:--</strong></div></div>';

  const main = document.querySelector("main");
  if (main) {
    const header = main.querySelector("header");
    if (header) header.insertAdjacentElement("afterend", element);
    else main.prepend(element);
  } else {
    document.body.prepend(element);
  }

  const status = element.querySelector(".study-clock-status");
  const dot = element.querySelector(".study-dot");
  const todayNode = element.querySelector("[data-study-today]");
  const weekNode = element.querySelector("[data-study-week]");
  const totalNode = element.querySelector("[data-study-total]");

  let base = null;
  let lastSync = performance.now();
  let connected = true;
  let inFlight = false;
  let requestedAgain = false;

  function foreground() {
    return document.visibilityState === "visible" && document.hasFocus();
  }
  function format(seconds) {
    const total = Math.max(0, Math.floor(seconds || 0));
    const hours = String(Math.floor(total / 3600)).padStart(2, "0");
    const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
    const secs = String(total % 60).padStart(2, "0");
    return hours + ":" + minutes + ":" + secs;
  }

  function render() {
    const counting = foreground() && navigator.onLine && connected;
    const extrapolated = counting && base ?
      Math.min(16, (performance.now() - lastSync) / 1000) : 0;

    if (base) {
      todayNode.textContent = format(base.today_seconds + extrapolated);
      weekNode.textContent = format(base.week_seconds + extrapolated);
      totalNode.textContent = format(base.total_seconds + extrapolated);
    }

    dot.classList.toggle("counting", counting);
    if (!navigator.onLine || !connected) {
      status.textContent = "Disconnected — unverified time is not counted";
    } else if (counting) {
      status.textContent = "Counting — this tab is in focus";
    } else {
      status.textContent = "Paused — tab hidden or window unfocused";
    }
  }

  async function pulse() {
    if (inFlight) {
      requestedAgain = true;
      return;
    }
    inFlight = true;
    const payload = {
      subject: subject,
      tab_id: tabId,
      seq: nextSequence(),
      active: foreground() && navigator.onLine
    };
    try {
      const response = await fetch("/api/study-time/pulse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        cache: "no-store",
        keepalive: !payload.active,
        body: JSON.stringify(payload)
      });
      if (!response.ok) throw new Error("Study clock request failed");
      const data = await response.json();
      if (!data.accepted) throw new Error("Stale timer request");
      base = data;
      lastSync = performance.now();
      connected = true;
    } catch (_) {
      connected = false;
    } finally {
      inFlight = false;
      render();
      if (requestedAgain) {
        requestedAgain = false;
        pulse();
      }
    }
  }

  // Send changes immediately, including tab swaps and switching to another app.
  for (const eventName of ["focus", "blur", "pageshow", "online", "offline"]) {
    window.addEventListener(eventName, pulse, { passive: true });
  }
  document.addEventListener("visibilitychange", pulse, { passive: true });

  // Pagehide is the last chance to close the session when the document unloads.
  window.addEventListener("pagehide", function () {
    if (!navigator.sendBeacon) return;
    const payload = JSON.stringify({
      subject: subject, tab_id: tabId, seq: nextSequence(), active: false
    });
    navigator.sendBeacon(
      "/api/study-time/pulse",
      new Blob([payload], { type: "application/json" })
    );
  });

  // Browser timers are throttled in background; the server deliberately awards
  // ZERO catch-up time when more than 16 seconds pass without a heartbeat.
  setInterval(function () {
    if (foreground()) pulse();
    else render();
  }, HEARTBEAT_MS);

  setInterval(render, 1000);
  pulse();
})();

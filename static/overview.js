/* Self Overview: live Kuwait time and server-recorded focused-study charts.
   No browser-supplied elapsed duration is ever credited by this page. */
(function () {
  "use strict";
  const select = document.getElementById("overview-subject");
  const dayInput = document.getElementById("overview-date");
  if (!select || !dayInput) return;

  const $ = selector => document.querySelector(selector);
  const pad = number => String(number).padStart(2, "0");
  const hhmmss = totalSeconds => {
    const t = Math.max(0, Math.floor(Number(totalSeconds) || 0));
    return pad(Math.floor(t / 3600)) + ":" + pad(Math.floor(t % 3600 / 60)) + ":" + pad(t % 60);
  };
  const minutesLabel = s => Math.round((Number(s) || 0) / 60) + "m";
  const labelDate = iso => {
    const d = new Date(iso + "T12:00:00+03:00");
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kuwait", weekday: "short", day: "numeric", month: "short"
    }).format(d);
  };

  const timeFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuwait", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false
  });
  const dateFormatter = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kuwait", weekday: "long", day: "numeric", month: "long", year: "numeric"
  });
  let snapshot = null;
  let syncedServerMs = null;
  let syncedAt = 0;
  let fetching = false;
  let refreshAgain = false;

  function kuwaitClock() {
    const time = new Date(syncedServerMs === null ? Date.now()
      : syncedServerMs + performance.now() - syncedAt);
    $("[data-kuwait-clock]").textContent = timeFormatter.format(time);
    $("[data-kuwait-date]").textContent = dateFormatter.format(time);
  }

  function value(record) {
    const subject = select.value;
    if (!record) return 0;
    if (subject === "ALL") return (record.AA || 0) + (record.TX || 0);
    return record[subject] || 0;
  }

  function addBar(group, item, index, max, type) {
    const total = value(item);
    const holder = document.createElement("div");
    holder.className = "overview-bar-item";

    const track = document.createElement("div");
    track.className = "overview-bar-track";
    const height = Math.max(0, Math.min(100, total / max * 100));

    function piece(subject, className) {
      const seconds = select.value === "ALL" || select.value === subject ? (item[subject] || 0) : 0;
      if (seconds <= 0) return;
      const part = document.createElement("div");
      part.className = className;
      part.style.height = String(seconds / max * 100) + "%";
      track.appendChild(part);
    }

    piece("AA", "overview-bar-aa");
    piece("TX", "overview-bar-tx");
    if (!total) track.classList.add("overview-no-study");

    const tick = document.createElement("span");
    tick.className = "overview-bar-tick";
    tick.textContent = type === "hour" ? (index % 3 === 0 ? pad(item.hour) : "")
      : labelDate(item.day).replace(/ [A-Za-z]+$/, "");

    const text = type === "hour" ? pad(item.hour) + ":00–" + pad(item.hour) + ":59"
      : labelDate(item.day);
    holder.title = text + " Kuwait · " + minutesLabel(total) + " focused (" +
      minutesLabel(item.AA) + " AA; " + minutesLabel(item.TX) + " TX)";
    holder.setAttribute("aria-label", holder.title);
    holder.appendChild(track);
    holder.appendChild(tick);
    group.appendChild(holder);
  }

  function chart(selector, rows, type) {
    const group = $(selector);
    group.replaceChildren();
    const max = Math.max(300, ...rows.map(value));
    rows.forEach((record, index) => addBar(group, record, index, max, type));
    group.setAttribute("aria-label", "Focused study time chart. Highest selected " +
      (type === "hour" ? "hour" : "day") + ": " + minutesLabel(max) + ".");
  }

  function render() {
    if (!snapshot) return;
    const s = snapshot;
    $("[data-kpi-today]").textContent = hhmmss(value(s.today_totals));
    $("[data-kpi-week]").textContent = hhmmss(value(s.week_totals));
    $("[data-kpi-lifetime]").textContent = hhmmss(value(s.lifetime_totals));
    $("[data-kpi-selected]").textContent = hhmmss(value(s.selected_totals));
    $("[data-kpi-selected-day]").textContent = labelDate(s.selected_day);
    $("[data-aa-today]").textContent = hhmmss(s.today_totals.AA);
    $("[data-tx-today]").textContent = hhmmss(s.today_totals.TX);
    $("[data-hour-title]").textContent = labelDate(s.selected_day) + " · hourly focused minutes (Kuwait time).";
    chart("[data-hour-bars]", s.hours, "hour");
    chart("[data-day-bars]", s.days, "day");
    $("[data-overview-refresh]").textContent = "Synced with Bot-Hosting · " +
      timeFormatter.format(new Date(s.server_now_ms));
  }

  async function refresh() {
    if (document.visibilityState !== "visible" || !navigator.onLine) return;
    if (fetching) { refreshAgain = true; return; }
    fetching = true;
    try {
      const query = dayInput.value ? "?date=" + encodeURIComponent(dayInput.value) : "";
      const response = await fetch("/api/self-overview" + query, {
        cache: "no-store", credentials: "same-origin"
      });
      if (!response.ok) throw new Error("No overview data");
      const result = await response.json();
      snapshot = result;
      syncedServerMs = result.server_now_ms;
      syncedAt = performance.now();
      dayInput.max = result.today;
      if (!dayInput.value) dayInput.value = result.today;
      // On the next day, automatically follow today unless a historical day was chosen.
      if (dayInput.dataset.followToday === "yes" && dayInput.value !== result.today) {
        dayInput.value = result.today;
        refreshAgain = true;
      }
      render();
    } catch (_) {
      $("[data-overview-refresh]").textContent = "Unable to refresh — last saved figures shown";
    } finally {
      fetching = false;
      if (refreshAgain) { refreshAgain = false; refresh(); }
    }
  }

  dayInput.dataset.followToday = "yes";
  dayInput.addEventListener("change", function () {
    dayInput.dataset.followToday = "no";
    refresh();
  });
  select.addEventListener("change", render);
  window.addEventListener("focus", refresh);
  window.addEventListener("online", refresh);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") refresh();
  });
  setInterval(function () {
    kuwaitClock();
    const time = new Date(syncedServerMs === null ? Date.now()
      : syncedServerMs + performance.now() - syncedAt);
    const components = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Kuwait", year: "numeric", month: "2-digit", day: "2-digit"
    }).formatToParts(time);
    const parts = Object.fromEntries(components.map(x => [x.type, x.value]));
    const today = [parts.year, parts.month, parts.day].join("-");
    if (dayInput.dataset.followToday === "yes" && snapshot && today !== snapshot.today) {
      dayInput.value = today;
      refresh();
    }
  }, 1000);
  setInterval(refresh, 10000);
  kuwaitClock();
  refresh();
})();

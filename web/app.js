/* PrimeLedger (prime sets for Warframe) — page logic. No frameworks, no external requests:
   the page talks only to the local server that started it. */
(() => {
"use strict";

// ----------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const SVG_NS = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  appendKids(el, kids);
  return el;
}
function s(tag, attrs, ...kids) {
  const el = document.createElementNS(SVG_NS, tag);
  setAttrs(el, attrs);
  appendKids(el, kids);
  return el;
}
function setAttrs(el, attrs) {
  if (!attrs) return;
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.setAttribute("class", v);
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else el.setAttribute(k, v);
  }
}
function appendKids(el, kids) {
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
}

const ICONS = {
  refresh: '<path d="M13.5 8a5.5 5.5 0 1 1-1.6-3.9"/><path d="M13.6 2.2v3h-3"/>',
  image: '<rect x="2" y="3" width="12" height="10" rx="2.2"/><circle cx="5.8" cy="6.6" r="1.1"/><path d="m3 11.6 3.2-3 2.3 2 2-1.8 2.5 2.4"/>',
  search: '<circle cx="7" cy="7" r="4.2"/><path d="m10.2 10.2 3.3 3.3"/>',
  info: '<circle cx="8" cy="8" r="6"/><path d="M8 7.2v4"/><circle cx="8" cy="5" r=".6" fill="currentColor"/>',
  chevron: '<path d="m6 3.5 4.5 4.5L6 12.5"/>',
  down: '<path d="M8 3v9.5"/><path d="m4 8.8 4 4 4-4"/>',
  up: '<path d="M4 12 12 4"/><path d="M6 4h6v6"/>',
  fall: '<path d="m4 4 8 8"/><path d="M12 6v6H6"/>',
  flat: '<path d="M3 8h10"/><path d="m9.5 4.5 3.5 3.5-3.5 3.5"/>',
  check: '<path d="m3.5 8.4 3 3 6-6.8"/>',
  alert: '<path d="M8 2.6 14 13H2Z"/><path d="M8 6.6v3.2"/><circle cx="8" cy="11.3" r=".6" fill="currentColor"/>',
  lock: '<rect x="3.5" y="7" width="9" height="6.5" rx="1.8"/><path d="M5.5 7V5.3a2.5 2.5 0 0 1 5 0V7"/>',
  external: '<path d="M9 3h4v4"/><path d="M13 3 7.5 8.5"/><path d="M11 9.5V12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h2.5"/>',
  plus: '<path d="M8 3.5v9M3.5 8h9"/>',
  minus: '<path d="M3.5 8h9"/>',
  close: '<path d="m4 4 8 8M12 4l-8 8"/>',
  sun: '<circle cx="8" cy="8" r="2.8"/><path d="M8 1.6v1.6M8 12.8v1.6M1.6 8h1.6M12.8 8h1.6M3.5 3.5l1.1 1.1M11.4 11.4l1.1 1.1M3.5 12.5l1.1-1.1M11.4 4.6l1.1-1.1"/>',
  moon: '<path d="M13 9.6A5.6 5.6 0 0 1 6.4 3a5.6 5.6 0 1 0 6.6 6.6Z"/>',
  folder: '<path d="M2 5a1.5 1.5 0 0 1 1.5-1.5h2.6l1.4 1.6h5A1.5 1.5 0 0 1 14 6.6v5A1.5 1.5 0 0 1 12.5 13h-9A1.5 1.5 0 0 1 2 11.6Z"/>',
  copy: '<rect x="5.5" y="5.5" width="8" height="8" rx="1.8"/><path d="M10.5 5.5V4a1.5 1.5 0 0 0-1.5-1.5H4A1.5 1.5 0 0 0 2.5 4v5A1.5 1.5 0 0 0 4 10.5h1.5"/>',
  cube: '<path d="M8 2 13.5 5v6L8 14 2.5 11V5Z"/><path d="M2.5 5 8 8l5.5-3M8 8v6"/>',
  table: '<rect x="2" y="3" width="12" height="10" rx="1.8"/><path d="M2 6.5h12M6.5 6.5V13"/>',
  clock: '<circle cx="8" cy="8" r="6"/><path d="M8 4.6V8l2.4 1.6"/>',
  gear: '<path d="M2.5 4.5h6M11.5 4.5h2M2.5 11.5h2M7.5 11.5h6"/><circle cx="10" cy="4.5" r="1.6"/><circle cx="6" cy="11.5" r="1.6"/>',
};
function icon(name, extra) {
  const span = h("span", { class: "ico" + (extra ? " " + extra : ""), "aria-hidden": "true" });
  span.innerHTML = `<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
  return span;
}

// ----------------------------------------------------------------- language
/* The texts of the page are written here in Russian and looked up in the table of the chosen
   language (web/i18n/<lang>.json, handed over by the server as window.I18N):
     t(text, a, b)      a plain text; {0} {1} in it are filled in;
     tn(forms, n)       a text that depends on a number: forms separated by |, # is the number itself;
     tx(text, node)     a text whose placeholders are page elements -- returns pieces for h(). */
const I18N = window.I18N || { lang: "ru", locale: "ru-RU", plural: ["one", "few", "many"], name: "", strings: {}, languages: [] };
const LANG = I18N.lang, LOCALE = I18N.locale;
function lookup(text) {
  const hit = I18N.strings[text.trim()];
  if (hit == null) return text;
  // the spaces the code put around a text stay as they were
  return text.slice(0, text.length - text.trimStart().length) + hit + text.slice(text.trimEnd().length);
}
const fill = (text, args) => (args.length ? text.replace(/\{(\d+)\}/g, (m, i) => (args[i] == null ? "" : String(args[i]))) : text);
function t(text, ...args) { return fill(lookup(text), args); }
const ownRules = new Intl.PluralRules(LOCALE), sourceRules = new Intl.PluralRules("ru");
function tn(forms, n, ...args) {
  const text = lookup(forms);
  // a text without a translation is still Russian: its forms follow the Russian rule
  const own = LANG === "ru" || text !== forms;
  const list = text.split("|");
  const count = Math.abs(Number(n)) || 0;
  let idx = (own ? I18N.plural : ["one", "few", "many"]).indexOf((own ? ownRules : sourceRules).select(count));
  if (idx < 0 || idx >= list.length) idx = list.length - 1;
  return fill(list[idx].replace(/#/g, fmt(Number(n) || 0)), args);
}
function tx(text, ...nodes) {
  const out = [];
  for (const bit of lookup(text).split(/(\{\d+\})/)) {
    const m = /^\{(\d+)\}$/.exec(bit);
    if (!m) { if (bit) out.push(bit); } else if (nodes[m[1]] != null && nodes[m[1]] !== false) out.push(nodes[m[1]]);
  }
  return out;
}
// for searching: case, accents and \u0451/\u0435 make no difference
const fold = (text) => String(text == null ? "" : text).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/\u0142/g, "l");

const nf = new Intl.NumberFormat(LOCALE);
const fmt = (n) => nf.format(Math.round(n));
const MINUS = "\u2212";
function pct(f) {
  const v = Math.round(Math.abs(f) * 100);
  return (f > 0 ? "+" : f < 0 ? MINUS : "") + v + "\u00a0%";
}
const pl = (n) => t("{0} пл", fmt(n));          // an amount of platinum
const shotNo = (n) => t("№{0}", n);              // a screenshot by its number in the dialog
const quoted = (text) => t("«{0}»", text);       // a name as it was read from a screenshot
const dayFmt = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long" });
const dayShort = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short" });
const monthFmt = new Intl.DateTimeFormat(LOCALE, { month: "short" });
const stampFmt = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
const parseDay = (iso) => new Date(iso + "T00:00:00");

async function api(path, opts) {
  const res = await fetch(path, opts);
  let body = null;
  try { body = await res.json(); } catch (e) { /* not JSON */ }
  if (!res.ok) throw new Error((body && body.error) || t("Ошибка {0}", res.status));
  return body;
}
const post = (path, payload) => api(path, {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-Requested-With": "primesets" },
  body: JSON.stringify(payload || {}),
});

let toastTimer = 0;
// action: {label, run} -- a button inside the message, to take back what was just done; such a message stays longer
function toast(text, action) {
  const el = $("#toast");
  el.replaceChildren(String(text), action ? h("button", { class: "toast-btn", onclick: () => { el.hidden = true; action.run(); } }, action.label) : "");
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, action ? 9000 : 3600);
}

// ----------------------------------------------------------------- state
const S = {
  data: null,
  market: new Map(),        // set slug -> {state: loading|done|error, data, error}
  lite: new Map(),          // set slug -> price-only answer (for the "почти собраны" list)
  parts: new Map(),         // "scope:slug" -> {state, data}
  copied: new Set(),        // "part slug|seller": the message for this seller was copied (its text stays in sight)
  reviewOpen: false,
  allParts: null,
  tab: "complete",
  query: "",
  sort: { complete: { key: "price", dir: "desc" }, partial: { key: "missing", dir: "asc" }, ducats: { key: "rate", dir: "desc" } },
  nearFilter: "all",
  open: new Set(),
  tableView: new Set(),
  queueGen: 0,
  queue: { running: false, done: 0, total: 0 },
  buyQueue: { running: false, done: 0, total: 0, gen: 0 },
  partsQueue: { running: false, done: 0, total: 0, gen: 0 },
};
const TABS = ["complete", "partial", "parts", "ducats", "collection"];
try {
  const saved = localStorage.getItem("primesets-tab");
  if (TABS.includes(saved)) S.tab = saved;
} catch (e) { /* storage unavailable */ }
// the address may name a tab or the settings: .../#ducats, .../#settings
const startAt = location.hash.slice(1);
if (TABS.includes(startAt)) S.tab = startAt;
// a number the user typed last time (a target, a threshold), kept between starts
function remembered(key, fallback) {
  try { const v = Number(localStorage.getItem(key)); return Number.isFinite(v) && v > 0 ? v : fallback; } catch (e) { return fallback; }
}
function remember(key, value) {
  try { localStorage.setItem(key, String(value)); } catch (e) { /* ignore */ }
}

// ----------------------------------------------------------------- small UI pieces
function thumb(rel, small) {
  const box = h("span", { class: "thumb" + (small ? " sm" : "") });
  if (rel) {
    const img = h("img", { src: "/img?p=" + encodeURIComponent(rel), alt: "", loading: "lazy", decoding: "async" });
    img.addEventListener("error", () => { img.remove(); box.append(icon("cube")); });
    box.append(img);
  } else {
    box.append(icon("cube"));
  }
  return box;
}

const CATEGORY = { warframe: t("Варфрейм"), primary: t("Основное оружие"), secondary: t("Вторичное оружие"), melee: t("Ближний бой"),
  sentinel: t("Страж"), archwing: t("Арчвинг"), other: t("Прочее") };
const MASTERY_OPTIONS = [
  ["mastered", t("Освоено")],
  ["owned", t("Есть в арсенале")],
  ["none", t("Не освоено")],
  [null, t("Не знаю")],
];
function masteryChip(set) {
  const m = set.mastery;
  if (!m || m.state === "na") return null;
  let chip;
  if (m.state === "mastered") chip = h("span", { class: "chip good" }, icon("check"), t("освоено"));
  else if (m.state === "none") chip = h("span", { class: "chip warn" }, icon("alert"), t("не освоено"));
  else if (m.state === "owned") chip = h("span", { class: "chip" }, t("есть в арсенале"));
  else chip = h("span", { class: "chip quiet" }, t("освоение не отмечено"));
  const btn = h("span", {
    class: "chip-btn", role: "button", tabindex: "0", title: t("Изменить отметку освоения"),
    onclick: (e) => { e.stopPropagation(); openMasteryMenu(btn, set); },
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); openMasteryMenu(btn, set); } },
  }, chip);
  return btn;
}

let menuEl = null;
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function openMasteryMenu(anchor, set) {
  closeMenu();
  const current = set.mastery.state === "unknown" ? null : set.mastery.state;
  menuEl = h("div", { class: "menu", role: "menu" },
    MASTERY_OPTIONS.map(([value, label]) => h("button", {
      role: "menuitemradio", "aria-checked": String(value === current),
      onclick: async () => {
        closeMenu();
        try {
          S.data = await post("/api/mastery/set", { slug: set.slug, state: value });
          render();
        } catch (err) { toast(err.message); }
      },
    }, value === current ? icon("check") : h("span", { class: "ico" }), label)));
  document.body.append(menuEl);
  const r = anchor.getBoundingClientRect();
  const w = menuEl.offsetWidth, hgt = menuEl.offsetHeight;
  menuEl.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px";
  menuEl.style.top = (r.bottom + hgt + 8 > innerHeight ? Math.max(8, r.top - hgt - 6) : r.bottom + 6) + "px";
  menuEl.querySelector('[aria-checked="true"]')?.focus();
}
document.addEventListener("click", (e) => { if (menuEl && !menuEl.contains(e.target)) closeMenu(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });
addEventListener("scroll", closeMenu, true);

const VAULT_HINT = {
  vaulted: t("Ни одна реликвия с частями этого комплекта сейчас не выпадает в миссиях."),
  available: t("Реликвии с частями комплекта сейчас выпадают в миссиях."),
  special: t("В миссиях реликвии не выпадают, но warframe.market не считает их убранными в хранилище: обычно это реликвии от Баро Ки'Тиира или из особых источников."),
  partial: t("Часть деталей сейчас можно добыть, часть — только из реликвий в хранилище."),
  unknown: t("Нет данных таблиц дропа."),
};
function vaultCell(set) {
  const v = set.vault;
  let chip;
  if (v.state === "vaulted") chip = h("span", { class: "chip solid" }, icon("lock"), v.label);
  else if (v.state === "unknown") chip = h("span", { class: "chip quiet" }, v.label);
  else chip = h("span", { class: "chip" }, v.label);
  return h("div", { class: "c-vault", title: VAULT_HINT[v.state] || "" }, chip, v.note ? h("div", { class: "sub" }, v.note) : null);
}

function setNameCell(set) {
  const meta = [h("span", null, CATEGORY[set.category] || "")];
  const chip = masteryChip(set);
  if (chip) meta.push(chip);
  return h("div", { class: "item" },
    thumb(set.thumb),
    h("div", { class: "item-text" },
      h("div", { class: "item-title" },
        h("span", { title: set.title_en }, set.title),
        set.complete > 1 ? h("span", { class: "times", title: t("Полных комплектов: {0}", set.complete) }, "×" + set.complete) : null),
      h("div", { class: "item-meta" }, meta)));
}

// ----------------------------------------------------------------- sparkline & chart
/* A row-sized trend line. Daily medians of thinly traded sets jump around, so the
   sparkline shows a trailing 7-day average weighted by deals; the detail chart keeps the raw days. */
function smooth(series, days) {
  const out = [];
  let lo = 0;
  for (let i = 0; i < series.length; i++) {
    const t = parseDay(series[i][0]).getTime();
    while (parseDay(series[lo][0]).getTime() <= t - days * 86400000) lo++;
    let sum = 0, vol = 0;
    for (let j = lo; j <= i; j++) { sum += series[j][1] * series[j][2]; vol += series[j][2]; }
    out.push([series[i][0], vol ? sum / vol : series[i][1], series[i][2]]);
  }
  return out;
}
function sparkline(trend) {
  const raw = trend.series || [];
  const W = 116, H = 32, pad = 5;
  if (raw.length < 2) return h("span", { class: "spark" });
  const pts = smooth(raw, 7);
  const t0 = parseDay(pts[0][0]).getTime(), t1 = parseDay(pts[pts.length - 1][0]).getTime();
  let lo = Infinity, hi = -Infinity;
  for (const p of pts) { lo = Math.min(lo, p[1]); hi = Math.max(hi, p[1]); }
  if (hi === lo) { hi += 1; lo -= 1; }
  const x = (t) => pad + (t - t0) / ((t1 - t0) || 1) * (W - pad * 2);
  const y = (v) => pad + (1 - (v - lo) / (hi - lo)) * (H - pad * 2);
  const xy = pts.map((p) => [x(parseDay(p[0]).getTime()), y(p[1])]);
  const path = (arr) => arr.map((q, i) => (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1)).join("");
  // the last comparison window is drawn in the accent: it is the "now" the trend is measured against
  const cut = t1 - (trend.window_days || 14) * 86400000;
  let from = pts.findIndex((p) => parseDay(p[0]).getTime() > cut);
  if (from < 1) from = Math.max(1, pts.length - 2);
  const end = xy[xy.length - 1];
  const svg = s("svg", { class: "spark", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img" },
    s("title", null, t("Цена сделок за {0} дн., среднее за 7 дней: {1} → {2} пл", trend.period_days, fmt(pts[0][1]), fmt(pts[pts.length - 1][1]))),
    s("path", { d: path(xy.slice(0, from + 1)), fill: "none", stroke: "var(--series-quiet)", "stroke-width": 1.5, "stroke-linejoin": "round", "stroke-linecap": "round" }),
    s("path", { d: path(xy.slice(from)), fill: "none", stroke: "var(--series)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }),
    s("circle", { cx: end[0].toFixed(1), cy: end[1].toFixed(1), r: 4, fill: "var(--series)", stroke: "var(--surface)", "stroke-width": 2 }));
  return svg;
}

function niceTicks(lo, hi, count) {
  // platinum is whole numbers: steps of 1, 2, 5, 10, 20, 50...
  if (hi - lo < 2) { hi += 1; lo = Math.max(0, lo - 1); }
  const raw = Math.max(1, (hi - lo) / count);
  const mag = Math.pow(10, Math.floor(Math.log10(raw)));
  const step = [1, 2, 5, 10].map((m) => m * mag).find((st) => st >= raw) || raw;
  const start = Math.floor(lo / step) * step, end = Math.ceil(hi / step) * step;
  const out = [];
  for (let v = start; v <= end + step / 2; v += step) out.push(Math.round(v));
  return out;
}

/* 90-day chart. Emphasis form: the 7-day average is the one accented series,
   the raw daily medians stay as thin context in the de-emphasis gray. */
function priceChart(trend, width, opts) {
  const o = Object.assign({
    smooth: 7,                       // 0: the points are drawn as they are, with no second line
    avgLabel: t("среднее за 7 дней"), dayLabel: t("за этот день"),
    volText: (p) => tn("# сделка|# сделки|# сделок", p.vol),
    aria: null,
  }, opts || {});
  const series = trend.series || [];
  if (series.length < 2) return h("div", { class: "chart-note" }, t("Слишком мало сделок, чтобы построить график."));
  const W = Math.max(300, Math.round(width || 520));
  const H = Math.round(Math.max(190, Math.min(250, W * 0.42)));
  const m = { l: 40, r: 46, t: 12, b: 26 };
  const avg = o.smooth ? smooth(series, o.smooth) : series;
  const pts = series.map((p, i) => ({ t: parseDay(p[0]).getTime(), price: p[1], avg: avg[i][1], vol: p[2] }));
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t;
  const ticks = niceTicks(Math.min(...pts.map((p) => p.price)), Math.max(...pts.map((p) => p.price)), 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const x = (t) => m.l + (t - t0) / ((t1 - t0) || 1) * (W - m.l - m.r);
  const y = (v) => m.t + (1 - (v - y0) / ((y1 - y0) || 1)) * (H - m.t - m.b);
  const pathOf = (key) => pts.map((p, i) => (i ? "L" : "M") + x(p.t).toFixed(1) + " " + y(p[key]).toFixed(1)).join("");
  const line = pathOf("avg");
  const base = H - m.b;
  const area = line + `L${x(t1).toFixed(1)} ${base}L${x(t0).toFixed(1)} ${base}Z`;
  const last = pts[pts.length - 1];

  const svg = s("svg", { class: "chart", width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", tabindex: "0",
    "aria-label": o.aria || t("Цена сделок за {0} дней, среднее за 7 дней: от {1} до {2} платины", trend.period_days, fmt(pts[0].avg), fmt(last.avg)) });
  for (const tick of ticks) {
    svg.append(s("line", { x1: m.l, x2: W - m.r, y1: y(tick), y2: y(tick), stroke: tick === y0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1 }));
    svg.append(s("text", { x: m.l - 8, y: y(tick) + 4, "text-anchor": "end" }, fmt(tick)));
  }
  // month labels on the time axis
  const d = new Date(t0); d.setDate(1); d.setMonth(d.getMonth() + 1);
  let labels = 0;
  for (; d.getTime() <= t1; d.setMonth(d.getMonth() + 1)) {
    const px = x(d.getTime());
    svg.append(s("line", { x1: px, x2: px, y1: base, y2: base + 4, stroke: "var(--axis)", "stroke-width": 1 }));
    svg.append(s("text", { x: px, y: base + 17, "text-anchor": "middle" }, monthFmt.format(d).replace(".", "")));
    labels++;
  }
  if (!labels) {
    svg.append(s("text", { x: m.l, y: base + 17, "text-anchor": "start" }, dayShort.format(new Date(t0))));
    svg.append(s("text", { x: W - m.r, y: base + 17, "text-anchor": "end" }, dayShort.format(new Date(t1))));
  }
  svg.append(s("path", { d: area, fill: "var(--series)", opacity: 0.1 }));
  if (o.smooth) svg.append(s("path", { d: pathOf("price"), fill: "none", stroke: "var(--series-quiet)", "stroke-width": 1, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  svg.append(s("path", { d: line, fill: "none", stroke: "var(--series)", "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }));
  const cross = s("line", { y1: m.t, y2: base, stroke: "var(--muted)", "stroke-width": 1, visibility: "hidden" });
  const dot = s("circle", { r: 4.5, fill: "var(--series)", stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" });
  svg.append(cross);
  svg.append(s("circle", { cx: x(last.t), cy: y(last.avg), r: 4.5, fill: "var(--series)", stroke: "var(--surface)", "stroke-width": 2 }));
  svg.append(s("text", { class: "end-label", x: x(last.t) + 9, y: y(last.avg) + 4 }, fmt(last.avg)));
  svg.append(dot);

  const tip = $("#tooltip");
  let active = -1;
  const key = (color) => h("span", { class: "key", style: `background:${color}` });
  function show(i, clientX, clientY) {
    active = i;
    const p = pts[i];
    const px = x(p.t), py = y(p.avg);
    cross.setAttribute("x1", px); cross.setAttribute("x2", px); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", px); dot.setAttribute("cy", py); dot.setAttribute("visibility", "visible");
    tip.replaceChildren(...[
      h("div", { class: "tt-sub" }, dayFmt.format(new Date(p.t))),
      h("div", { class: "tt-row" }, key("var(--series)"), h("strong", null, pl(p.avg)), h("span", { class: "tt-sub" }, o.avgLabel)),
      o.smooth ? h("div", { class: "tt-row" }, key("var(--series-quiet)"), h("strong", null, pl(p.price)), h("span", { class: "tt-sub" }, o.dayLabel)) : null,
      h("div", { class: "tt-sub" }, o.volText(p, i)),
    ].filter(Boolean));
    // a modal dialog is drawn above the whole page: a tooltip for a chart inside it must live inside it too
    const host = svg.closest("dialog") || document.body;
    if (tip.parentNode !== host) host.append(tip);
    tip.hidden = false;
    const box = svg.getBoundingClientRect();
    if (clientX == null) { clientX = box.left + px; clientY = box.top + py; }
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left = clientX + 14, top = clientY - th - 12;
    if (left + tw > innerWidth - 8) left = clientX - tw - 14;
    if (top < 8) top = clientY + 16;
    tip.style.left = left + "px"; tip.style.top = top + "px";
  }
  function hide() {
    active = -1;
    cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden");
    tip.hidden = true;
  }
  svg.addEventListener("pointermove", (e) => {
    const box = svg.getBoundingClientRect();
    const t = t0 + ((e.clientX - box.left) - m.l) / (W - m.l - m.r) * (t1 - t0);
    let best = 0;
    for (let i = 1; i < pts.length; i++) if (Math.abs(pts[i].t - t) < Math.abs(pts[best].t - t)) best = i;
    show(best, e.clientX, e.clientY);
  });
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("focus", () => show(pts.length - 1));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const i = active < 0 ? pts.length - 1 : active;
    show(Math.max(0, Math.min(pts.length - 1, i + (e.key === "ArrowLeft" ? -1 : 1))));
  });
  return svg;
}

function priceTable(trend) {
  const series = trend.series || [];
  const avg = smooth(series, 7);
  const rows = series.map((r, i) => [r[0], r[1], avg[i][1], r[2]]).reverse();
  return h("div", { class: "table-view" },
    h("table", null,
      h("thead", null, h("tr", null, h("th", null, t("День")), h("th", null, t("Среднее за 7 дн., пл")), h("th", null, t("За день, пл")), h("th", null, t("Сделок")))),
      h("tbody", null, rows.map((r) => h("tr", null,
        h("td", null, dayFmt.format(parseDay(r[0]))), h("td", null, fmt(r[2])), h("td", null, fmt(r[1])), h("td", null, fmt(r[3])))))));
}

// ----------------------------------------------------------------- market cells
const DIR = {
  up: [t("растёт"), "up", "up"],
  down: [t("падает"), "fall", "down"],
  flat: [t("стабильна"), "flat", ""],
  unknown: [t("мало данных"), "flat", ""],
};
function priceCell(set) {
  const m = S.market.get(set.slug);
  const cell = h("div", { class: "c-price" });
  if (!m || m.state === "loading") {
    cell.append(h("span", { class: "skeleton", style: "width:64px;height:20px" }), h("div", { class: "sub" }, h("span", { class: "skeleton", style: "width:96px;height:11px" })));
    return cell;
  }
  if (m.state === "error" || !m.data.price) {
    cell.append(h("div", { class: "dim" }, t("нет данных")),
      h("div", { class: "sub" }, (m.error || (m.data && m.data.errors[0]) || t("маркет не ответил")).slice(0, 70)));
    return cell;
  }
  const p = m.data.price, trend = m.data.trend;
  if (p.value != null) {
    cell.append(h("div", { class: "price num", title: p.sell_prices.length ? t("Самые дешёвые предложения: {0} пл", p.sell_prices.join(", ")) : "" },
      fmt(p.value), h("span", { class: "unit" }, t("пл"))));
  } else {
    cell.append(h("div", { class: "dim" }, t("нет предложений")));
  }
  const bits = [];
  if (p.basis === "online") bits.push(t("продавец не в игре"));
  if (trend && trend.recent_price != null) bits.push(t("сделки за 7 дн.: ~{0}", fmt(trend.recent_price)));
  if (set.complete > 1 && p.value != null) bits.unshift(t("за {0}: {1}", set.complete, fmt(p.value * set.complete)));
  cell.append(h("div", { class: "sub num" }, bits.join(" · ")));
  const pv = partsVerdict(set);
  if (pv && pv.better) {
    cell.append(h("div", { class: "chip better", title: t("Если продать части по отдельности по минимальным ценам продавцов в игре, выйдет {0} пл — на {1} больше, чем комплектом. Сделок при этом понадобится больше.", fmt(pv.total), fmt(pv.diff)) },
      t("по частям +{0} пл", fmt(pv.diff))));
  }
  return cell;
}
function trendCell(set) {
  const m = S.market.get(set.slug);
  const cell = h("div", { class: "c-trend trend" });
  if (!m || m.state === "loading") {
    cell.append(h("div", { class: "trend-text" }, h("span", { class: "skeleton", style: "width:110px;height:18px" })),
      h("span", { class: "skeleton", style: "width:116px;height:26px" }));
    return cell;
  }
  const trend = m.state === "done" ? m.data.trend : null;
  if (!trend) { cell.append(h("div", { class: "trend-text dim" }, t("нет данных"))); return cell; }
  const [label, ico, cls] = DIR[trend.direction] || DIR.unknown;
  const main = h("div", { class: "trend-main" }, h("span", { class: "dir " + cls }, icon(ico)), h("span", null, label));
  if (trend.change != null) main.append(h("span", { class: "pct num " + cls }, pct(trend.change)));
  const sub = trend.change == null ? (trend.reason || "")
    : trend.period_days < 80 ? t("{0} → {1} пл за {2} дн.", fmt(trend.start_price), fmt(trend.end_price), trend.period_days)
    : t("{0} → {1} пл", fmt(trend.start_price), fmt(trend.end_price));
  cell.append(h("div", { class: "trend-text" }, main, h("div", { class: "sub num" }, sub)), sparkline(trend));
  return cell;
}

// ----------------------------------------------------------------- details
const AVAIL = {
  missions: ["on", t("падает в миссиях")],
  special: ["special", t("особые реликвии")],
  vaulted: ["", t("в хранилище")],
  unknown: ["", t("нет данных о реликвиях")],
};
function relicTitle(part) {
  if (!part.relics.length) return "";
  return part.relics.map((r) => (r.drops ? t("{0} — падает", r.name) : r.wfm_vaulted === false ? t("{0} — вне миссий", r.name) : t("{0} — в хранилище", r.name))).join("\n");
}
/* Who to write to about a missing part: its cheapest sellers who are in the game, each with a message
   in the site's own format.  They come with the price of the part, in the same answer of the market. */
function sellersBlock(set, part, row) {
  if (!Array.isArray(row.sellers)) return null;      // an answer without sellers: the server is still the one started before the update
  const box = h("div", { class: "sellers" });
  if (!row.sellers.length) {
    box.append(h("div", { class: "sellers-none" },
      !row.orders_at ? t("маркет не ответил")
        : row.price == null ? t("Эту часть сейчас никто не продаёт.")
          : t("В игре эту часть сейчас никто не продаёт. На сайте её предлагают от {0} пл.", fmt(row.price))));
    return box;
  }
  box.append(h("div", { class: "sellers-title" }, t("Продавцы в игре")));
  for (const sl of row.sellers) {
    const key = part.slug + "|" + sl.user;
    const copied = S.copied.has(key);
    const meta = [typeof sl.reputation === "number" && sl.reputation > 0 ? t("репутация {0}", sl.reputation) : null,
      sl.quantity > 1 ? t("у него {0} шт.", sl.quantity) : null].filter(Boolean).join(" · ");
    box.append(h("div", { class: "seller" },
      h("span", { class: "seller-name", title: sl.user }, sl.user),
      h("div", { class: "seller-price num" }, h("b", null, pl(sl.platinum)),
        sl.count > 1 ? h("div", { class: "sub" }, t("за {0}: {1}", sl.count, fmt(sl.platinum * sl.count))) : null),
      h("div", { class: "seller-actions" },
        h("button", { class: "btn subtle", title: sl.message,
          onclick: async () => { await copyText(sl.message, t("Сообщение скопировано — вставьте его в чат игры")); S.copied.add(key); refreshRow(set.slug); } },
          icon(copied ? "check" : "copy"), t("Сообщение")),
        h("button", { class: "btn subtle", title: t("Покупка состоялась: занести в инвентарь {0} шт.", sl.count),
          onclick: () => boughtPart(set, part, sl) }, t("Купил"))),
      meta ? h("div", { class: "seller-meta" }, meta) : null,
      // after the first press the text stays in sight: it shows what went to the clipboard and can be selected by hand
      copied ? h("input", { class: "msg-line", readonly: true, value: sl.message, "aria-label": t("Сообщение продавцу"),
        onfocus: (e) => e.target.select() }) : null));
  }
  return box;
}
/* "Купил": the part goes into the inventory at once.  The app cannot see a trade, it is told about it;
   the message that follows offers to take the press back. */
async function boughtPart(set, part, sl) {
  try {
    S.data = await post("/api/inventory/bought", { slug: part.slug, count: sl.count, platinum: sl.platinum, seller: sl.user });
  } catch (err) { toast(err.message); return; }
  const complete = S.data.complete.some((x) => x.slug === set.slug);
  const what = part.name + (sl.count > 1 ? ` ×${sl.count}` : "");
  afterPurchase(set.slug, complete);
  toast(complete ? t("Куплено: {0}. Комплект «{1}» собран.", what, set.title) : t("Куплено: {0}. Часть занесена в инвентарь.", what),
    { label: t("Отменить"), run: () => undoBought(set.slug, part, sl.count) });
}
async function undoBought(setSlug, part, count) {
  try { S.data = await post("/api/inventory/bought", { slug: part.slug, count, undo: true }); }
  catch (err) { toast(err.message); return; }
  afterPurchase(setSlug, false);
  toast(t("Покупка отменена: часть убрана из инвентаря"));
}
// the inventory changed through a purchase (or its undoing): show it, and do not announce it as news
function afterPurchase(setSlug, complete) {
  S.parts.delete("missing:" + setSlug);             // what this set lacks is different now
  if (complete) S.open.delete(setSlug);             // it has moved to the complete sets
  render();
  queueMarket(false);                               // a set that has just become complete has no price yet
  const still = S.data.partial.find((x) => x.slug === setSlug);
  if (still && S.open.has(setSlug)) loadParts(still, "missing", false);
  ownUpdateSeen();
}
function partsPanel(set, scope) {
  const key = scope + ":" + set.slug;
  const pm = S.parts.get(key);
  const priceOf = {};
  if (pm && pm.state === "done") for (const p of pm.data.parts) priceOf[p.slug] = p;
  const list = h("div", { class: "parts" }, set.parts.map((p) => {
    const [dotCls, availText] = AVAIL[p.availability] || AVAIL.unknown;
    const lacks = scope === "missing" && p.missing > 0;
    let priceText = "";
    if (pm && pm.state === "loading" && (scope === "all" || lacks)) priceText = h("span", { class: "skeleton", style: "width:44px" });
    else if (priceOf[p.slug]) priceText = priceOf[p.slug].price != null ? pl(priceOf[p.slug].price) : "—";
    const line = h("div", { class: "part" },
      thumb(p.thumb, true),
      h("div", null,
        h("div", { class: "part-name", title: p.en }, p.label),
        h("div", { class: "part-meta", title: relicTitle(p) }, h("span", { class: "dot " + dotCls }), availText)),
      h("div", { class: "have num" + (lacks ? " lack" : "") },
        lacks ? t("не хватает {0}", p.missing) : [t("есть {0}", p.owned), p.quantity > 1 ? t("нужно {0}", p.quantity) : null].filter(Boolean).join(" · ")),
      h("div", { class: "part-price num" }, priceText));
    return lacks && priceOf[p.slug] ? [line, sellersBlock(set, p, priceOf[p.slug])] : line;
  }));
  const totals = h("div", { class: "totals num" });
  const m = S.market.get(set.slug);
  const setPrice = setPriceOf(set.slug);
  if (scope === "all") {
    if (setPrice != null) totals.append(h("span", null, t("Комплектом: "), h("b", null, pl(setPrice))));
    if (pm && pm.state === "done" && pm.data.total != null) totals.append(h("span", null, t("По частям: "), h("b", null, pl(pm.data.total))));
    const buyMax = m && m.state === "done" && m.data.price ? m.data.price.buy_max : null;
    if (buyMax != null) totals.append(h("span", null, t("Покупают за: "), h("b", null, pl(buyMax))));
  } else {
    if (pm && pm.state === "done") {
      totals.append(h("span", null, t("Докупить недостающее: "), h("b", null, pm.data.total != null ? pl(pm.data.total) : t("нет предложений"))));
    }
    if (setPrice != null) totals.append(h("span", null, t("Готовый комплект стоит: "), h("b", null, pl(setPrice))));
  }
  return h("div", { class: "panel" },
    h("div", { class: "panel-title" }, h("span", null, t("Состав комплекта")), h("span", null, t("цены частей — минимальные у продавцов в игре"))),
    list, totals.childNodes.length ? totals : null);
}
function chartPanel(set) {
  const m = S.market.get(set.slug);
  const panel = h("div", { class: "panel" });
  const title = h("div", { class: "panel-title" }, h("span", null, t("Цена закрытых сделок за 90 дней, платина")));
  panel.append(title);
  if (!m || m.state === "loading") { panel.append(h("span", { class: "skeleton", style: "width:100%;height:150px" })); return panel; }
  const trend = m.state === "done" ? m.data.trend : null;
  if (!trend) { panel.append(h("div", { class: "chart-note" }, t("Статистика сделок не загрузилась."))); return panel; }
  const asTable = S.tableView.has(set.slug);
  title.append(h("div", { class: "seg" },
    h("button", { "aria-pressed": String(!asTable), onclick: () => { S.tableView.delete(set.slug); refreshRow(set.slug); } }, t("График")),
    h("button", { "aria-pressed": String(asTable), onclick: () => { S.tableView.add(set.slug); refreshRow(set.slug); } }, t("Таблица"))));
  if (asTable) {
    panel.append(priceTable(trend));
  } else {
    // drawn at the panel's real width, so labels keep their size; redrawn when the window changes
    const wrap = h("div", { class: "chart-wrap" });
    let drawn = 0;
    const draw = () => {
      const w = Math.floor(wrap.clientWidth);
      if (!w || w === drawn) return;
      drawn = w;
      wrap.replaceChildren(priceChart(trend, w));
    };
    new ResizeObserver(draw).observe(wrap);
    panel.append(
      h("div", { class: "chart-legend" },
        h("span", null, h("span", { class: "key", style: "background:var(--series)" }), t("среднее за 7 дней")),
        h("span", null, h("span", { class: "key thin", style: "background:var(--series-quiet)" }), t("цена за день (медиана сделок)"))),
      wrap);
  }
  let note;
  if (trend.change != null) {
    note = t("Тренд: первые {0} дн. в среднем {1} пл, последние {2} дн. — {3} пл ({4}). Сделок за период: {5}.", trend.window_days, fmt(trend.start_price), trend.window_days, fmt(trend.end_price), pct(trend.change), fmt(trend.volume));
  } else {
    note = (trend.reason ? trend.reason[0].toUpperCase() + trend.reason.slice(1) + ". " : "") + t("Сделок за период: {0}.", fmt(trend.volume));
  }
  panel.append(h("div", { class: "chart-note" }, note));
  return panel;
}
function detail(set, scope) {
  const left = h("div", null);
  if (set.mastery && set.mastery.warn && set.complete > 0) {
    left.append(h("div", { class: "callout" }, icon("alert"),
      h("div", null, t("Этот комплект у вас не освоен. Если продать его сейчас, очки мастерства за него придётся добывать заново — сначала постройте и прокачайте."))));
  }
  const pm = scope === "missing" ? S.parts.get("missing:" + set.slug) : null;
  if (partsStale(pm)) {
    left.append(h("div", { class: "callout" }, icon("alert"),
      h("div", null, t("Предложения запрошены {0}: продавцы могли выйти из игры, а цены — измениться. Обновите, прежде чем писать.", stampFmt.format(new Date(pm.data.oldest_at * 1000))))));
  }
  left.append(partsPanel(set, scope));
  const asking = Boolean(pm && pm.state === "loading");
  left.append(h("div", { class: "actions" },
    h("a", { class: "link", href: set.market_url, target: "_blank", rel: "noopener" }, icon("external"), t("Открыть на warframe.market")),
    scope === "missing" ? h("button", { class: "btn subtle", disabled: asking,
      title: t("Заново запросить предложения по недостающим частям: продавцы меняются каждую минуту"),
      onclick: () => loadParts(set, "missing", true) }, icon("refresh", asking ? "spin" : ""), asking ? t("Запрашиваю…") : t("Обновить продавцов")) : null,
    scope === "all" && set.complete > 0 ? h("button", { class: "btn subtle", title: t("Строка для торгового чата с этим комплектом и его ценой"),
      onclick: () => {
        if (setPriceOf(set.slug) == null) { toast(t("Цена ещё не загружена или комплект сейчас никто не продаёт")); return; }
        copyText(listingText([set]), t("Объявление скопировано — вставьте его в чат игры"));
      } }, icon("copy"), t("Скопировать объявление")) : null,
    scope === "all" && set.complete > 0 ? h("button", { class: "btn subtle", title: t("Комплект продан: убрать его части из инвентаря и записать сделку в журнал"),
      onclick: () => openSellDialog(set, { price: setPriceOf(set.slug) }) }, icon("check"), t("Продал…")) : null));
  return h("div", { class: "detail" }, left, h("div", null, chartPanel(set)));
}

// the offers behind the prices of the parts go out of date fast: sellers leave the game
function partsStale(entry) {
  return Boolean(entry && entry.state === "done" && entry.data.oldest_at && Date.now() / 1000 - entry.data.oldest_at > entry.data.ttl_orders);
}
async function loadParts(set, scope, force) {
  const key = scope + ":" + set.slug;
  const cur = S.parts.get(key);
  // what is known is kept -- except the sellers of the missing parts once they are out of date:
  // a message is written to them, so they are asked anew (the server answers from its cache while that is fresh)
  if (!force && cur && cur.state !== "error" && !(scope === "missing" && partsStale(cur))) return;
  S.parts.set(key, { state: "loading" });
  refreshRow(set.slug);
  try {
    const data = await api(`/api/parts-market?slug=${set.slug}&scope=${scope}${force ? "&force=1" : ""}`);
    S.parts.set(key, { state: "done", data });
  } catch (err) {
    S.parts.set(key, { state: "error", error: err.message });
  }
  refreshRow(set.slug);
}
async function loadMarket(slug, force) {
  S.market.set(slug, { state: "loading" });
  refreshRow(slug);
  try {
    const data = await api(`/api/market?slug=${slug}${force ? "&force=1" : ""}`);
    S.market.set(slug, { state: "done", data });
  } catch (err) {
    S.market.set(slug, { state: "error", error: err.message });
  }
  refreshRow(slug);
}

// ----------------------------------------------------------------- rows
function toggleRow(set, scope) {
  if (S.open.has(set.slug)) {
    S.open.delete(set.slug);
  } else {
    S.open.add(set.slug);
    loadParts(set, scope, false);
    const m = S.market.get(set.slug);
    if (!m || m.state === "error") loadMarket(set.slug, false);
  }
  refreshRow(set.slug);
}
function rowHead(set, scope, cells) {
  return h("button", { class: "row-head", "aria-expanded": String(S.open.has(set.slug)), onclick: () => toggleRow(set, scope) },
    cells, h("span", { class: "chev" }, icon("chevron")));
}
function completeRow(set) {
  const open = S.open.has(set.slug);
  return h("div", { class: "row" + (open ? " open" : ""), "data-slug": set.slug },
    rowHead(set, "all", [setNameCell(set), priceCell(set), vaultCell(set), trendCell(set)]),
    open ? detail(set, "all") : null);
}
function setPriceOf(slug) {
  const m = S.market.get(slug);
  if (m && m.state === "done" && m.data.price) return m.data.price.value;
  const lite = S.lite.get(slug);
  return lite && lite.price ? lite.price.value : null;
}
function buyCell(set) {
  const pm = S.parts.get("missing:" + set.slug);
  const cell = h("div", { class: "c-buy" });
  if (!pm) cell.append(h("span", { class: "dim" }, "—"));
  else if (pm.state === "loading") cell.append(h("span", { class: "skeleton", style: "width:60px;height:18px" }));
  else if (pm.state === "error") cell.append(h("span", { class: "dim" }, t("нет данных")));
  else if (pm.data.total == null) cell.append(h("span", { class: "dim" }, t("нет предложений")));
  else cell.append(h("div", { class: "price num", style: "font-size:16px" }, "≈ " + fmt(pm.data.total), h("span", { class: "unit" }, t("пл"))));
  const whole = setPriceOf(set.slug);
  if (pm && pm.state === "done" && whole != null) cell.append(h("div", { class: "sub num", title: t("Минимальная цена готового комплекта") }, t("комплект: {0} пл", fmt(whole))));
  return cell;
}
function partialRow(set) {
  const open = S.open.has(set.slug);
  const need = set.parts.reduce((a, p) => a + p.quantity, 0);
  const have = set.parts.reduce((a, p) => a + Math.min(p.owned, p.quantity), 0);
  const missing = set.parts.filter((p) => p.missing > 0);
  return h("div", { class: "row" + (open ? " open" : ""), "data-slug": set.slug },
    rowHead(set, "missing", [
      setNameCell(set),
      h("div", { class: "meter", title: t("Собрано {0} из {1} частей", have, need) },
        h("div", { class: "meter-track" }, h("div", { class: "meter-fill", style: `width:${Math.round(have / need * 100)}%` })),
        h("span", { class: "meter-text num" }, t("{0} из {1}", have, need))),
      h("div", { class: "c-missing missing" }, missing.map((p) => h("span", { class: "chip", title: p.name }, p.label + (p.missing > 1 ? ` ×${p.missing}` : "")))),
      vaultCell(set),
      buyCell(set),
    ]),
    open ? detail(set, "missing") : null);
}
function refreshRow(slug) {
  if (!S.data || (S.tab !== "complete" && S.tab !== "partial")) return;      // other tabs draw their own rows
  const old = document.querySelector(`.row[data-slug="${slug}"]`);
  if (!old) return;
  const inComplete = S.data.complete.find((x) => x.slug === slug);
  const set = inComplete || S.data.partial.find((x) => x.slug === slug);
  if (!set) return;
  const tabNow = S.tab === "partial" ? "partial" : "complete";
  if ((tabNow === "complete") !== Boolean(inComplete)) return;
  old.replaceWith(inComplete ? completeRow(set) : partialRow(set));
}

// ----------------------------------------------------------------- sorting & filtering
function matchesQuery(set) {
  const q = fold(S.query.trim());
  if (!q) return true;
  const hay = fold([set.title, set.title_en, CATEGORY[set.category] || "", ...set.parts.map((p) => p.label)].join(" "));
  return q.split(/\s+/).every((w) => hay.includes(w));
}
const VAULT_ORDER = { vaulted: 0, partial: 1, special: 2, available: 3, unknown: 4 };
function sortSets(list, tab) {
  const { key, dir } = S.sort[tab];
  const mul = dir === "asc" ? 1 : -1;
  const byName = (a, b) => a.title.localeCompare(b.title, LOCALE);
  const marketValue = (set, fn) => {
    const m = S.market.get(set.slug);
    return m && m.state === "done" ? fn(m.data) : null;
  };
  const num = (get) => (a, b) => {
    const va = get(a), vb = get(b);
    if (va == null && vb == null) return byName(a, b);
    if (va == null) return 1;            // unknown values always sink to the bottom
    if (vb == null) return -1;
    return (va - vb) * mul || byName(a, b);
  };
  let cmp;
  if (key === "name") cmp = (a, b) => byName(a, b) * mul;
  else if (key === "price") {
    // while prices are still arriving keep the calm alphabetical order, then sort once
    if (S.queue.running) cmp = byName;
    else cmp = num((x) => marketValue(x, (d) => (d.price && d.price.value != null ? d.price.value : null)));
  } else if (key === "trend") {
    if (S.queue.running) cmp = byName;
    else cmp = num((x) => marketValue(x, (d) => (d.trend ? d.trend.change : null)));
  } else if (key === "vault") cmp = (a, b) => (VAULT_ORDER[a.vault.state] - VAULT_ORDER[b.vault.state]) * mul || byName(a, b);
  else if (key === "missing") cmp = (a, b) => (a.missing_count - b.missing_count) * mul || byName(a, b);
  else if (key === "buy") cmp = num((x) => { const pm = S.parts.get("missing:" + x.slug); return pm && pm.state === "done" ? pm.data.total : null; });
  else cmp = byName;
  return [...list].sort(cmp);
}
function sortButton(tab, key, label, title) {
  const cur = S.sort[tab];
  const active = cur.key === key;
  return h("button", {
    class: "sort", title: title || "", "aria-sort": active ? (cur.dir === "asc" ? "ascending" : "descending") : "none",
    onclick: () => {
      const firstDir = key === "name" || key === "missing" || key === "vault" || key === "buy" || (tab === "ducats" && key === "price") ? "asc" : "desc";
      S.sort[tab] = active ? { key, dir: cur.dir === "asc" ? "desc" : "asc" } : { key, dir: firstDir };
      renderView();
    },
  }, label, icon("down"));
}

// ----------------------------------------------------------------- views
function emptyState(title, text, withButton) {
  const art = h("div", { class: "empty-art" });
  art.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12 2.5 20.5 12 12 21.5 3.5 12Z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 7.5 16 12l-4 4.5L8 12Z" fill="currentColor"/></svg>';
  return h("div", { class: "card empty" + (withButton ? "" : " small") }, withButton ? art : null, h("h2", null, title), h("p", null, text),
    withButton ? h("div", { class: "empty-actions" },
      h("button", { class: "btn primary", onclick: openUpdateDialog }, icon("image"), h("span", null, t("Как добавить инвентарь"))),
      h("button", { class: "btn ghost", title: t("Показать программу на выдуманном инвентаре"), onclick: () => setDemo(true) }, h("span", null, t("Посмотреть на примере")))) : null);
}
function viewComplete() {
  const d = S.data;
  if (!d.complete.length) {
    return d.inventory.distinct
      ? emptyState(t("Полных комплектов пока нет"), t("Загляните на вкладку «Почти собраны»: там видно, каких частей не хватает до ближайших комплектов."), false)
      : emptyState(t("Добавьте свой инвентарь"), t("Сделайте скриншоты прайм-частей в игре — приложение прочитает их, найдёт полные комплекты, покажет цены на warframe.market и подскажет, что ещё не освоено."), true);
  }
  const list = sortSets(d.complete.filter(matchesQuery), "complete");
  const card = h("div", { class: "card complete" },
    h("div", { class: "cols" },
      sortButton("complete", "name", t("Комплект")),
      sortButton("complete", "price", t("Цена на warframe.market"), t("Минимальная цена продажи комплекта у игроков, которые сейчас в игре")),
      sortButton("complete", "vault", t("В хранилище"), t("По официальным таблицам дропа Digital Extremes")),
      sortButton("complete", "trend", t("Цена за 3 месяца"), t("Сравнение начала и конца 90-дневной истории закрытых сделок")),
      h("span")),
    list.length ? list.map(completeRow) : h("div", { class: "empty small" }, h("p", null, t("Ничего не найдено."))));
  const pq = S.partsQueue;
  const tools = h("div", { class: "inv-tools", id: "sell-tools" },
    h("button", { class: "btn ghost", title: t("Запросить цены всех частей и отметить комплекты, которые выгоднее продать по частям"),
      onclick: () => (pq.running ? stopPartsQueue() : runPartsQueue()) },
      icon(pq.running ? "close" : "refresh"), h("span", null, pq.running ? t("Остановить ({0} из {1})", pq.done, pq.total) : t("Комплектом или по частям?"))),
    h("button", { class: "btn ghost", onclick: openListingDialog }, icon("copy"), h("span", null, t("Объявление для чата"))),
    h("button", { class: "btn ghost", title: t("Игроки, которые прямо сейчас в игре и покупают ваши комплекты"), onclick: openSellNowDialog },
      icon("up"), h("span", null, t("Покупатели сейчас"))),
    h("button", { class: "btn ghost", title: t("Подобрать, что продать, чтобы получить нужное число платины"), onclick: openGoalDialog },
      icon("flat"), h("span", null, t("Цель по платине"))),
    h("span", { class: "sub" }, t("Сравнение запрашивает цены частей: по одному запросу, не чаще двух в секунду.")));
  return h("div", null, tools, card);
}
function viewPartial() {
  const d = S.data;
  if (!d.partial.length) return emptyState(t("Начатых комплектов нет"), d.inventory.distinct ? t("Все ваши части уже складываются в полные комплекты.") : t("Сначала добавьте инвентарь."), false);
  let list = d.partial.filter(matchesQuery);
  if (S.nearFilter !== "all") list = list.filter((x) => x.missing_count <= Number(S.nearFilter));
  list = sortSets(list, "partial");
  const select = h("select", { class: "select", "aria-label": t("Сколько частей не хватает"), onchange: (e) => { S.nearFilter = e.target.value; renderView(); } },
    [["all", t("Не хватает: сколько угодно")], ["1", t("Не хватает 1 части")], ["2", t("Не хватает до 2 частей")], ["3", t("Не хватает до 3 частей")]]
      .map(([v, text]) => h("option", { value: v, selected: S.nearFilter === v }, text)));
  const bq = S.buyQueue;
  const buyBtn = h("button", { class: "btn ghost", onclick: () => (bq.running ? stopBuyQueue() : runBuyQueue(list)) },
    icon(bq.running ? "close" : "refresh"),
    h("span", null, bq.running ? t("Остановить ({0} из {1})", bq.done, bq.total) : t("Узнать цены недостающих частей")));
  const tools = h("div", { class: "inv-tools" }, select, buyBtn,
    h("span", { class: "sub" }, t("Запросы идут по одному, не чаще двух в секунду.")));
  const card = h("div", { class: "card partial" },
    h("div", { class: "cols" },
      sortButton("partial", "name", t("Комплект")),
      sortButton("partial", "missing", t("Собрано"), t("Сначала те, до которых ближе всего")),
      h("span", null, t("Не хватает")),
      sortButton("partial", "vault", t("В хранилище")),
      sortButton("partial", "buy", t("Докупить"), t("Минимальные цены недостающих частей у продавцов в игре")),
      h("span")),
    list.length ? list.map(partialRow) : h("div", { class: "empty small" }, h("p", null, t("Под этот фильтр ничего не подходит."))));
  return h("div", null, tools, card);
}
function stopBuyQueue() { S.buyQueue.gen++; S.buyQueue.running = false; renderView(); }
async function runBuyQueue(list) {
  const bq = S.buyQueue;
  const gen = ++bq.gen;
  const todo = list.filter((x) => { const pm = S.parts.get("missing:" + x.slug); return !pm || pm.state === "error"; });
  if (!todo.length) { toast(t("Цены уже загружены.")); return; }
  Object.assign(bq, { running: true, done: 0, total: todo.length });
  renderView();
  for (const set of todo) {
    if (gen !== bq.gen) return;
    if (setPriceOf(set.slug) == null && !S.lite.has(set.slug)) {
      // one extra request: what the finished set sells for, to weigh against buying the parts
      try { S.lite.set(set.slug, await api(`/api/market?slug=${set.slug}&lite=1`)); } catch (e) { /* shown as missing */ }
    }
    await loadParts(set, "missing", false);
    bq.done++;
    const label = document.querySelector(".inv-tools .btn span:not(.ico)");
    if (label && gen === bq.gen) label.textContent = t("Остановить ({0} из {1})", bq.done, bq.total);
  }
  if (gen === bq.gen) { bq.running = false; renderView(); }
}

function viewParts() {
  const d = S.data;
  const sets = [...d.complete, ...d.partial].filter(matchesQuery).sort((a, b) => a.title.localeCompare(b.title, LOCALE));
  const input = h("input", { type: "search", placeholder: t("Добавить часть: начните вводить название"), autocomplete: "off", spellcheck: "false" });
  const sug = h("div", { class: "suggest", hidden: true });
  const addBox = h("div", { class: "add-box" }, h("label", { class: "search" }, icon("plus"), input), sug);
  async function suggest() {
    const q = fold(input.value.trim());
    if (q.length < 2) { sug.hidden = true; return; }
    if (!S.allParts) { try { S.allParts = (await api("/api/parts")).parts; } catch (e) { S.allParts = []; } }
    const words = q.split(/\s+/);
    const found = S.allParts.filter((p) => { const hay = fold(p.name + " " + p.en); return words.every((w) => hay.includes(w)); }).slice(0, 12);
    sug.replaceChildren(...(found.length ? found.map((p) => h("button", {
      onclick: async () => {
        const owned = ownedCount(p.slug);
        await setCount(p.slug, owned + 1);
        toast(t("Добавлено: {0}", p.name));
      },
    }, h("span", null, p.name), h("small", null, p.set))) : [h("div", { class: "sub", style: "padding:10px" }, t("Такой прайм-части в каталоге нет"))]));
    sug.hidden = false;
  }
  input.addEventListener("input", suggest);
  input.addEventListener("focus", suggest);
  const tools = h("div", { class: "inv-tools" }, addBox,
    h("span", { class: "sub" }, t("Здесь можно поправить количество вручную, если скриншот прочитан неточно.")));
  if (!sets.length) {
    return h("div", null, tools, emptyState(d.inventory.distinct ? t("Ничего не найдено") : t("Список частей пуст"),
      d.inventory.distinct ? t("Попробуйте другой запрос.") : t("Добавьте части через скриншоты или вручную — поле выше."), false));
  }
  const grid = h("div", { class: "inv-grid" }, sets.map((set) => h("div", { class: "inv-card" },
    h("div", { class: "inv-head" },
      h("div", { class: "inv-title", title: set.title_en }, set.title),
      set.complete ? h("span", { class: "times" }, "×" + set.complete) : h("span", { class: "chip" }, t("не хватает {0}", set.missing_count))),
    set.parts.map((p) => h("div", { class: "inv-line" + (p.owned ? "" : " zero") },
      h("span", { class: "name", title: p.name }, p.label, p.quantity > 1 ? h("span", { class: "need" }, t("нужно {0}", p.quantity)) : null),
      h("span", { class: "stepper" },
        h("button", { class: "step", "aria-label": t("Меньше"), disabled: p.owned <= 0, onclick: () => setCount(p.slug, p.owned - 1) }, icon("minus")),
        h("span", { class: "qty" + (p.owned ? "" : " zero") }, String(p.owned)),
        h("button", { class: "step", "aria-label": t("Больше"), onclick: () => setCount(p.slug, p.owned + 1) }, icon("plus"))))))));
  return h("div", null, tools, grid);
}
function ownedCount(slug) {
  for (const set of [...S.data.complete, ...S.data.partial]) for (const p of set.parts) if (p.slug === slug) return p.owned;
  return 0;
}
async function setCount(slug, count) {
  try {
    S.data = await post("/api/inventory/set", { slug, count: Math.max(0, count) });
    render();
    queueMarket(false);
  } catch (err) { toast(err.message); }
}

// ----------------------------------------------------------------- collection: every prime set, what is owned and what is mastered
const C = { data: null, stale: true, loading: false, error: "", show: "all", category: "all" };
async function loadCollection() {
  if (C.loading) return;
  C.loading = true;
  try { C.data = (await api("/api/collection")).sets; C.stale = false; C.error = ""; }
  catch (err) { C.error = err.message; }
  C.loading = false;
  if (S.tab === "collection") renderView();
}
const C_SHOW = [
  ["all", t("Все")],
  ["todo", t("Не освоено")],
  ["mastered", t("Освоено")],
  ["complete", t("Есть комплект")],
  ["started", t("Начато")],
  ["empty", t("Нет частей")],
];
function collectionMatch(s) {
  if (C.category !== "all" && s.category !== C.category) return false;
  const m = s.mastery.state;
  if (C.show === "todo" && (m === "mastered" || m === "na")) return false;
  if (C.show === "mastered" && m !== "mastered") return false;
  if (C.show === "complete" && !s.complete) return false;
  if (C.show === "started" && (s.complete || !s.have)) return false;
  if (C.show === "empty" && s.have) return false;
  const q = fold(S.query.trim());
  if (!q) return true;
  const hay = fold([s.title, s.title_en, CATEGORY[s.category] || ""].join(" "));
  return q.split(/\s+/).every((w) => hay.includes(w));
}
function collectionTile(s) {
  const m = s.mastery;
  let stock;
  if (s.complete) stock = h("span", { class: "chip good" }, icon("check"), s.complete > 1 ? t("комплект ×{0}", s.complete) : t("комплект собран"));
  else if (s.have) {
    stock = h("div", { class: "meter", title: t("Собрано {0} из {1} частей", s.have, s.need) },
      h("div", { class: "meter-track" }, h("div", { class: "meter-fill", style: `width:${Math.round(s.have / s.need * 100)}%` })),
      h("span", { class: "meter-text num" }, t("{0} из {1}", s.have, s.need)));
  } else stock = h("span", { class: "sub" }, t("частей нет"));
  return h("div", { class: "col-tile" + (m.state === "mastered" ? " mastered" : "") + (s.complete ? " complete" : s.have ? "" : " none") },
    h("a", { class: "col-pic", href: s.market_url, target: "_blank", rel: "noopener", title: t("Открыть на warframe.market") }, thumb(s.thumb)),
    h("div", { class: "col-name", title: s.title_en }, s.title),
    h("div", { class: "col-meta" }, masteryChip(s) || h("span", { class: "chip quiet" }, m.label)),
    h("div", { class: "col-stock" }, stock));
}
function viewCollection() {
  if (C.stale && !C.loading) loadCollection();
  if (!C.data) {
    return C.error ? h("div", { class: "card empty small" }, h("h2", null, t("Не удалось загрузить список комплектов")), h("p", null, C.error),
      h("button", { class: "btn subtle", onclick: () => { C.error = ""; C.stale = true; renderView(); } }, t("Повторить")))
      : h("div", { class: "card" }, h("div", { class: "empty small" }, h("span", { class: "skeleton", style: "width:60%;height:18px" })));
  }
  const all = C.data;
  const can = all.filter((s) => s.mastery.state !== "na");
  const mastered = can.filter((s) => s.mastery.state === "mastered").length;
  const unknown = can.filter((s) => s.mastery.state === "unknown").length;
  const complete = all.filter((s) => s.complete).length, started = all.filter((s) => !s.complete && s.have).length;
  const bar = (label, value, total, note) => h("div", { class: "col-bar" },
    h("div", { class: "col-bar-head" }, h("span", null, label), h("b", { class: "num" }, t("{0} из {1}", value, total))),
    h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: `width:${total ? Math.round(value / total * 100) : 0}%` })),
    h("div", { class: "sub" }, note || " "));
  const list = all.filter(collectionMatch);
  const cats = Object.keys(CATEGORY).filter((c) => all.some((s) => s.category === c));
  const tools = h("div", { class: "inv-tools" },
    h("div", { class: "seg" }, C_SHOW.map(([value, label]) => h("button", { "aria-pressed": String(C.show === value), onclick: () => { C.show = value; renderView(); } }, label))),
    h("select", { class: "select", "aria-label": t("Вид предметов"), onchange: (e) => { C.category = e.target.value; renderView(); } },
      h("option", { value: "all", selected: C.category === "all" }, t("Все виды")),
      cats.map((c) => h("option", { value: c, selected: C.category === c }, CATEGORY[c]))),
    h("span", { class: "sub" }, tn("показан # комплект|показано # комплекта|показано # комплектов", list.length)));
  return h("div", null,
    h("div", { class: "card col-summary" },
      bar(t("Освоено"), mastered, can.length, unknown ? t("ещё не отмечено: {0} — щёлкните по метке у предмета", unknown) : ""),
      bar(t("Собрано комплектов"), complete, all.length, started ? t("начато, но не собрано: {0}", started) : "")),
    tools,
    list.length ? h("div", { class: "col-grid" }, list.map(collectionTile)) : h("div", { class: "card empty small" }, h("p", null, t("Под этот фильтр ничего не подходит."))));
}


// ----------------------------------------------------------------- ducats: which set is the cheapest way to ducats
// Every set of the catalog, not only the owned ones: buy it whole, hand its parts in at the ducat kiosk.
const D = {
  list: null, state: "idle", error: "", ttl: 600,
  price: new Map(),          // set slug -> {state: loading|done|error, price, at, error}
  queue: { running: false, done: 0, total: 0, gen: 0 },
  calc: { target: 1000, plan: null, state: "idle", error: "", exclude: new Set(), done: [], copied: new Set() },
};
try {
  const want = Number(localStorage.getItem("primesets-ducat-target"));
  if (want >= 5 && want <= 50000) D.calc.target = Math.round(want);
} catch (e) { /* storage unavailable */ }
const rateFmt = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
async function loadDucats() {
  if (D.state === "loading") return;
  D.state = "loading";
  try {
    const res = await api("/api/ducats");
    D.list = res.sets;
    D.ttl = res.ttl_orders || 600;
    // what the app already knows from earlier requests, however old: shown at once, with its age
    for (const s of D.list) if (s.price && !D.price.has(s.slug)) D.price.set(s.slug, { state: "done", price: s.price, at: s.orders_at });
    D.state = "done";
  } catch (err) {
    D.state = "error"; D.error = err.message;
  }
  renderTabs();
  if (S.tab === "ducats") renderView();
}
function ducatPrice(set) {
  const p = D.price.get(set.slug);
  return p && p.state === "done" && p.price && p.price.value != null ? p.price.value : null;
}
function ducatRate(set) {
  const v = ducatPrice(set);
  return v ? set.ducats / v : null;
}
function ducatBest() {
  let best = 0;
  for (const s of D.list || []) { const r = ducatRate(s); if (r != null && r > best) best = r; }
  return best;
}
function sortDucats(list) {
  const { key, dir } = S.sort.ducats;
  const mul = dir === "asc" ? 1 : -1;
  const byName = (a, b) => a.title.localeCompare(b.title, LOCALE);
  const num = (get) => (a, b) => {
    const va = get(a), vb = get(b);
    if (va == null && vb == null) return byName(a, b);
    if (va == null) return 1;                  // sets without a price sink to the bottom
    if (vb == null) return -1;
    return (va - vb) * mul || byName(a, b);
  };
  const cmp = key === "name" ? (a, b) => byName(a, b) * mul
    : key === "ducats" ? num((x) => x.ducats)
    : key === "price" ? num(ducatPrice)
    : num(ducatRate);
  return [...list].sort(cmp);
}
function ducatDetail(set) {
  const p = D.price.get(set.slug);
  const value = ducatPrice(set);
  const parts = h("div", { class: "panel" },
    h("div", { class: "panel-title" }, h("span", null, t("Что даёт комплект в киоске дукатов")), h("span", null, t("части сдаются по одной"))),
    h("div", { class: "ducat-list" }, set.parts.map((x) => h("div", { class: "ducat-line" },
      h("span", { title: x.name }, x.label + (x.quantity > 1 ? ` ×${x.quantity}` : "")),
      h("span", { class: "num" }, String((x.ducats || 0) * x.quantity))))),
    h("div", { class: "totals num" }, h("span", null, t("Всего: "), h("b", null, tn("# дукат|# дуката|# дукатов", set.ducats)))));
  const offers = h("div", { class: "panel" },
    h("div", { class: "panel-title" }, h("span", null, t("Предложения на warframe.market")),
      p && p.state === "done" && p.at ? h("span", null, t("от {0}", stampFmt.format(new Date(p.at * 1000)))) : null));
  if (p && p.state === "done" && p.price && p.price.sell_prices.length) {
    offers.append(h("div", { class: "ducat-list" }, p.price.sell_prices.slice(0, 5).map((plat, i) => h("div", { class: "ducat-line" },
      h("span", null, i === 0 ? t("Самое дешёвое") : t("{0}-е по цене", i + 1)),
      h("span", { class: "num" }, t("{0} пл · {1} дук. за 1 пл", fmt(plat), rateFmt.format(set.ducats / plat)))))));
    if (value != null && p.price.sell_prices[0] !== value) {
      offers.append(h("div", { class: "sub" }, t("В расчёт взята цена {0} пл: это самое дешёвое предложение продавца, который сейчас в игре.", fmt(value))));
    }
  } else if (p && p.state === "error") {
    offers.append(h("div", { class: "dim" }, p.error || t("маркет не ответил")));
  } else if (p && p.state === "done") {
    offers.append(h("div", { class: "dim" }, t("Сейчас этот комплект никто из игроков онлайн не продаёт.")));
  } else {
    offers.append(h("div", { class: "dim" }, t("Цена ещё не запрашивалась.")));
  }
  const notes = [];
  if (set.owned > 0) notes.push(t("У вас уже есть этот комплект: {0}.", set.owned));
  if (set.vault.state === "vaulted") notes.push(t("Комплект в хранилище: такие обычно дорожают."));
  if (notes.length) offers.append(h("div", { class: "sub" }, notes.join(" ")));
  offers.append(
    h("div", { class: "actions" },
      h("a", { class: "link", href: set.market_url, target: "_blank", rel: "noopener" }, icon("external"), t("Открыть на warframe.market")),
      h("button", { class: "btn subtle", onclick: () => loadDucatPrice(set.slug, true) }, icon("refresh"), t("Обновить цену"))));
  return h("div", { class: "detail" }, parts, offers);
}
function ducatRow(set, best) {
  const open = S.open.has(set.slug);
  const p = D.price.get(set.slug);
  const value = ducatPrice(set), rate = ducatRate(set);
  const pieces = set.parts.reduce((a, x) => a + x.quantity, 0);
  const priceCell = h("div", { class: "c-price" });
  if (p && p.state === "loading" && value == null) {
    priceCell.append(h("span", { class: "skeleton", style: "width:56px;height:18px" }));
  } else if (value != null) {
    // one cheap offer is not a market: say what the next seller asks
    const next = p.price.sell_prices.filter((x) => x >= value)[1];
    const sub = [p.price.basis === "online" ? t("продавец не в игре")
      : p.price.sell_ingame ? t("в игре: {0}", p.price.sell_ingame + (p.price.sell_ingame >= 5 ? "+" : "")) : "",
      next != null && next > value ? t("далее {0}", fmt(next)) : ""].filter(Boolean).join(" · ");
    priceCell.append(
      h("div", { class: "price num" }, fmt(value), h("span", { class: "unit" }, t("пл"))),
      h("div", { class: "sub num" }, sub));
    priceCell.title = t("Продавцов в игре среди пяти самых дешёвых: {0}. Самые дешёвые предложения: {1} пл", p.price.sell_ingame, p.price.sell_prices.join(", "));
  } else if (p && p.state === "error") {
    priceCell.append(h("div", { class: "dim" }, t("нет данных")));
  } else if (p && p.state === "done") {
    priceCell.append(h("div", { class: "dim" }, t("нет предложений")));
  } else {
    priceCell.append(h("div", { class: "dim" }, "—"));
  }
  const rateCell = h("div", { class: "c-rate" });
  if (rate != null) {
    rateCell.title = t("{0} дукатов за {1} пл", set.ducats, fmt(value));
    rateCell.append(
      h("div", { class: "price num" }, rateFmt.format(rate), h("span", { class: "unit" }, t("дук. за 1 пл"))),
      h("div", { class: "meter-track rate-track" }, h("div", { class: "meter-fill", style: `width:${best ? Math.max(2, Math.round(rate / best * 100)) : 0}%` })));
  } else {
    rateCell.append(h("div", { class: "dim" }, "—"));
  }
  return h("div", { class: "row" + (open ? " open" : ""), "data-slug": set.slug },
    h("button", { class: "row-head", "aria-expanded": String(open),
      onclick: () => { if (open) S.open.delete(set.slug); else S.open.add(set.slug); refreshDucatRow(set.slug); } },
      h("div", { class: "item" }, thumb(set.thumb),
        h("div", { class: "item-text" },
          h("div", { class: "item-title" }, h("span", { title: set.title_en }, set.title)),
          h("div", { class: "item-meta" }, h("span", null, CATEGORY[set.category] || "")))),
      h("div", { class: "c-ducats" },
        h("div", { class: "ducat-num num" }, String(set.ducats)),
        h("div", { class: "sub num" }, tn("# часть|# части|# частей", pieces))),
      priceCell, rateCell,
      h("span", { class: "chev" }, icon("chevron"))),
    open ? ducatDetail(set) : null);
}
function refreshDucatRow(slug) {
  if (S.tab !== "ducats" || !D.list) return;
  const old = document.querySelector(`.ducats .row[data-slug="${slug}"]`);
  const set = D.list.find((x) => x.slug === slug);
  if (old && set) old.replaceWith(ducatRow(set, ducatBest()));
}
function ducatTools() {
  const q = D.queue;
  const asked = D.list.filter((s) => { const p = D.price.get(s.slug); return p && p.state === "done"; });
  const known = D.list.filter((s) => ducatPrice(s) != null).length;
  const oldest = asked.reduce((a, s) => Math.min(a, D.price.get(s.slug).at || a), Infinity);
  const label = q.running ? t("Остановить ({0} из {1})", q.done, q.total) : asked.length ? t("Обновить цены") : t("Узнать цены всех комплектов");
  let status;
  if (q.running) status = t("Запрашиваю цены: по одному запросу, не чаще двух в секунду.");
  else if (!asked.length) status = t("Цены ещё не запрашивались. Это {0} запросов к warframe.market — около полутора минут.", D.list.length);
  else status = Number.isFinite(oldest) ? t("Цены известны для {0} из {1} · самые старые от {2}.", known, D.list.length, stampFmt.format(new Date(oldest * 1000)))
    : t("Цены известны для {0} из {1}.", known, D.list.length);
  return h("div", { class: "inv-tools", id: "ducat-tools" },
    h("button", { class: "btn " + (asked.length || q.running ? "ghost" : "primary"), onclick: () => (q.running ? stopDucatQueue() : runDucatQueue(false)) },
      icon(q.running ? "close" : "refresh"), h("span", null, label)),
    h("button", { class: "btn ghost", title: t("Ваши лишние части: какие выгоднее сдать на дукаты, а какие продать за платину"), onclick: openBaroDialog },
      icon("cube"), h("span", null, t("Что сдать Баро"))),
    h("span", { class: "sub" }, status));
}
function updateDucatTools() {
  const old = $("#ducat-tools");
  if (old && S.tab === "ducats") old.replaceWith(ducatTools());
}
function viewDucats() {
  if (!D.list) {
    if (D.state === "error") {
      return h("div", { class: "card empty small" }, h("h2", null, t("Не удалось загрузить список комплектов")), h("p", null, D.error),
        h("button", { class: "btn subtle", onclick: () => { D.state = "idle"; loadDucats(); renderView(); } }, t("Повторить")));
    }
    loadDucats();
    return h("div", { class: "card" }, h("div", { class: "empty small" }, h("span", { class: "skeleton", style: "width:60%;height:18px" })));
  }
  const list = sortDucats(D.list.filter(matchesQuery));
  const best = ducatBest();
  const card = h("div", { class: "card ducats" },
    h("div", { class: "cols" },
      sortButton("ducats", "name", t("Комплект")),
      sortButton("ducats", "ducats", t("Дукаты"), t("Сколько дукатов дают все части комплекта в киоске")),
      sortButton("ducats", "price", t("Цена комплекта"), t("Минимальная цена продажи комплекта у игроков, которые сейчас в игре")),
      sortButton("ducats", "rate", t("Дукатов за 1 платину"), t("Дукаты комплекта, делённые на его цену: чем больше, тем выгоднее покупка")),
      h("span")),
    list.length ? list.map((s) => ducatRow(s, best)) : h("div", { class: "empty small" }, h("p", null, t("Ничего не найдено."))));
  return h("div", null,
    h("p", { class: "lead" }, t("Какой комплект купить на warframe.market, чтобы получить больше всего дукатов за каждую платину. Комплект покупается целиком, а его части сдаются в киоск дукатов в реле.")),
    ducatTools(), calcCard(), card);
}
async function loadDucatPrice(slug, force) {
  const before = D.price.get(slug);
  D.price.set(slug, { ...(before || {}), state: before && before.state === "done" ? "done" : "loading", busy: true });
  refreshDucatRow(slug);
  try {
    const data = await api(`/api/market?slug=${slug}&lite=1${force ? "&force=1" : ""}`);
    if (data.price) D.price.set(slug, { state: "done", price: data.price, at: data.orders_at });
    else D.price.set(slug, { state: "error", error: (data.errors && data.errors[0]) || t("маркет не ответил") });
  } catch (err) {
    D.price.set(slug, before && before.state === "done" ? { state: "done", price: before.price, at: before.at } : { state: "error", error: err.message });
  }
  refreshDucatRow(slug);
}
function stopDucatQueue() { D.queue.gen++; D.queue.running = false; if (S.tab === "ducats") renderView(); }
async function runDucatQueue(force) {
  if (!D.list) return;
  const q = D.queue;
  const now = Date.now() / 1000;
  const todo = D.list.filter((s) => {
    const p = D.price.get(s.slug);
    return force || !p || p.state !== "done" || !p.at || now - p.at > D.ttl;
  }).map((s) => s.slug);
  if (!todo.length) { toast(t("Цены свежие: им меньше {0} минут.", Math.round(D.ttl / 60))); return; }
  const gen = ++q.gen;
  Object.assign(q, { running: true, done: 0, total: todo.length });
  for (const slug of todo) if (!D.price.has(slug)) D.price.set(slug, { state: "loading" });
  if (S.tab === "ducats") renderView();
  const worker = async () => {
    while (todo.length && gen === q.gen) {
      const slug = todo.shift();
      await loadDucatPrice(slug, force);
      if (gen !== q.gen) return;
      q.done++;
      // rows move as the ranking fills in: re-sort now and then, not on every answer
      if (S.tab === "ducats") { if (q.done % 8 === 0) renderView(); else updateDucatTools(); }
    }
  };
  await Promise.all([worker(), worker()]);
  if (gen !== q.gen) return;
  q.running = false;
  for (const [slug, p] of D.price) if (p.state === "loading") D.price.delete(slug);
  if (S.tab === "ducats") renderView();
  if (D.calc.plan) planDucats();              // the offers have changed: the shopping list is built from them
}

// ----------------------------------------------------------------- ducats: the purchase calculator
// "I need 1000 ducats": the server picks the cheapest sets among the remembered offers of sellers who
// are in the game; here the list is shown seller by seller, with the message to paste into the game chat.
function calcTotals() {
  const c = D.calc;
  const done = c.done.reduce((a, x) => ({ gain: a.gain + x.gain, cost: a.cost + x.cost, n: a.n + x.count }), { gain: 0, cost: 0, n: 0 });
  const plan = c.plan ? { gain: c.plan.ducats, cost: c.plan.platinum, n: c.plan.steps.reduce((a, s) => a + s.count, 0) } : { gain: 0, cost: 0, n: 0 };
  return { done, plan, gain: done.gain + plan.gain, cost: done.cost + plan.cost, n: done.n + plan.n };
}
function renderCalc() {
  const old = $("#calc");
  if (old && S.tab === "ducats") old.replaceWith(calcCard());
}
async function planDucats() {
  const c = D.calc;
  if (!(c.target >= 5)) { toast(t("Укажите, сколько дукатов нужно.")); return; }
  const need = c.target - c.done.reduce((a, x) => a + x.gain, 0);
  if (need <= 0) {
    c.plan = { steps: [], ducats: 0, platinum: 0, reached: true, oldest_at: null };
    c.state = "idle"; renderCalc();
    return;
  }
  c.state = "loading"; renderCalc();
  try {
    c.plan = await post("/api/ducats/plan", { target: need, exclude: [...c.exclude, ...c.done.map((x) => x.key)] });
    c.state = "idle"; c.error = "";
  } catch (err) {
    c.state = "error"; c.error = err.message;
  }
  renderCalc();
}
async function copyText(text, okText) {
  try { await navigator.clipboard.writeText(text); toast(okText); return true; } catch (e) { /* try the old way */ }
  try {
    const area = h("textarea", { readonly: true, style: "position:fixed;left:-1000px;top:0;opacity:0" });
    area.value = text;
    (document.querySelector("dialog[open]") || document.body).append(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    if (ok) { toast(okText); return true; }
  } catch (e) { /* nothing else to try */ }
  toast(t("Не удалось скопировать — выделите текст вручную"));
  return false;
}
function calcStep(step) {
  const c = D.calc;
  const copied = c.copied.has(step.key);
  const meta = [t("продавец {0}", step.user),
    typeof step.reputation === "number" && step.reputation > 0 ? t("репутация {0}", step.reputation) : null,
    step.quantity > step.count ? t("у него {0} шт.", step.quantity) : null].filter(Boolean).join(" · ");
  return h("div", { class: "calc-step" },
    thumb(step.thumb, true),
    h("div", { class: "calc-what" },
      h("div", { class: "part-name" }, step.title + (step.count > 1 ? ` ×${step.count}` : "")),
      h("div", { class: "part-meta" }, meta)),
    h("div", { class: "calc-num num" },
      h("b", null, t("{0} пл", fmt(step.cost))),
      h("div", { class: "sub" }, [t("{0} дук.", fmt(step.gain)), step.count > 1 ? t("по {0} пл", fmt(step.platinum)) : null].filter(Boolean).join(" · "))),
    h("div", { class: "calc-actions" },
      h("button", { class: "btn subtle", title: step.message,
        onclick: async () => { await copyText(step.message, t("Сообщение скопировано — вставьте его в чат игры")); c.copied.add(step.key); renderCalc(); } },
        icon(copied ? "check" : "copy"), t("Сообщение")),
      h("button", { class: "btn subtle", title: t("Покупка состоялась: учесть её и пересчитать остаток"),
        onclick: () => { c.done.push(step); planDucats(); } }, t("Купил")),
      h("button", { class: "btn subtle", title: t("Продавец не отвечает или передумал: подобрать замену"),
        onclick: () => { c.exclude.add(step.key); planDucats(); } }, t("Не отвечает"))),
    // after the first press the text stays in sight: it shows what went to the clipboard and can be selected by hand
    copied ? h("input", { class: "msg-line", readonly: true, value: step.message, "aria-label": t("Сообщение продавцу"),
      onfocus: (e) => e.target.select() }) : null);
}
function calcCard() {
  const c = D.calc;
  const known = D.list ? D.list.filter((s) => ducatPrice(s) != null).length : 0;
  const input = h("input", { class: "num-input num", type: "number", min: "5", max: "50000", step: "5", value: String(c.target), "aria-label": t("Сколько дукатов нужно"),
    oninput: (e) => {
      c.target = Math.max(0, Math.round(Number(e.target.value) || 0));
      try { localStorage.setItem("primesets-ducat-target", String(c.target)); } catch (err) { /* ignore */ }
    },
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); planDucats(); } } });
  const box = h("div", { class: "card calc", id: "calc" },
    h("div", { class: "calc-head" },
      h("div", { class: "calc-title" }, h("h3", null, t("Калькулятор закупки")),
        h("div", { class: "sub" }, t("Самый дешёвый набор комплектов на нужное число дукатов — у продавцов, которые сейчас в игре."))),
      h("div", { class: "calc-form" },
        h("label", { class: "calc-field" }, h("span", { class: "sub" }, t("Нужно дукатов")), input),
        h("button", { class: "btn primary", disabled: !known || c.state === "loading", onclick: () => planDucats() },
          c.state === "loading" ? t("Считаю…") : c.plan || c.done.length ? t("Пересчитать") : t("Подобрать")))));
  if (!known) {
    box.append(h("div", { class: "sub calc-note" }, t("Сначала узнайте цены комплектов кнопкой выше: без них подбирать не из чего.")));
    return box;
  }
  if (c.state === "error") box.append(h("div", { class: "callout" }, icon("alert"), h("div", null, c.error)));
  if (!c.plan && !c.done.length) return box;
  const tot = calcTotals();
  const plan = c.plan || { steps: [], reached: true };
  box.append(h("div", { class: "calc-sum" },
    h("div", { class: "price num" }, fmt(tot.cost), h("span", { class: "unit" }, t("пл"))),
    h("div", { class: "sub num" }, [tn("# дукат|# дуката|# дукатов", tot.gain),
      tot.cost ? t("{0} дук. за 1 пл", rateFmt.format(tot.gain / tot.cost)) : null, t("покупок: {0}", tot.n),
      tot.done.n ? t("из них сделано: {0}", tot.done.n) : null].filter(Boolean).join(" · "))));
  if (c.plan && !plan.reached) {
    box.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
      t("У продавцов в игре сейчас не набирается {0} дукатов: хватает на {1}. Обновите цены позже или начните подбор заново.", fmt(c.target), fmt(tot.gain)))));
  }
  if (plan.oldest_at && Date.now() / 1000 - plan.oldest_at > D.ttl) {
    box.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
      h("div", null, t("Цены в этом подборе запрошены {0}: продавцы могли выйти из игры, а цены — измениться.", stampFmt.format(new Date(plan.oldest_at * 1000)))),
      h("div", { class: "actions" }, h("button", { class: "btn subtle", disabled: D.queue.running, onclick: () => runDucatQueue(false) },
        icon("refresh"), t("Обновить цены и пересчитать"))))));
  }
  if (c.done.length) {
    box.append(h("div", { class: "calc-list done" }, c.done.map((x) => h("div", { class: "calc-step" },
      thumb(x.thumb, true),
      h("div", { class: "calc-what" },
        h("div", { class: "part-name" }, x.title + (x.count > 1 ? ` ×${x.count}` : "")),
        h("div", { class: "part-meta" }, icon("check"), t("куплено у {0}", x.user))),
      h("div", { class: "calc-num num" }, h("b", null, t("{0} пл", fmt(x.cost))), h("div", { class: "sub" }, t("{0} дук.", fmt(x.gain)))),
      h("div", { class: "calc-actions" },
        h("button", { class: "btn subtle", onclick: () => { c.done = c.done.filter((y) => y !== x); planDucats(); } }, t("Отменить")))))));
  }
  if (plan.steps.length) box.append(h("div", { class: "calc-list" }, plan.steps.map(calcStep)));
  else if (c.done.length && plan.reached) box.append(h("div", { class: "sub ok-line" }, icon("check"), t("Нужное число дукатов набрано.")));
  box.append(h("div", { class: "calc-foot sub" },
    h("span", null, t("Сообщение продавцу вставьте в чат игры сами (Ctrl+V): приложение в игру ничего не отправляет. Каждая покупка — отдельная сделка, а их число в день ограничено рангом мастерства.")),
    c.done.length || c.exclude.size || c.copied.size
      ? h("button", { class: "link-btn", onclick: () => { c.done = []; c.exclude.clear(); c.copied.clear(); planDucats(); } }, t("Начать подбор заново")) : null));
  return box;
}




// ----------------------------------------------------------------- ducats: what to hand in to Baro
/* The other direction: the parts the user already has beyond full sets.  A part that costs next to
   nothing in platinum is better handed in at the ducat kiosk; a part with a real price is better
   sold.  The border between the two is the user's: how many ducats one platinum should bring. */
const BARO = { data: null, state: "idle", error: "", rate: remembered("primesets-baro-rate", 10), hold: true,
  queue: { running: false, done: 0, total: 0, gen: 0 } };
async function loadBaro() {
  try { BARO.data = await api("/api/baro"); BARO.state = "done"; BARO.error = ""; }
  catch (err) { BARO.state = "error"; BARO.error = err.message; }
  renderBaro();
}
function stopBaroQueue() { BARO.queue.gen++; BARO.queue.running = false; loadBaro(); }
async function runBaroQueue(force) {
  const q = BARO.queue, d = BARO.data;
  if (!d || q.running) return;
  const fresh = (p) => p.asked && Date.now() / 1000 - p.orders_at <= d.ttl_orders;
  const sets = [...new Set(d.parts.filter((p) => force || !fresh(p)).map((p) => p.set))];
  if (!sets.length) { toast(t("Цены уже загружены.")); return; }
  const gen = ++q.gen;
  Object.assign(q, { running: true, done: 0, total: sets.length });
  renderBaro();
  for (const slug of sets) {
    if (gen !== q.gen) return;
    try { await api(`/api/parts-market?slug=${slug}&scope=spare${force ? "&force=1" : ""}`); } catch (e) { /* that set stays without a price */ }
    q.done++;
    if (gen !== q.gen) return;
    try { BARO.data = await api("/api/baro"); } catch (e) { /* the list is shown anew at the end */ }
    if (gen === q.gen) renderBaro();          // the parts fall into their groups as their prices come in
  }
  if (gen !== q.gen) return;
  q.running = false;
  loadBaro();
}
// where a spare part belongs: "hold" | "ducats" | "sell" | "unknown" (no price asked yet)
function baroGroup(p) {
  if (BARO.hold && p.near) return "hold";
  if (!p.asked || (p.price == null && !p.ducats)) return "unknown";
  if (p.price == null || !p.ducats) return p.ducats ? "ducats" : "sell";
  return p.ducats / p.price >= BARO.rate ? "ducats" : "sell";
}
function baroRow(p, group) {
  const worth = p.price != null ? t("на маркете {0} пл", fmt(p.price)) + (p.basis === "online" ? " · " + t("продавец не в игре") : "") : p.asked ? t("на маркете не продают") : "";
  return h("div", { class: "calc-step" },
    thumb(p.thumb, true),
    h("div", { class: "calc-what" },
      h("div", { class: "part-name", title: p.name }, p.set_title + ": " + p.label + (p.count > 1 ? ` ×${p.count}` : "")),
      h("div", { class: "part-meta" }, group === "sell" ? t("в киоске {0} дук.", fmt(p.ducats))
        : [t("{0} дук. за штуку", fmt(p.ducats)), worth].filter(Boolean).join(" · "))),
    h("div", { class: "calc-num num" }, group === "sell"
      ? [h("b", null, pl(p.price * p.count)), p.count > 1 ? h("div", { class: "sub" }, t("по {0} пл", fmt(p.price))) : null]
      : h("b", null, t("{0} дук.", fmt(p.ducats * p.count)))),
    h("span"));
}
function renderBaro() {
  const dlg = $("#dlg-baro");
  if (!dlg.open) return;
  const body = h("div", { class: "dlg-body" });
  const d = BARO.data, q = BARO.queue;
  if (BARO.state === "error") body.append(h("div", { class: "callout" }, icon("alert"), h("div", null, BARO.error)));
  else if (!d) body.append(h("span", { class: "skeleton", style: "width:100%;height:160px" }));
  else if (!d.parts.length) {
    body.append(h("div", { class: "empty small" }, h("p", null, t("Лишних частей нет: всё, что у вас есть, складывается в полные комплекты."))));
  } else {
    const groups = { ducats: [], sell: [], hold: [], unknown: [] };
    for (const p of d.parts) groups[baroGroup(p)].push(p);
    groups.ducats.sort((a, b) => b.ducats * b.count - a.ducats * a.count);
    groups.sell.sort((a, b) => b.price * b.count - a.price * a.count);
    const kinds = new Set(d.parts.map((p) => p.slug)).size;
    const asked = d.parts.filter((p) => p.asked).length;
    const oldest = d.parts.reduce((a, p) => (p.orders_at ? Math.min(a, p.orders_at) : a), Infinity);
    const rate = h("input", { class: "num-input num", type: "number", min: "1", max: "100", step: "1", value: String(BARO.rate), "aria-label": t("Сколько дукатов должна приносить одна платина"),
      onchange: (e) => { BARO.rate = Math.min(100, Math.max(1, Math.round(Number(e.target.value) || 10))); remember("primesets-baro-rate", BARO.rate); renderBaro(); } });
    body.append(
      h("div", { class: "calc-head" },
        h("div", { class: "calc-title" }, h("div", { class: "sub" },
          t("Части сверх полных комплектов. Если за одну платину цены часть даёт в киоске не меньше указанного числа дукатов, её выгоднее сдать Баро, иначе — продать."))),
        h("div", { class: "calc-form" },
          h("label", { class: "calc-field" }, h("span", { class: "sub" }, t("Дукатов за 1 пл, не меньше")), rate))),
      h("div", { class: "dlg-tools" },
        h("button", { class: "btn " + (asked === d.parts.length || q.running ? "ghost" : "primary"), id: "baro-ask", onclick: () => (q.running ? stopBaroQueue() : runBaroQueue(asked === d.parts.length)) },
          icon(q.running ? "close" : "refresh"), h("span", null, q.running ? t("Остановить ({0} из {1})", q.done, q.total) : asked === d.parts.length ? t("Обновить цены") : t("Узнать цены частей"))),
        h("span", { class: "sub" }, q.running ? t("Запрашиваю цены: по одному запросу, не чаще двух в секунду.")
          : !asked ? t("Цены частей ещё не запрашивались. Запросов к warframe.market: {0} — около {1} мин.", kinds, Math.max(1, Math.round(kinds * d.min_interval / 60)))
            : Number.isFinite(oldest) ? t("Цены известны для {0} из {1} · самые старые от {2}.", asked, d.parts.length, stampFmt.format(new Date(oldest * 1000)))
              : t("Цены известны для {0} из {1}.", asked, d.parts.length))),
      h("label", { class: "check-line" },
        h("input", { type: "checkbox", checked: BARO.hold, onchange: (e) => { BARO.hold = e.target.checked; renderBaro(); } }),
        h("span", null, t("Придержать части комплектов, которым до полного не хватает одной части"))));
    const section = (title, sum, list, group, empty) => h("section", { class: "baro-sec" },
      h("div", { class: "baro-head" }, h("h3", null, title), h("span", { class: "num" }, sum)),
      list.length ? h("div", { class: "calc-list" }, list.map((p) => baroRow(p, group))) : h("div", { class: "sub" }, empty));
    const count = (list) => list.reduce((a, p) => a + p.count, 0);
    body.append(
      section(t("Сдать на дукаты"), groups.ducats.length ? tn("# часть|# части|# частей", count(groups.ducats)) + " · " + tn("# дукат|# дуката|# дукатов", groups.ducats.reduce((a, p) => a + p.ducats * p.count, 0)) : "",
        groups.ducats, "ducats", asked ? t("Под этот порог ничего не попало.") : t("Появится, когда будут известны цены.")),
      section(t("Продать за платину"), groups.sell.length ? tn("# часть|# части|# частей", count(groups.sell)) + " · ≈ " + pl(groups.sell.reduce((a, p) => a + p.price * p.count, 0)) : "",
        groups.sell, "sell", asked ? t("Под этот порог ничего не попало.") : t("Появится, когда будут известны цены.")));
    if (groups.hold.length) {
      body.append(section(t("Придержать"), tn("# часть|# части|# частей", count(groups.hold)), groups.hold, "hold", ""));
    }
    if (groups.unknown.length) {
      body.append(h("div", { class: "sub" }, tn("Без цены пока # часть: нажмите «Узнать цены частей».|Без цены пока # части: нажмите «Узнать цены частей».|Без цены пока # частей: нажмите «Узнать цены частей».", count(groups.unknown))));
    }
    body.append(h("p", { class: "foot" }, t("Цена части — минимальная у продавцов в игре. Дукаты за часть берутся из данных warframe.market. Части полных комплектов сюда не входят: комплект выгоднее продать целиком.")));
  }
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(h("div", { class: "dlg-head" }, h("h2", null, t("Что сдать Баро")), closeButton(dlg)), body);
  body.scrollTop = scroll;
}
function openBaroDialog() {
  const dlg = $("#dlg-baro");
  if (!dlg.open) dlg.showModal();
  renderBaro();
  loadBaro();
}

// ----------------------------------------------------------------- history: what changed and what it is worth
const HIST = { data: null, state: "idle", error: "", open: new Set(), view: "now" };
const SOURCE_RU = { screenshots: t("по скриншотам"), "screenshots+manual": t("по скриншотам, с правками вручную"), manual: t("правки вручную"),
  sale: t("продажа"), purchase: t("покупка") };
async function loadHistory() {
  try { HIST.data = await api("/api/history"); HIST.state = "done"; }
  catch (err) { HIST.state = "error"; HIST.error = err.message; }
  return HIST.data;
}
function changeSummary(u) {
  const bits = [];
  if (u.added.length) bits.push("+" + tn("# часть|# части|# частей", u.added.length));
  if (u.removed.length) bits.push(MINUS + tn("# часть|# части|# частей", u.removed.length));
  if (u.changed.length) bits.push(t("у {0} изменилось количество", u.changed.length));
  return bits;
}
function historySeen(value) {
  try {
    if (value) localStorage.setItem("primesets-history-seen", value);
    return localStorage.getItem("primesets-history-seen") || "";
  } catch (e) { return value || ""; }
}
function renderChangesBanner() {
  const banner = $("#changes-banner");
  const last = HIST.data && HIST.data.updates[0];
  if (!last || last.first || last.at <= historySeen() || $("#dlg-history").open) { banner.hidden = true; return; }
  const sets = [];
  if (last.sets_up.length) sets.push(t("Стали полными: {0}.", last.sets_up.map((x) => x.title).join(", ")));
  if (last.sets_down.length) sets.push(t("Перестали быть полными: {0}.", last.sets_down.map((x) => x.title).join(", ")));
  banner.replaceChildren(icon("clock"),
    h("div", { class: "notice-body" },
      h("div", { class: "notice-title" }, t("Обновление от {0}: {1}", stampFmt.format(new Date(last.at)), changeSummary(last).join(", ") || t("состав не изменился"))),
      sets.length ? h("div", { class: "notice-text" }, sets.join(" ")) : null),
    h("button", { class: "btn subtle", onclick: openHistoryDialog }, t("Что изменилось")),
    h("button", { class: "btn subtle", onclick: () => { historySeen(last.at); banner.hidden = true; } }, t("Понятно")));
  banner.hidden = false;
}
async function checkChanges() {
  await loadHistory();
  renderChangesBanner();
  if ($("#dlg-history").open) renderHistory();
}

/* The complete sets the user holds now, valued day by day at the prices of closed deals: what the
   present stock would have fetched on each of the last 90 days.  A set without a deal on some day
   keeps its last known price (its first one before that). */
function holdingsSeries() {
  const sets = S.data ? S.data.complete : [];
  const per = [], missing = [];
  let ready = true;
  for (const set of sets) {
    const m = S.market.get(set.slug);
    if (!m || m.state === "loading") { ready = false; continue; }
    const series = m.state === "done" && m.data.trend ? m.data.trend.series : null;
    if (!series || !series.length) { missing.push(set.title); continue; }
    per.push({ copies: set.complete, series });
  }
  const days = [...new Set(per.flatMap((p) => p.series.map((r) => r[0])))].sort();
  const at = per.map(() => 0);
  const out = days.map((day) => {
    let sum = 0, deals = 0;
    per.forEach((p, k) => {
      while (at[k] + 1 < p.series.length && p.series[at[k] + 1][0] <= day) at[k]++;
      const row = p.series[at[k]];
      sum += row[1] * p.copies;
      if (row[0] === day) deals += row[2];
    });
    return [day, Math.round(sum), Math.max(1, deals)];
  });
  return { series: out, missing, ready, sets: per.length, copies: per.reduce((a, p) => a + p.copies, 0) };
}
function valuePanel() {
  const panel = h("div", { class: "panel hist-value" });
  const vals = (HIST.data && HIST.data.values) || [];
  panel.append(h("div", { class: "panel-title" }, h("span", null, t("Стоимость готовых комплектов, платина")),
    h("div", { class: "seg" },
      h("button", { "aria-pressed": String(HIST.view === "now"), onclick: () => { HIST.view = "now"; renderHistory(); } }, t("Нынешние за 90 дней")),
      h("button", { "aria-pressed": String(HIST.view === "days"), onclick: () => { HIST.view = "days"; renderHistory(); } }, t("По дням")))));
  const wrap = h("div", { class: "chart-wrap" });
  const draw = (trend, opts) => {
    // drawn at the real width of the dialog, redrawn when the window changes
    let drawn = 0;
    const go = () => {
      const w = Math.floor(wrap.clientWidth);
      if (!w || w === drawn) return;
      drawn = w;
      wrap.replaceChildren(priceChart(trend, w, opts));
    };
    new ResizeObserver(go).observe(wrap);
  };
  if (HIST.view === "now") {
    const now = holdingsSeries();
    if (!S.data || !S.data.complete.length) {
      panel.append(h("div", { class: "chart-note" }, t("Готовых комплектов пока нет.")));
    } else if (!now.ready || S.queue.running) {
      panel.append(h("span", { class: "skeleton", style: "width:100%;height:150px" }),
        h("div", { class: "chart-note" }, t("Цены ещё загружаются — график появится через несколько секунд.")));
      setTimeout(() => { if ($("#dlg-history").open && HIST.view === "now") renderHistory(); }, 2500);
    } else if (now.series.length < 2) {
      panel.append(h("div", { class: "chart-note" }, t("По вашим комплектам слишком мало сделок, чтобы построить график.")));
    } else {
      draw({ series: now.series, period_days: 90 }, {
        dayLabel: t("по сделкам этого дня"),
        volText: (p) => tn("# сделка по этим комплектам|# сделки по этим комплектам|# сделок по этим комплектам", p.vol),
        aria: t("Стоимость нынешних готовых комплектов за 90 дней: от {0} до {1} платины", fmt(now.series[0][1]), fmt(now.series[now.series.length - 1][1])),
      });
      panel.append(
        h("div", { class: "chart-legend" },
          h("span", null, h("span", { class: "key", style: "background:var(--series)" }), t("среднее за 7 дней")),
          h("span", null, h("span", { class: "key thin", style: "background:var(--series-quiet)" }), t("по сделкам каждого дня"))),
        wrap,
        h("div", { class: "chart-note" },
          t("Сколько стоили бы ваши нынешние комплекты ({0}, экземпляров {1}) в каждый из дней — по ценам закрытых сделок. Это не минимальные цены продавцов, поэтому число отличается от плитки «Стоимость».", now.sets, now.copies) +
          (now.missing.length ? t(" Не учтены: {0} — по ним не было сделок.", now.missing.join(", ")) : "")));
    }
  } else if (vals.length < 2) {
    panel.append(h("div", { class: "chart-note" }, vals.length
      ? t("Пока одна запись: {0} пл, {1}. График появится, когда приложение поработает в разные дни: значение плитки «Стоимость» записывается при каждом запуске, одно на день.", fmt(vals[0].value), dayFmt.format(parseDay(vals[0].date)))
      : t("Записей пока нет: значение плитки «Стоимость» записывается, когда загружены все цены, одно на день.")));
  } else {
    draw({ series: vals.map((v) => [v.date, v.value, 1]), period_days: vals.length }, {
      smooth: 0, avgLabel: t("по минимальным ценам продавцов"),
      volText: (p, i) => t("комплектов: {0}, экземпляров: {1}", vals[i].sets, vals[i].copies),
      aria: t("Стоимость готовых комплектов по дням: от {0} до {1} платины", fmt(vals[0].value), fmt(vals[vals.length - 1].value)),
    });
    panel.append(wrap,
      h("div", { class: "chart-note" }, t("То, что показывала плитка «Стоимость» в дни, когда вы открывали приложение: меняется и от цен, и от состава инвентаря.")),
      h("div", { class: "table-view" }, h("table", null,
        h("thead", null, h("tr", null, h("th", null, t("День")), h("th", null, t("Стоимость, пл")), h("th", null, t("Комплектов")), h("th", null, t("Экземпляров")))),
        h("tbody", null, [...vals].reverse().map((v) => h("tr", null,
          h("td", null, dayFmt.format(parseDay(v.date))), h("td", null, fmt(v.value)), h("td", null, String(v.sets)), h("td", null, String(v.copies))))))));
  }
  return panel;
}
function updateCard(u) {
  const open = HIST.open.has(u.at);
  const any = u.added.length || u.removed.length || u.changed.length;
  const what = u.first
    ? tn("в списке # разная часть, {0} шт.; полных комплектов: {1}|в списке # разные части, {0} шт.; полных комплектов: {1}|в списке # разных частей, {0} шт.; полных комплектов: {1}", u.distinct, u.total, u.complete)
    : (changeSummary(u).join(", ") || t("состав не изменился"));
  const lines = [];
  const setNames = (list) => list.map((x) => x.title + (x.old > 0 || x.new > 1 ? ` (${x.old} → ${x.new})` : "")).join(", ");
  if (u.sets_up.length) lines.push(h("div", { class: "hist-line" }, h("span", { class: "chip good" }, icon("up"), t("стали полными")), h("span", null, setNames(u.sets_up))));
  if (u.sets_down.length) lines.push(h("div", { class: "hist-line" }, h("span", { class: "chip warn" }, icon("fall"), t("перестали быть полными")), h("span", null, setNames(u.sets_down))));
  if (!u.first) lines.push(h("div", { class: "sub num" },
    tn("Было # часть ({0} шт.), стало {1} ({2} шт.) · полных комплектов {3} → {4}|Было # части ({0} шт.), стало {1} ({2} шт.) · полных комплектов {3} → {4}|Было # частей ({0} шт.), стало {1} ({2} шт.) · полных комплектов {3} → {4}",
      u.distinct_before, u.total_before, u.distinct, u.total, u.complete_before, u.complete)));
  const list = (title, rows, text) => (rows.length ? h("div", null, h("b", null, `${title}: ${rows.length}`), h("ul", null, rows.map((r) => h("li", null, text(r))))) : null);
  return h("div", { class: "hist-card" },
    h("button", { class: "hist-head", "aria-expanded": String(open), disabled: u.first || !any,
      onclick: () => { if (open) HIST.open.delete(u.at); else HIST.open.add(u.at); renderHistory(); } },
      h("div", { class: "hist-when" }, h("b", null, stampFmt.format(new Date(u.at))),
        h("span", { class: "sub" }, [u.first ? t("первая запись") : "", SOURCE_RU[u.source] || "", u.note].filter(Boolean).join(" · "))),
      h("div", { class: "hist-what" }, what),
      u.first || !any ? h("span") : h("span", { class: "chev" }, icon("chevron"))),
    lines.length ? h("div", { class: "hist-sets" }, lines) : null,
    open && any && !u.first ? h("div", { class: "hist-detail" },
      list(t("Появились"), u.added, (r) => `${r.item} ×${r.count}`),
      list(t("Исчезли"), u.removed, (r) => `${r.item} ×${r.count}`),
      list(t("Изменилось количество"), u.changed, (r) => `${r.item}: ${r.old} → ${r.new}`)) : null);
}
// what the user sold ("Продал"): the journal, the newest first; a line entered by mistake is taken back here
function salesPanel() {
  const box = HIST.data && HIST.data.sales;
  if (!box || !box.sales.length) return null;
  const undo = async (sale) => {
    try {
      await afterSale(await post("/api/sales/undo", { id: sale.id }));
      toast(t("Продажа отменена: части вернулись в инвентарь"));
    } catch (err) { toast(err.message); }
  };
  return h("div", { class: "panel sales-panel" },
    h("div", { class: "panel-title" }, h("span", null, t("Журнал продаж")),
      h("span", { class: "num" }, t("за 30 дней: {0} пл · всего: {1} пл", fmt(box.totals.month), fmt(box.totals.platinum)))),
    h("div", { class: "sales-list" }, box.sales.map((s) => h("div", { class: "sale-row" },
      thumb(s.thumb, true),
      h("div", { class: "calc-what" }, h("div", { class: "part-name" }, s.title + (s.count > 1 ? ` ×${s.count}` : "")),
        h("div", { class: "part-meta" }, [stampFmt.format(new Date(s.at)), s.buyer ? t("покупатель {0}", s.buyer) : null].filter(Boolean).join(" · "))),
      h("div", { class: "calc-num num" }, h("b", null, pl(s.sum)), s.count > 1 ? h("div", { class: "sub" }, t("по {0} пл", fmt(s.platinum))) : null),
      h("button", { class: "btn subtle", title: t("Запись сделана по ошибке: вернуть части в инвентарь и убрать её из журнала"), onclick: () => undo(s) }, t("Отменить"))))));
}
function renderHistory() {
  const dlg = $("#dlg-history");
  if (!dlg.open) return;
  const body = h("div", { class: "dlg-body" });
  if (HIST.state === "error" || !HIST.data) {
    body.append(h("div", { class: "callout" }, icon("alert"), h("div", null, HIST.error || t("История не загрузилась."))));
  } else {
    const ups = HIST.data.updates;
    const sold = salesPanel();
    body.append(valuePanel());
    if (sold) body.append(sold);
    body.append(h("h3", { class: "hist-title" }, t("Что менялось в инвентаре")),
      ups.length ? h("div", { class: "hist-list" }, ups.map(updateCard))
        : h("div", { class: "sub" }, t("Пока нет ни одного обновления: история начнётся с первого занесённого инвентаря.")));
  }
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, t("История")),
      h("button", { class: "btn ghost icon-only", "aria-label": t("Закрыть"), onclick: () => dlg.close() }, icon("close"))),
    body);
  body.scrollTop = scroll;
}
async function openHistoryDialog() {
  const dlg = $("#dlg-history");
  if (!dlg.open) {
    dlg.replaceChildren(h("div", { class: "dlg-head" }, h("h2", null, t("История"))),
      h("div", { class: "dlg-body" }, h("span", { class: "skeleton", style: "width:100%;height:160px" })));
    dlg.showModal();
  }
  await loadHistory();
  const last = HIST.data && HIST.data.updates[0];
  if (last) { HIST.open.add(last.at); historySeen(last.at); }
  $("#changes-banner").hidden = true;
  renderHistory();
}
// what the complete sets add up to, once every price is in: one record a day for the "По дням" chart
function reportValue() {
  const d = S.data;
  if (!d || !d.complete.length) return;
  let sum = 0, priced = 0;
  for (const set of d.complete) {
    const m = S.market.get(set.slug);
    if (!m || m.state !== "done" || !m.data.price) return;        // an incomplete picture is not recorded
    if (m.data.price.value != null) { sum += m.data.price.value * set.complete; priced++; }
  }
  if (!priced) return;
  post("/api/history/value", { value: sum, sets: d.complete.length, copies: d.complete.reduce((a, x) => a + x.complete, 0), priced })
    .then((res) => { if (HIST.data) HIST.data.values = res.values; }).catch(() => { /* a convenience only */ });
}

// ----------------------------------------------------------------- selling: whole or by parts, and a listing for the chat
function partsVerdict(set) {
  const pm = S.parts.get("all:" + set.slug), price = setPriceOf(set.slug);
  if (!pm || pm.state !== "done" || pm.data.total == null || price == null) return null;
  const diff = pm.data.total - price;
  return { total: pm.data.total, diff, better: diff >= Math.max(3, price * 0.1) };       // a platinum or two is not worth the extra trades
}
function stopPartsQueue() { S.partsQueue.gen++; S.partsQueue.running = false; renderView(); }
async function runPartsQueue() {
  const q = S.partsQueue;
  const todo = S.data.complete.filter((x) => { const pm = S.parts.get("all:" + x.slug); return !pm || pm.state === "error"; });
  const count = () => S.data.complete.filter((x) => { const v = partsVerdict(x); return v && v.better; }).length;
  const say = () => { const n = count(); toast(n ? tn("По частям выгоднее: # комплект — смотрите пометки у цены|По частям выгоднее: # комплекта — смотрите пометки у цены|По частям выгоднее: # комплектов — смотрите пометки у цены", n) : t("Комплектом не хуже, чем по частям, во всех случаях")); };
  if (!todo.length) { say(); return; }
  const gen = ++q.gen;
  Object.assign(q, { running: true, done: 0, total: todo.length });
  renderView();
  for (const set of todo) {
    if (gen !== q.gen) return;
    await loadParts(set, "all", false);
    q.done++;
    const label = document.querySelector("#sell-tools .btn span:not(.ico)");
    if (label && gen === q.gen) label.textContent = t("Остановить ({0} из {1})", q.done, q.total);
  }
  if (gen !== q.gen) return;
  q.running = false;
  if (S.tab === "complete") renderView();
  say();
}
// The trade chat is read by people, in the language of their game: the text is offered in the
// language of the interface and in English (warframe.market gives the item names in both).
const LIST = { lang: LANG === "en" ? "en" : "own", cut: 0, off: new Set(), touched: false };
function listingText(sets) {
  const en = LIST.lang === "en";
  const items = sets.map((s) => {
    const price = Math.max(1, setPriceOf(s.slug) - LIST.cut), n = s.complete;
    if (en) return `${s.title_en}${n > 1 ? ` x${n}` : ""} ${price}p${n > 1 ? " each" : ""}`;
    return n > 1 ? t("{0} ×{1} {2}п за шт.", s.title, n, price) : t("{0} {1}п", s.title, price);
  });
  if (!items.length) return "";
  return en ? "WTS prime sets: " + items.join(", ") : t("Продам прайм-комплекты: {0}", items.join(", "));
}
function renderListing() {
  const dlg = $("#dlg-listing");
  if (!dlg.open || !S.data) return;
  const all = S.data.complete.filter((s) => setPriceOf(s.slug) != null).sort((a, b) => setPriceOf(b.slug) - setPriceOf(a.slug));
  const noPrice = S.data.complete.filter((s) => setPriceOf(s.slug) == null);
  const picked = all.filter((s) => !LIST.off.has(s.slug));
  const sum = picked.reduce((a, s) => a + Math.max(1, setPriceOf(s.slug) - LIST.cut) * s.complete, 0);
  const area = h("textarea", { class: "listing-text", rows: "5", spellcheck: "false", "aria-label": t("Текст объявления") });
  area.value = listingText(picked);
  const count = h("span", { class: "sub num" });
  const recount = () => { count.textContent = [tn("# знак|# знака|# знаков", area.value.length), t("комплектов: {0}", picked.length), t("на {0} пл", fmt(sum))].join(" · "); };
  area.addEventListener("input", recount);
  recount();
  const seg = (key, options) => h("div", { class: "seg" }, options.map(([value, label]) =>
    h("button", { "aria-pressed": String(LIST[key] === value), onclick: () => { LIST[key] = value; renderListing(); } }, label)));
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, t("Объявление для торгового чата")),
      h("button", { class: "btn ghost icon-only", "aria-label": t("Закрыть"), onclick: () => dlg.close() }, icon("close"))),
    h("div", { class: "dlg-body" },
      h("div", { class: "listing-opts" },
        LANG === "en" ? null : seg("lang", [["own", I18N.name], ["en", "English"]]),
        seg("cut", [[0, t("Цена как у самого дешёвого")], [1, t("На 1 пл дешевле")]])),
      area,
      h("div", { class: "actions" },
        h("button", { class: "btn primary", disabled: !picked.length,
          onclick: () => copyText(area.value, t("Объявление скопировано — вставьте его в чат игры")) }, icon("copy"), t("Скопировать")),
        count),
      all.length ? h("div", { class: "listing-list" }, all.map((s) => h("label", { class: "listing-row" },
        h("input", { type: "checkbox", checked: !LIST.off.has(s.slug),
          onchange: (e) => { LIST.touched = true; if (e.target.checked) LIST.off.delete(s.slug); else LIST.off.add(s.slug); renderListing(); } }),
        h("span", { class: "grow" }, s.title + (s.complete > 1 ? ` ×${s.complete}` : ""),
          s.mastery && s.mastery.warn ? h("span", { class: "chip warn" }, icon("alert"), t("не освоено")) : null),
        h("span", { class: "num" }, t("{0} пл", fmt(setPriceOf(s.slug)))))))
        : h("div", { class: "sub" }, t("Цены ещё не загружены или готовых комплектов нет.")),
      noPrice.length ? h("div", { class: "sub" }, t("Не попали в список, потому что сейчас их никто не продаёт: {0}.", noPrice.map((s) => s.title).join(", "))) : null,
      h("p", { class: "foot" }, t("Цена — минимальная у продавцов в игре на эту минуту. Текст можно поправить прямо в поле. В чат игры вставьте его сами: приложение туда ничего не отправляет."))));
  dlg.querySelector(".dlg-body").scrollTop = scroll;
}
function openListingDialog() {
  const dlg = $("#dlg-listing");
  // a set that is not mastered yet is better built first than sold: left out until the user ticks it
  if (!LIST.touched) LIST.off = new Set(S.data.complete.filter((s) => s.mastery && s.mastery.warn).map((s) => s.slug));
  if (!dlg.open) dlg.showModal();
  renderListing();
}

// ----------------------------------------------------------------- selling: "sold", who buys now, a platinum target
/* The app cannot see a trade: a sale is what the user tells it.  "Продал" takes the parts of the set
   out of the inventory and writes the sale into the journal, where it can be taken back. */
const SELL = { set: null, price: 0, count: 1, buyer: "", busy: false, after: null };
function closeButton(dlg) {
  return h("button", { class: "btn ghost icon-only", "aria-label": t("Закрыть"), onclick: () => dlg.close() }, icon("close"));
}
function openSellDialog(set, opts) {
  const o = opts || {};
  const most = Math.max(1, set.complete || 1);
  Object.assign(SELL, { set, price: Math.max(0, Math.round(Number(o.price) || 0)), count: Math.min(Math.max(1, o.count || 1), most),
    buyer: o.buyer || "", busy: false, after: o.after || null });
  const dlg = $("#dlg-sell");
  if (!dlg.open) dlg.showModal();
  renderSell();
}
function renderSell() {
  const dlg = $("#dlg-sell"), set = SELL.set;
  if (!dlg.open || !set) return;
  const most = Math.max(1, set.complete || 1);
  const total = h("b", { class: "num" });
  const recount = () => { total.textContent = pl(SELL.price * SELL.count); };
  const price = h("input", { class: "num-input num", type: "number", min: "0", max: "100000", step: "1", value: String(SELL.price), "aria-label": t("Цена за один комплект, платина"),
    oninput: (e) => { SELL.price = Math.max(0, Math.round(Number(e.target.value) || 0)); recount(); },
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); recordSale(); } } });
  const count = h("input", { class: "num-input num", type: "number", min: "1", max: String(most), step: "1", value: String(SELL.count), disabled: most < 2, "aria-label": t("Сколько комплектов продано"),
    oninput: (e) => { SELL.count = Math.min(most, Math.max(1, Math.round(Number(e.target.value) || 1))); recount(); } });
  recount();
  const notMastered = (set.mastery && set.mastery.warn) || set.unmastered;
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, t("Продажа")), closeButton(dlg)),
    h("div", { class: "dlg-body" },
      h("div", { class: "sell-what" }, thumb(set.thumb), h("div", null, h("b", null, set.title),
        h("div", { class: "sub" }, SELL.buyer ? t("покупатель {0}", SELL.buyer) : tn("у вас # комплект|у вас # комплекта|у вас # комплектов", most)))),
      notMastered ? h("div", { class: "callout" }, icon("alert"), h("div", null, t("Этот комплект у вас не освоен: после продажи очки мастерства за него придётся добывать заново."))) : null,
      h("div", { class: "sell-form" },
        h("label", { class: "calc-field" }, h("span", { class: "sub" }, t("Цена за комплект, пл")), price),
        h("label", { class: "calc-field" }, h("span", { class: "sub" }, t("Количество")), count),
        h("div", { class: "calc-field" }, h("span", { class: "sub" }, t("Итого")), h("div", { class: "sell-total" }, total))),
      h("p", { class: "sub" }, t("Части комплекта уйдут из инвентаря, а сделка запишется в журнал (кнопка «История»). Запись можно отменить: части вернутся.")),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", disabled: SELL.busy, onclick: recordSale }, icon("check"), t("Записать продажу")),
        h("button", { class: "btn ghost", onclick: () => dlg.close() }, t("Отмена")))));
  price.focus();
  price.select();
}
async function recordSale() {
  if (SELL.busy || !SELL.set) return;
  SELL.busy = true;
  const sold = { slug: SELL.set.slug, sum: SELL.price * SELL.count, count: SELL.count };
  try {
    const res = await post("/api/sales/add", { slug: sold.slug, platinum: SELL.price, count: SELL.count, buyer: SELL.buyer });
    afterSale(res);
    $("#dlg-sell").close();
    toast(t("Продажа записана: +{0} пл", fmt(sold.sum)));
    if (SELL.after) SELL.after(sold);
  } catch (err) {
    toast(err.message);
  } finally {
    SELL.busy = false;
  }
}
// the inventory changed through a sale (or its undoing): show it, and do not announce it as news
function afterSale(res) {
  S.data = res.overview;
  S.parts.clear();
  const alive = new Set([...S.data.complete, ...S.data.partial].map((x) => x.slug));
  for (const slug of [...S.market.keys()]) if (!alive.has(slug)) S.market.delete(slug);
  render();
  queueMarket(false);                 // a set that came back with an undone sale has no price yet
  return ownUpdateSeen();
}
// the user's own press changed the inventory: the update it made is no news to announce
function ownUpdateSeen() {
  return loadHistory().then(() => {
    const last = HIST.data && HIST.data.updates[0];
    if (last) historySeen(last.at);
    renderChangesBanner();
    if ($("#dlg-history").open) renderHistory();
  });
}

/* Who buys the complete sets right now: buy orders of players who are in the game.  The orders came
   with the prices of the sets, so nothing is asked anew until the user presses "Обновить". */
const NOW = { data: null, state: "idle", error: "", copied: new Set(), refreshing: false };
async function loadSellNow() {
  try { NOW.data = await api("/api/sell-now"); NOW.state = "done"; NOW.error = ""; }
  catch (err) { NOW.state = "error"; NOW.error = err.message; }
  renderSellNow();
}
async function refreshSellNow() {
  if (NOW.refreshing) return;
  NOW.refreshing = true;
  renderSellNow();
  await queueMarket(true);
  NOW.refreshing = false;
  await loadSellNow();
}
function sellNowRow(row) {
  const b = row.buyers[0];
  const key = row.slug + "|" + b.user;
  const copied = NOW.copied.has(key);
  const set = S.data.complete.find((x) => x.slug === row.slug) || { slug: row.slug, title: row.title, thumb: row.thumb, complete: row.copies, unmastered: row.unmastered };
  return h("div", { class: "calc-step" },
    thumb(row.thumb, true),
    h("div", { class: "calc-what" },
      h("div", { class: "part-name" }, row.title + (row.copies > 1 ? ` ×${row.copies}` : "")),
      h("div", { class: "part-meta" }, row.unmastered ? h("span", { class: "chip warn" }, icon("alert"), t("не освоено")) : null,
        [t("покупатель {0}", b.user),
          typeof b.reputation === "number" && b.reputation > 0 ? t("репутация {0}", b.reputation) : null,
          b.quantity > 1 ? t("возьмёт {0} шт.", b.quantity) : null,
          row.buyers.length > 1 ? t("ещё покупают за {0}", row.buyers.slice(1).map((x) => fmt(x.platinum)).join(", ")) : null].filter(Boolean).join(" · "))),
    h("div", { class: "calc-num num" },
      h("b", null, pl(b.platinum)),
      h("div", { class: "sub" }, row.sell_min == null ? t("никто не продаёт") : row.sell_min > b.platinum ? t("продают от {0} пл", fmt(row.sell_min)) : t("не ниже цены продавцов"))),
    h("div", { class: "calc-actions" },
      h("button", { class: "btn subtle", title: b.message,
        onclick: async () => { await copyText(b.message, t("Сообщение скопировано — вставьте его в чат игры")); NOW.copied.add(key); renderSellNow(); } },
        icon(copied ? "check" : "copy"), t("Сообщение")),
      h("button", { class: "btn subtle", title: t("Сделка состоялась: убрать части из инвентаря и записать продажу"),
        onclick: () => openSellDialog(set, { price: b.platinum, buyer: b.user, after: () => loadSellNow() }) }, t("Продал…"))),
    copied ? h("input", { class: "msg-line", readonly: true, value: b.message, "aria-label": t("Сообщение покупателю"), onfocus: (e) => e.target.select() }) : null);
}
function renderSellNow() {
  const dlg = $("#dlg-sellnow");
  if (!dlg.open) return;
  const body = h("div", { class: "dlg-body" });
  const d = NOW.data;
  if (NOW.state === "error") body.append(h("div", { class: "callout" }, icon("alert"), h("div", null, NOW.error)));
  else if (!d) body.append(h("span", { class: "skeleton", style: "width:100%;height:140px" }));
  else {
    const stale = d.oldest_at && Date.now() / 1000 - d.oldest_at > d.ttl_orders;
    body.append(h("div", { class: "dlg-tools" },
      h("span", { class: "sub" }, !d.complete ? t("Готовых комплектов пока нет.")
        : d.priced < d.complete ? t("Заявки известны для {0} из {1} комплектов.", d.priced, d.complete)
          : t("Заявки покупателей запрошены {0}.", stampFmt.format(new Date(d.oldest_at * 1000)))),
      d.complete ? h("button", { class: "btn subtle", disabled: NOW.refreshing || S.queue.running, onclick: refreshSellNow },
        icon("refresh", NOW.refreshing ? "spin" : ""), NOW.refreshing ? t("Запрашиваю…") : t("Обновить")) : null));
    if (stale && !NOW.refreshing) {
      body.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
        t("Этим заявкам больше {0} минут: покупатели могли выйти из игры. Обновите, прежде чем писать.", Math.round(d.ttl_orders / 60)))));
    }
    if (d.sets.length) body.append(h("div", { class: "calc-list" }, d.sets.map(sellNowRow)));
    else if (d.complete) body.append(h("div", { class: "empty small" }, h("p", null, t("Сейчас никто из игроков в игре не покупает ваши комплекты. Загляните позже: заявки меняются каждую минуту."))));
    body.append(h("p", { class: "foot" }, t("Здесь только покупатели со статусом «в игре»: с ними можно торговать сразу. Сообщение вставьте в чат игры сами — приложение туда ничего не отправляет. Покупатель обычно предлагает меньше, чем просят продавцы: это плата за скорость.")));
  }
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(h("div", { class: "dlg-head" }, h("h2", null, t("Покупатели сейчас")), closeButton(dlg)), body);
  body.scrollTop = scroll;
}
function openSellNowDialog() {
  const dlg = $("#dlg-sellnow");
  if (!dlg.open) dlg.showModal();
  renderSellNow();
  loadSellNow();
}

/* "I need 500 platinum": the server picks what to sell from the complete sets -- what is bought often
   first -- out of the prices and the week's deals the app already holds. */
const GOAL = { target: remembered("primesets-plat-target", 300), keep: true, plan: null, state: "idle", error: "", done: [], exclude: new Set() };
async function planGoal() {
  if (!(GOAL.target >= 1)) { toast(t("Укажите, сколько платины нужно.")); return; }
  const need = GOAL.target - GOAL.done.reduce((a, x) => a + x.sum, 0);
  if (need <= 0) {
    GOAL.plan = { steps: [], platinum: 0, reached: true, held: [], unpriced: [], available: 0 };
    GOAL.state = "idle";
    renderGoal();
    return;
  }
  GOAL.state = "loading";
  renderGoal();
  try {
    GOAL.plan = await post("/api/sales/plan", { target: need, keep_unmastered: GOAL.keep, exclude: [...GOAL.exclude] });
    GOAL.state = "idle"; GOAL.error = "";
  } catch (err) {
    GOAL.state = "error"; GOAL.error = err.message;
  }
  renderGoal();
}
const SPEED = { fast: ["good", t("покупают часто")], normal: ["", t("покупают")], slow: ["quiet", t("покупают редко")] };
function goalStep(step) {
  const [cls, label] = SPEED[step.speed] || SPEED.slow;
  const own = S.data.complete.find((x) => x.slug === step.slug);
  const set = { ...(own || { slug: step.slug, title: step.title, thumb: step.thumb }), complete: Math.max(own ? own.complete : 1, step.count) };
  return h("div", { class: "calc-step" },
    thumb(step.thumb, true),
    h("div", { class: "calc-what" },
      h("div", { class: "part-name" }, step.title + (step.count > 1 ? ` ×${step.count}` : "")),
      h("div", { class: "part-meta" }, h("span", { class: "chip " + cls }, label),
        [step.deals != null ? tn("# сделка за неделю|# сделки за неделю|# сделок за неделю", step.deals) : t("о сделках данных нет"),
          step.buyer ? t("в игре покупают за {0} пл", fmt(step.buyer.platinum)) : null].filter(Boolean).join(" · "))),
    h("div", { class: "calc-num num" }, h("b", null, pl(step.sum)), step.count > 1 ? h("div", { class: "sub" }, t("по {0} пл", fmt(step.platinum))) : null),
    h("div", { class: "calc-actions" },
      h("button", { class: "btn subtle", title: t("Сделка состоялась: убрать части из инвентаря и записать продажу"),
        onclick: () => openSellDialog(set, { price: step.platinum, count: step.count,
          after: (sold) => { GOAL.done.push({ title: step.title, thumb: step.thumb, sum: sold.sum, count: sold.count }); planGoal(); } }) }, t("Продал…")),
      h("button", { class: "btn subtle", title: t("Не предлагать этот комплект в этом подборе"),
        onclick: () => { GOAL.exclude.add(step.slug); planGoal(); } }, t("Не этот"))));
}
function goalListing() {
  const steps = GOAL.plan ? GOAL.plan.steps : [];
  const sets = steps.map((st) => { const own = S.data.complete.find((x) => x.slug === st.slug); return own ? { ...own, complete: st.count } : null; })
    .filter((s) => s && setPriceOf(s.slug) != null);
  if (!sets.length) { toast(t("Цены ещё не загружены или готовых комплектов нет.")); return; }
  copyText(listingText(sets), t("Объявление скопировано — вставьте его в чат игры"));
}
function renderGoal() {
  const dlg = $("#dlg-goal");
  if (!dlg.open) return;
  const p = GOAL.plan;
  const sold = GOAL.done.reduce((a, x) => a + x.sum, 0);
  const input = h("input", { class: "num-input num", type: "number", min: "1", max: "1000000", step: "10", value: String(GOAL.target), "aria-label": t("Сколько платины нужно"),
    oninput: (e) => { GOAL.target = Math.max(0, Math.round(Number(e.target.value) || 0)); remember("primesets-plat-target", GOAL.target); },
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); planGoal(); } } });
  const body = h("div", { class: "dlg-body" },
    h("div", { class: "calc-head" },
      h("div", { class: "calc-title" }, h("div", { class: "sub" }, t("Что продать, чтобы получить нужное число платины. Сначала то, что покупают часто: такая сделка состоится сегодня, а не через неделю."))),
      h("div", { class: "calc-form" },
        h("label", { class: "calc-field" }, h("span", { class: "sub" }, t("Нужно платины")), input),
        h("button", { class: "btn primary", disabled: GOAL.state === "loading", onclick: () => planGoal() },
          GOAL.state === "loading" ? t("Считаю…") : p || GOAL.done.length ? t("Пересчитать") : t("Подобрать")))),
    h("label", { class: "check-line" },
      h("input", { type: "checkbox", checked: GOAL.keep, onchange: (e) => { GOAL.keep = e.target.checked; if (p) planGoal(); } }),
      h("span", null, t("Не трогать неосвоенное: такие комплекты лучше сначала построить"))));
  if (GOAL.state === "error") body.append(h("div", { class: "callout" }, icon("alert"), h("div", null, GOAL.error)));
  if (p) {
    const trades = p.steps.reduce((a, s) => a + s.count, 0);
    body.append(h("div", { class: "calc-sum" },
      h("div", { class: "price num" }, fmt(sold + p.platinum), h("span", { class: "unit" }, t("пл"))),
      h("div", { class: "sub num" }, [tn("# сделка|# сделки|# сделок", trades + GOAL.done.reduce((a, x) => a + x.count, 0)),
        sold ? t("из них уже продано на {0} пл", fmt(sold)) : null].filter(Boolean).join(" · "))));
    if (!p.reached) {
      body.append(h("div", { class: "callout" }, icon("alert"), h("div", null, p.available || GOAL.done.length
        ? t("На {0} пл готовых комплектов не хватает: по нынешним ценам выходит {1}.", fmt(GOAL.target), fmt(sold + p.platinum))
        : t("Подбирать не из чего: нет готовых комплектов с известной ценой."))));
    }
    if (p.oldest_at && Date.now() / 1000 - p.oldest_at > p.ttl_orders) {
      body.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
        h("div", null, t("Цены в этом подборе запрошены {0} и могли измениться.", stampFmt.format(new Date(p.oldest_at * 1000)))),
        h("div", { class: "actions" }, h("button", { class: "btn subtle", disabled: S.queue.running,
          onclick: async () => { await queueMarket(true); planGoal(); } }, icon("refresh"), t("Обновить цены и пересчитать"))))));
    }
    if (GOAL.done.length) {
      body.append(h("div", { class: "calc-list done" }, GOAL.done.map((x) => h("div", { class: "calc-step" },
        thumb(x.thumb, true),
        h("div", { class: "calc-what" }, h("div", { class: "part-name" }, x.title + (x.count > 1 ? ` ×${x.count}` : "")),
          h("div", { class: "part-meta" }, icon("check"), t("продано"))),
        h("div", { class: "calc-num num" }, h("b", null, pl(x.sum))), h("span")))));
    }
    if (p.steps.length) body.append(h("div", { class: "calc-list" }, p.steps.map(goalStep)));
    else if (p.reached && GOAL.done.length) body.append(h("div", { class: "sub ok-line" }, icon("check"), t("Нужная сумма набрана.")));
    const notes = [];
    if (p.held && p.held.length) notes.push(t("Не тронуты как неосвоенные: {0}.", p.held.join(", ")));
    if (p.unpriced && p.unpriced.length) notes.push(t("Сейчас их никто не продаёт, цены нет: {0}.", p.unpriced.join(", ")));
    if (notes.length) body.append(h("div", { class: "sub" }, notes.join(" ")));
    body.append(h("div", { class: "calc-foot sub" },
      h("span", null, t("Цена — минимальная у продавцов в игре; частота — закрытые сделки за последнюю неделю. Число сделок в день в игре ограничено рангом мастерства.")),
      h("span", { class: "foot-links" },
        p.steps.length ? h("button", { class: "link-btn", onclick: goalListing }, t("Объявление по этому списку")) : null,
        GOAL.done.length || GOAL.exclude.size ? h("button", { class: "link-btn", onclick: () => { GOAL.done = []; GOAL.exclude.clear(); planGoal(); } }, t("Начать подбор заново")) : null)));
  }
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(h("div", { class: "dlg-head" }, h("h2", null, t("Цель по платине")), closeButton(dlg)), body);
  body.scrollTop = scroll;
}
function openGoalDialog() {
  const dlg = $("#dlg-goal");
  if (!dlg.open) dlg.showModal();
  renderGoal();
}

// ----------------------------------------------------------------- chrome: tiles, tabs, banners
function tile(label, value, unit, sub, attention, title) {
  return h("div", { class: "tile" + (attention ? " attention" : ""), title: title || "" },
    h("div", { class: "tile-label" }, label),
    h("div", { class: "tile-value" }, value, unit ? h("span", { class: "tile-unit" }, unit) : null),
    h("div", { class: "tile-sub" }, sub || ""));
}
function renderTiles() {
  const d = S.data, box = $("#tiles");
  if (!d.complete.length && !d.partial.length) { box.hidden = true; return; }
  box.hidden = false;
  const copies = d.complete.reduce((a, x) => a + x.complete, 0);
  let sum = 0, priced = 0, noOffer = 0;
  for (const set of d.complete) {
    const m = S.market.get(set.slug);
    if (m && m.state === "done" && m.data.price) {
      if (m.data.price.value != null) { sum += m.data.price.value * set.complete; priced++; } else noOffer++;
    }
  }
  const loaded = d.complete.filter((x) => { const m = S.market.get(x.slug); return m && m.state !== "loading"; }).length;
  const vaulted = d.complete.filter((x) => x.vault.state === "vaulted").length;
  const notMastered = d.complete.filter((x) => x.mastery.state === "none").length;
  const unknownMastery = d.complete.filter((x) => x.mastery.state === "unknown").length;
  const near = d.partial.filter((x) => x.missing_count === 1).length;
  let valueSub = t("по минимальным ценам продавцов в игре");
  if (d.complete.length && loaded < d.complete.length) valueSub = t("считаю… {0} из {1}", loaded, d.complete.length);
  else if (noOffer) valueSub = tn("без # комплекта: нет предложений|без # комплектов: нет предложений|без # комплектов: нет предложений", noOffer);
  let masterySub = t("всё, что собрано, уже освоено");
  if (notMastered) masterySub = t("сначала постройте, потом продавайте");
  else if (unknownMastery) masterySub = t("ещё не отмечено: {0} — щёлкните по метке у комплекта", unknownMastery);
  box.replaceChildren(
    tile(t("Готовых комплектов"), String(d.complete.length), null,
      copies > d.complete.length ? tn("всего # экземпляр|всего # экземпляра|всего # экземпляров", copies) : (near ? t("ещё {0} — без одной части", near) : "")),
    tile(t("Стоимость на warframe.market"), d.complete.length ? fmt(sum) : "0", t("пл"), valueSub, false,
      t("Сумма минимальных цен продажи по всем готовым комплектам")),
    tile(t("В хранилище"), String(vaulted), null, d.complete.length ? t("из {0} готовых", d.complete.length) : ""),
    tile(t("Не освоено"), String(notMastered), null, masterySub, notMastered > 0,
      t("Готовые комплекты, которые ещё не дали вам очки мастерства")));
}
function renderTabs() {
  const d = S.data;
  const tabs = [
    ["complete", t("Готовые комплекты"), d.complete.length],
    ["partial", t("Почти собраны"), d.partial.length],
    ["parts", t("Все части"), d.inventory.distinct],
    ["ducats", t("Дукаты"), D.list ? D.list.length : null],
    ["collection", t("Коллекция"), null],
  ];
  $("#tabs").replaceChildren(...tabs.map(([id, label, count]) => h("button", {
    class: "tab", role: "tab", "aria-selected": String(S.tab === id),
    onclick: () => { S.tab = id; S.open.clear(); try { localStorage.setItem("primesets-tab", id); } catch (e) { /* ignore */ } renderTabs(); renderView(); },
  }, label, count == null ? null : h("span", { class: "count num" }, String(count)))));
}
function renderStatus() {
  const inv = S.data.inventory;
  let text = t("Инвентарь пока пуст");
  if (S.data.demo) {
    text = [t("Пример инвентаря"), tn("# часть|# части|# частей", inv.total)].join(" · ");
  } else if (inv.updated_at && inv.distinct) {
    const src = { screenshots: t("по скриншотам"), "screenshots+manual": t("по скриншотам, с правками вручную"), manual: t("введён вручную") }[inv.source] || "";
    text = [t("Инвентарь от {0}", stampFmt.format(new Date(inv.updated_at))), src, tn("# часть|# части|# частей", inv.total)].filter(Boolean).join(" · ");
  }
  $("#inv-status").textContent = text;
}
async function setDemo(on) {
  try {
    S.data = await post("/api/demo", { on });
    S.parts.clear(); S.market.clear(); S.lite.clear();
    HIST.data = null;
    render();
    queueMarket(false);
    checkChanges();
  } catch (err) { toast(err.message); }
}
function renderBanners() {
  const d = S.data, cat = d.catalog;
  // a newer version is out: say so once, with the way to its page; nothing is downloaded by the app itself
  const ub = $("#update-banner"), up = d.update || {};
  let skipped = "";
  try { skipped = localStorage.getItem("primesets-update-skip") || ""; } catch (e) { /* ignore */ }
  if (up.state === "newer" && up.latest && up.latest !== skipped) {
    ub.replaceChildren(icon("up"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, t("Вышла версия {0}", up.latest)),
        h("div", { class: "notice-text" }, t("У вас версия {0}. Новую можно скачать на странице проекта: достаточно заменить файл программы, данные останутся.", up.current))),
      up.url ? h("a", { class: "btn primary", href: up.url, target: "_blank", rel: "noopener" }, icon("external"), t("Открыть страницу")) : null,
      h("button", { class: "btn subtle", onclick: () => { try { localStorage.setItem("primesets-update-skip", up.latest); } catch (e) { /* ignore */ } ub.hidden = true; } }, t("Позже")));
    ub.hidden = false;
  } else {
    ub.hidden = true;
  }
  const db = $("#demo-banner");
  if (d.demo) {
    db.replaceChildren(icon("info"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, t("Это пример: выдуманный инвентарь")),
        h("div", { class: "notice-text" }, t("Цены настоящие, а части придуманы — чтобы посмотреть, как работает программа. Изменить пример нельзя; ваш собственный инвентарь он не затрагивает."))),
      h("button", { class: "btn primary", onclick: () => { setDemo(false).then(openUpdateDialog); } }, icon("image"), t("Добавить свой инвентарь")),
      h("button", { class: "btn subtle", onclick: () => setDemo(false) }, t("Убрать пример")));
    db.hidden = false;
  } else {
    db.hidden = true;
  }
  const cb = $("#catalog-banner");
  if (cat.building) {
    const share = cat.total ? Math.round(cat.done / cat.total * 100) : 0;
    cb.replaceChildren(icon("refresh", "spin"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, cat.ready ? t("Обновляю справочник комплектов") : t("Загружаю справочник комплектов с warframe.market")),
        h("div", { class: "notice-text" }, t("{0}. Это нужно один раз, дальше данные берутся из кэша.", cat.total > 1 ? t("{0}: {1} из {2}", cat.stage, cat.done, cat.total) : cat.stage)),
        h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: `width:${share}%` }))));
    cb.hidden = false;
  } else if (cat.error && !cat.ready) {
    cb.replaceChildren(icon("alert"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, t("Не удалось загрузить справочник комплектов")),
        h("div", { class: "notice-text" }, cat.error)),
      h("button", { class: "btn subtle", onclick: refreshCatalog }, t("Повторить")));
    cb.hidden = false;
  } else if (cat.ready && cat.droptables && !cat.droptables.available) {
    cb.replaceChildren(icon("alert"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, t("Таблицы дропа Digital Extremes недоступны")),
        h("div", { class: "notice-text" }, t("Колонка «В хранилище» пока без данных. ") + (cat.droptables.error || ""))),
      h("button", { class: "btn subtle", onclick: refreshCatalog }, t("Повторить")));
    cb.hidden = false;
  } else {
    cb.hidden = true;
  }

  const rb = $("#review-banner");
  const review = d.inventory.review || [];
  if (review.length) {
    const list = h("ul", { hidden: !S.reviewOpen }, review.map((r, i) => h("li", null,
      h("span", { class: "grow" },
        h("b", null, r.name), r.count ? ` ×${r.count}` : "", " — ", r.note || "",
        r.suggestions && r.suggestions.length ? ". " + t("Похоже на: {0}", r.suggestions.map((x) => x.item).join("; ")) : ""),
      h("button", { class: "btn subtle", onclick: async () => { try { S.data = await post("/api/inventory/dismiss-review", { index: i }); render(); } catch (e) { toast(e.message); } } }, t("Понятно")))));
    const toggle = h("button", { class: "btn subtle", "aria-expanded": String(Boolean(S.reviewOpen)),
      onclick: () => { S.reviewOpen = !S.reviewOpen; renderBanners(); } }, S.reviewOpen ? t("Свернуть") : t("Показать"));
    rb.replaceChildren(icon("alert"),
      h("div", { class: "notice-body" },
        h("div", { class: "notice-title" }, tn("Проверьте # запись после распознавания|Проверьте # записи после распознавания|Проверьте # записей после распознавания", review.length)),
        h("div", { class: "notice-text", hidden: Boolean(S.reviewOpen) }, t("Часть названий прочитана неуверенно или не найдена в каталоге.")),
        list),
      toggle);
    rb.hidden = false;
  } else {
    rb.hidden = true;
  }
}
const EN_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
const longDate = new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", year: "numeric" });
function localDate(text) {
  // the drop tables page signs itself as "22 October, 2026"
  const m = /^(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})$/.exec((text || "").trim());
  const month = m ? EN_MONTHS.indexOf(m[2].toLowerCase()) : -1;
  return month < 0 ? text : longDate.format(new Date(Number(m[3]), month, Number(m[1])));
}
function renderLegend() {
  const d = S.data, cat = d.catalog, lim = d.limits;
  const dt = cat.droptables || {};
  const when = (ts) => (ts ? stampFmt.format(new Date(ts * 1000)) : "—");
  $("#legend-body").replaceChildren(
    h("div", null, h("h3", null, t("Цена на warframe.market")),
      t("Самая низкая цена продажи целого комплекта среди игроков, которые прямо сейчас в игре (платформа ПК). Если таких нет — у тех, кто онлайн на сайте, с пометкой. Рядом для сверки — средняя цена реальных сделок за последние 7 дней.")),
    h("div", null, h("h3", null, t("Цена за 3 месяца")),
      t("История закрытых сделок за 90 дней. Сравнивается средняя цена первых {0} дней и последних {1} дней (медианы по дням, взвешенные по числу сделок). Изменение меньше {2} % считается стабильной ценой.", lim.trend_window, lim.trend_window, Math.round(lim.trend_threshold * 100))),
    h("div", null, h("h3", null, t("В хранилище")),
      t("«Да» — ни одна реликвия с частями комплекта сейчас не выпадает в миссиях. Источник — официальные таблицы дропа Digital Extremes{0}. Пометка «особые реликвии» — когда в миссиях реликвий нет, но warframe.market не считает их убранными в хранилище.",
        dt.updated ? " " + t("(редакция от {0})", localDate(dt.updated)) : "")),
    h("div", null, h("h3", null, t("Дукатов за 1 платину")),
      t("Вкладка «Дукаты»: сколько дукатов дают все части комплекта в киоске (стоимость частей в дукатах — из данных warframe.market), делённое на цену комплекта — ту же минимальную цену продавца в игре. Учтены все комплекты справочника, а не только ваши. Цены запрашиваются по кнопке: это по одному запросу на комплект.")),
    h("div", null, h("h3", null, t("Полный комплект и освоение")),
      t("Комплект считается по составу с warframe.market: если часть нужна в двух экземплярах, учитываются оба. Отметки «освоено» берутся с ваших скриншотов кузницы или профиля либо ставятся вручную — у Digital Extremes нет открытых данных об аккаунте.")),
    h("div", { class: "wide" },
      t("Приложение не подключается к игре и ничего в ней не делает: оно работает с картинками, которые вы сделали сами, и с открытыми данными. "),
      t("Запросы к warframe.market идут по одному, не чаще {0} в секунду (правила сайта разрешают 3); цены хранятся {1} минут, статистика — {2} часов. ", Math.round(1 / lim.wfm_min_interval), Math.round(lim.ttl_orders / 60), Math.round(lim.ttl_stats / 3600)),
      t("Справочник комплектов: {0}. Запросов к маркету за этот запуск: {1}. ", when(cat.built_at), d.requests.api_requests),
      h("a", { href: "#", onclick: (e) => { e.preventDefault(); refreshCatalog(); } }, t("Обновить справочник"))));
}
async function refreshCatalog() {
  try { await post("/api/catalog/refresh"); toast(t("Обновляю справочник…")); await loadOverview(); } catch (err) { toast(err.message); }
}

function renderView() {
  const d = S.data, view = $("#view");
  if (!d.catalog.ready) {
    view.replaceChildren(d.catalog.building ? h("div") : emptyState(t("Справочник ещё не загружен"), t("Проверьте подключение к интернету и нажмите «Повторить» выше."), false));
    return;
  }
  view.replaceChildren(S.tab === "partial" ? viewPartial() : S.tab === "parts" ? viewParts() : S.tab === "ducats" ? viewDucats()
    : S.tab === "collection" ? viewCollection() : viewComplete());
}
function render() {
  if (!S.data) return;
  C.stale = true;                     // the inventory or the mastery marks may have changed: the collection is asked for anew
  renderStatus(); renderBanners(); renderTiles(); renderTabs(); renderView(); renderLegend();
  $("#btn-prices").disabled = !S.data.complete.length && S.tab !== "ducats";
}

// ----------------------------------------------------------------- market queue
function setProgress() {
  const q = S.queue, bar = $("#progress");
  bar.hidden = !q.running;
  $("#progress-fill").style.width = (q.total ? Math.round(q.done / q.total * 100) : 0) + "%";
  const btn = $("#btn-prices");
  btn.firstElementChild.classList.toggle("spin", q.running);
}
async function queueMarket(force) {
  if (!S.data || !S.data.catalog.ready) return;
  const gen = ++S.queueGen;
  const todo = S.data.complete.map((x) => x.slug).filter((slug) => {
    const m = S.market.get(slug);
    return force || !m || m.state === "error";
  });
  if (!todo.length) { S.queue.running = false; setProgress(); renderTiles(); return; }
  S.queue = { running: true, done: 0, total: todo.length };
  for (const slug of todo) S.market.set(slug, { state: "loading" });
  setProgress(); renderTiles(); renderView();
  const worker = async () => {
    while (todo.length && gen === S.queueGen) {
      const slug = todo.shift();
      try {
        const data = await api(`/api/market?slug=${slug}${force ? "&force=1" : ""}`);
        S.market.set(slug, { state: "done", data });
      } catch (err) {
        S.market.set(slug, { state: "error", error: err.message });
      }
      if (gen !== S.queueGen) return;
      S.queue.done++;
      refreshRow(slug); renderTiles(); setProgress();
    }
  };
  await Promise.all([worker(), worker()]);
  if (gen !== S.queueGen) return;
  S.queue.running = false;
  setProgress(); renderTiles();
  reportValue();
  if (S.tab === "complete") renderView();      // apply the price/trend sort once everything is in
}

// ----------------------------------------------------------------- update dialog
const pad2 = (n) => String(n).padStart(2, "0");
async function uploadScreenshots(list) {
  const pics = [...list].filter((f) => /\.(png|jpe?g|webp|bmp)$/i.test(f.name) || /^image\//.test(f.type || ""));
  if (!pics.length) { toast(t("Подходят только картинки: png, jpg, webp.")); return 0; }
  let ok = 0;
  const now = new Date();
  const stamp = `${now.getFullYear()}${pad2(now.getMonth() + 1)}${pad2(now.getDate())}-${pad2(now.getHours())}${pad2(now.getMinutes())}${pad2(now.getSeconds())}`;
  for (const [i, f] of pics.entries()) {
    // a picture pasted from the clipboard arrives as a nameless "image.png": give it a readable name
    let name = f.name || "";
    if (!name || /^image\.(png|jpe?g|webp|bmp)$/i.test(name)) {
      const ext = (f.type || "image/png").split("/")[1].replace("jpeg", "jpg");
      name = `screenshot-${stamp}${pics.length > 1 ? "-" + (i + 1) : ""}.${ext}`;
    }
    try {
      await api("/api/screenshot?name=" + encodeURIComponent(name), { method: "POST", headers: { "X-Requested-With": "primesets" }, body: f });
      ok++;
    } catch (err) { toast(`${name}: ${err.message}`); }
  }
  if (ok) toast(t("Добавлено скриншотов: {0}", ok));
  return ok;
}

const R = { state: null, mode: null, timer: 0, loginUntil: 0, busy: false, showAll: false, zoom: null };
async function refreshRecognize(force) {
  try {
    R.state = await api("/api/recognize" + (force ? "?refresh=1" : ""));
  } catch (err) {
    if (!R.state) R.state = { provider: { id: "", kind: "", ready: false, reason: "error", error: err.message }, job: null, files: [] };
  }
  renderDialog();
  scheduleRecognizePoll();
}
function scheduleRecognizePoll() {
  clearTimeout(R.timer);
  const dlg = $("#dlg-update");
  const job = R.state && R.state.job;
  const running = job && job.state === "running";
  if (!dlg.open && !running) return;
  const checking = R.state && R.state.joins && R.state.joins.state === "checking";
  if (running) R.timer = setTimeout(() => refreshRecognize(false), 1000);
  // the join check runs in the background; the server also announces its end, this is the fallback
  else if (checking) R.timer = setTimeout(() => refreshRecognize(false), 900);
  // after "Войти" keep checking for a few minutes, so the dialog notices the finished sign-in by itself
  else if (Date.now() < R.loginUntil && !(R.state && R.state.provider.ready)) R.timer = setTimeout(() => refreshRecognize(true), 4000);
}
async function recognizeAction(path, payload) {
  if (R.busy) return null;
  R.busy = true;
  try {
    const res = await api(path, { method: "POST", headers: { "Content-Type": "application/json", "X-Requested-With": "primesets" }, body: JSON.stringify(payload || {}) });
    if (res && res.recognize) R.state = res.recognize; else if (res && res.provider) R.state = res;
    return res;
  } catch (err) {
    toast(err.message);
    return null;
  } finally {
    R.busy = false;
    renderDialog();
    scheduleRecognizePoll();
  }
}

// who reads the screenshots: the connection chosen in the settings
const PROVIDER = {
  claude_cli: { title: "Claude Code", kind: t("Подписка Claude"), login: t("Войти в Claude Code"),
    missing: t("На этом компьютере не найден Claude Code. Установите его (он ставится и вместе с приложением Claude) или выберите другое подключение.") },
  codex_cli: { title: "Codex", kind: t("Подписка ChatGPT"), login: t("Войти в Codex"),
    missing: t("На этом компьютере не найден Codex. Установите приложение Codex или Codex CLI либо выберите другое подключение.") },
  anthropic_api: { title: "Claude API", kind: t("API-ключ Anthropic") },
  openai_api: { title: "OpenAI API", kind: t("API-ключ OpenAI") },
  deepseek_api: { title: "DeepSeek API", kind: t("API-ключ DeepSeek") },
  gemini_api: { title: "Gemini API", kind: t("API-ключ Google") },
};
function providerLine(p) {
  const meta = PROVIDER[p.id] || { title: p.id || "?", kind: "" };
  const settings = (label, primary) => h("button", { class: primary ? "btn primary" : "btn subtle", onclick: () => openSettingsDialog() }, label);
  if (p.ready) {
    const model = p.model || t("по умолчанию");
    return h("div", null,
      h("div", { class: "sub ok-line" }, icon("check"), h("span", null,
        p.kind === "api"
          ? t("Читает {0} по вашему ключу (модель: {1}). Картинки отправляются только этому сервису; запросы оплачиваются по его тарифам.", meta.title, model)
          : t("Читает {0} по вашей подписке (модель: {1}). Картинки отправляются только этому сервису.", meta.title, model),
        " ", h("button", { class: "link-btn", onclick: () => openSettingsDialog() }, t("Изменить подключение")))),
      p.pillow === false ? h("div", { class: "sub" }, t("Не найдена библиотека Pillow: большие скриншоты читаются целиком, мелкий текст может распознаться хуже.")) : null);
  }
  let text, buttons = [settings(t("Открыть настройки"), false)];
  if (p.reason === "no_cli") {
    text = meta.missing || "";
  } else if (p.reason === "login") {
    text = t("Нужен разовый вход в {0} — своим аккаунтом. Откроется окно с командой входа и браузер; пароль приложение не видит.", meta.title);
    buttons = [
      h("button", { class: "btn primary", onclick: async () => { R.loginUntil = Date.now() + 5 * 60000; await recognizeAction("/api/recognize/login"); } }, meta.login || t("Войти")),
      h("button", { class: "btn subtle", onclick: () => refreshRecognize(true) }, icon("refresh"), t("Проверить снова")),
      settings(t("Другое подключение"), false)];
  } else if (p.reason === "no_key") {
    text = t("Для подключения «{0}» нужен ваш API-ключ: введите его в настройках. Ключ хранится только на этом компьютере, в зашифрованном виде.", meta.title);
    buttons = [settings(t("Открыть настройки"), true)];
  } else if (p.reason === "no_sdk") {
    text = t("Для Claude API нужна библиотека anthropic: выполните «pip install anthropic» или пользуйтесь готовым exe.");
  } else {
    text = p.error || t("Подключение для распознавания не настроено.");
    buttons = [h("button", { class: "btn subtle", onclick: () => refreshRecognize(true) }, icon("refresh"), t("Проверить снова")), settings(t("Открыть настройки"), false)];
  }
  return h("div", { class: "callout" }, icon("alert"), h("div", null, h("div", null, text), h("div", { class: "actions" }, buttons)));
}

// which screenshots stand at a break of the list (see primesets/continuity.py)
function gapNames(joins) {
  const names = new Set();
  if (joins && (joins.state === "gaps" || joins.state === "unsure")) {
    for (const g of joins.gaps) { names.add(g.after); names.add(g.before); }
  }
  return names;
}
// the topmost / lowest screenshot when it is not the top / bottom of the list
function edgeNames(joins) {
  const names = new Set();
  if (joins && joins.available) {
    if (joins.start === "missing" && joins.first) names.add(joins.first);
    if (joins.end === "missing" && joins.last) names.add(joins.last);
  }
  return names;
}
function shotNumber(files, name) {
  const i = files.findIndex((f) => f.name === name);
  return i < 0 ? "?" : String(i + 1);
}
function zoomShot(name) { R.zoom = name; renderDialog(); }
function lightbox(files) {
  if (!R.zoom || !files.some((f) => f.name === R.zoom)) { R.zoom = null; return null; }
  const close = () => { R.zoom = null; renderDialog(); };
  return h("div", { class: "lightbox", role: "button", tabindex: "0", "aria-label": t("Закрыть просмотр"), onclick: close,
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); close(); } } },
    h("span", { class: "lightbox-cap" }, t("Снимок №{0} · {1} · нажмите, чтобы закрыть", shotNumber(files, R.zoom), R.zoom)),
    h("img", { src: "/api/screenshot-thumb?large=1&name=" + encodeURIComponent(R.zoom), alt: "" }));
}

function fileGrid(files, locked, joins) {
  if (!files.length) return h("div", { class: "sub" }, t("Скриншотов пока нет."));
  const gaps = gapNames(joins);
  const edges = edgeNames(joins);
  const key = (locked ? "L|" : "U|") + files.map((f) => f.name + ":" + Math.round(f.mtime)).join("|") + "#" + [...gaps].join("|") + "#" + [...edges].join("|");
  if (R.gridKey === key && R.gridEl) return R.gridEl;
  R.gridKey = key;
  R.gridEl = h("div", { class: "shots" }, files.map((f, i) => h("div", { class: "shot" + (gaps.has(f.name) ? " gap" : edges.has(f.name) ? " edge" : ""),
      title: gaps.has(f.name) ? t("{0} — здесь список не стыкуется с соседним снимком", f.name)
        : edges.has(f.name) ? t("{0} — список продолжается за этим снимком", f.name) : f.name },
    h("img", { src: "/api/screenshot-thumb?name=" + encodeURIComponent(f.name) + "&v=" + Math.round(f.mtime), alt: "", loading: "lazy",
      onclick: () => zoomShot(f.name) }),
    h("span", { class: "shot-n" }, String(i + 1)),
    h("span", { class: "shot-name" }, f.name),
    locked ? null : h("button", { class: "shot-x", "aria-label": t("Убрать {0}", f.name), title: t("Убрать из списка (файл переедет в папку _done)"),
      onclick: () => recognizeAction("/api/screenshots/remove", { name: f.name }) }, icon("close")))));
  return R.gridEl;
}

// "Between №9 and №10 the list does not join": the same wording before and after the reading
function gapLines(joins, files) {
  const pill = (name) => h("button", { class: "pill", title: t("Посмотреть снимок {0}", name), onclick: () => zoomShot(name) }, shotNo(shotNumber(files, name)));
  const item = (text) => h("span", { class: "sub" }, " " + text);
  return h("ul", { class: "gap-list" }, joins.gaps.map((g) => h("li", null, tx("между {0}{1} и {2}{3}",
    pill(g.after), g.after_item ? item(t("(последняя часть — «{0}»)", g.after_item)) : null,
    pill(g.before), g.before_item ? item(t("(первая — «{0}»)", g.before_item)) : null))));
}
// "the list was not shot from its top / to its bottom": notes for the dialog (review = after the reading)
function endsNotes(joins, files, review, mode) {
  if (!joins || !joins.available) return [];
  const pill = (name) => h("button", { class: "pill warn", title: t("Посмотреть снимок {0}", name), onclick: () => zoomShot(name) }, shotNo(shotNumber(files, name)));
  const tail = review
    ? (mode === "replace"
        ? t("В режиме «Это весь мой список» непрочитанные части исчезнут из инвентаря — безопаснее «Только добавить и обновить» либо «Не заносить», доснять и распознать заново.")
        : t("Поэтому выбран режим «Только добавить и обновить»: непрочитанные части останутся в инвентаре как были. Надёжнее — «Не заносить», доснять и распознать заново."))
    : null;
  const notes = [];
  const lastItem = joins.last_item ? h("span", { class: "sub" }, " " + t("(последняя часть — «{0}»)", joins.last_item)) : null;
  const firstItem = joins.first_item ? h("span", { class: "sub" }, " " + t("(первая часть — «{0}»)", joins.first_item)) : null;
  if (joins.end === "missing" && joins.last) {
    notes.push(h("div", { class: "callout joins" }, icon("alert"), h("div", null,
      h("b", null, t("Список, похоже, снят не до конца")),
      h("div", { class: "gap-how" }, review
        ? tx("Внизу снимка {0}{1} виден обрезанный ряд, а снимка с продолжением нет: его части не прочитаны.", pill(joins.last), lastItem)
        : tx("Внизу снимка {0}{1} виден обрезанный ряд, а снимка с продолжением нет: его части не прочитаются. Долистайте список в игре до упора, нажмите F6 и добавьте снимок сюда.", pill(joins.last), lastItem)),
      tail ? h("div", { class: "gap-how" }, tail) : null)));
  }
  if (joins.start === "missing" && joins.first) {
    notes.push(h("div", { class: "callout joins" }, icon("alert"), h("div", null,
      h("b", null, t("Список, похоже, снят не с начала")),
      h("div", { class: "gap-how" }, review
        ? tx("На снимке {0}{1} ползунок прокрутки стоит не в самом верху: выше есть ещё ряды.", pill(joins.first), firstItem)
        : tx("На снимке {0}{1} ползунок прокрутки стоит не в самом верху: выше есть ещё ряды. Если там прайм-части — вернитесь в начало списка, нажмите F6 и добавьте снимок сюда.", pill(joins.first), firstItem)),
      tail ? h("div", { class: "gap-how" }, tail) : null)));
  }
  return notes;
}
function joinsBlock(joins, files) {
  if (!joins || !joins.available) return null;
  const main = joinsVerdict(joins, files);
  const notes = endsNotes(joins, files, false, null);
  if (!main && !notes.length) return null;
  return h("div", { class: "joins-all" }, main, notes);
}
function joinsVerdict(joins, files) {
  if (joins.state === "checking") {
    return h("div", { class: "sub ok-line joins" }, icon("refresh", "spin"), t("Сверяю, стыкуются ли экраны списка…"));
  }
  const whole = joins.start === "ok" && joins.end === "ok";
  if (joins.state === "ok") {
    return h("div", { class: "sub ok-line joins" }, icon("check"),
      whole ? tn("Экраны инвентаря стыкуются: # снимок, пропущенных рядов нет, список снят от начала до конца.|Экраны инвентаря стыкуются: # снимка, пропущенных рядов нет, список снят от начала до конца.|Экраны инвентаря стыкуются: # снимков, пропущенных рядов нет, список снят от начала до конца.", joins.pages)
        : tn("Экраны инвентаря стыкуются: # снимок, пропущенных рядов нет.|Экраны инвентаря стыкуются: # снимка, пропущенных рядов нет.|Экраны инвентаря стыкуются: # снимков, пропущенных рядов нет.", joins.pages));
  }
  if (joins.state === "none" && joins.pages === 1 && whole) {
    return h("div", { class: "sub ok-line joins" }, icon("check"), t("Список помещается на одном снимке и снят целиком."));
  }
  if (joins.state === "gaps") {
    return h("div", { class: "callout bad joins" }, icon("alert"), h("div", null,
      h("b", null, joins.gaps.length === 1 ? t("Похоже, при прокрутке пропущен ряд")
        : tn("Похоже, при прокрутке пропущены ряды: # место|Похоже, при прокрутке пропущены ряды: # места|Похоже, при прокрутке пропущены ряды: # мест", joins.gaps.length)),
      h("div", null, t("Список не стыкуется:")),
      gapLines(joins, files),
      h("div", { class: "gap-how" }, t("Части из пропущенного ряда не прочитаются. Вернитесь в игре к этому месту, сделайте ещё один снимок (F6) так, чтобы на нём был виден пропущенный ряд, и добавьте его сюда — порядок снимков не важен."))));
  }
  if (joins.state === "unsure") {
    return h("div", { class: "callout bad joins" }, icon("alert"), h("div", null,
      h("b", null, t("Соседние снимки не стыкуются ни в одной паре")),
      h("div", { class: "gap-how" }, t("Если вы листали больше чем на три ряда за раз, между экранами остались непрочитанные ряды. Листайте так, чтобы обрезанный нижний ряд становился верхним, и переснимите список. Если листали правильно — экран игры выглядит непривычно для проверки, и её предупреждение можно не учитывать."))));
  }
  if (joins.state === "unknown") {
    return h("div", { class: "sub joins" },
      tn("Не удалось сверить # пару соседних снимков ({0}): они разного размера. Остальные стыкуются.|Не удалось сверить # пары соседних снимков ({0}): они разного размера. Остальные стыкуются.|Не удалось сверить # пар соседних снимков ({0}): они разного размера. Остальные стыкуются.",
        joins.unknown.length, joins.unknown.map((u) => t("№{0} и №{1}", shotNumber(files, u.after), shotNumber(files, u.before))).join(", ")));
  }
  return null;
}

const FILE_STATE = { queued: t("в очереди"), reading: t("читаю…"), done: t("прочитан"), error: t("ошибка") };
function jobProgress(job) {
  return h("div", null,
    h("div", { class: "bar-track" }, h("div", { class: "bar-fill", style: `width:${job.total ? Math.round(job.done / job.total * 100) : 0}%` })),
    h("ul", { class: "joblist" }, job.files.map((f) => h("li", { class: "job-" + f.state },
      f.state === "reading" ? icon("refresh", "spin") : f.state === "done" ? icon("check") : f.state === "error" ? icon("alert") : h("span", { class: "ico" }),
      h("span", { class: "grow" }, f.name),
      h("span", { class: "sub" }, f.state === "done" ? tn("# часть|# части|# частей", f.parts) : f.state === "error" ? f.error : FILE_STATE[f.state] || "")))),
    h("div", { class: "actions" },
      h("button", { class: "btn ghost", onclick: () => recognizeAction("/api/recognize/cancel") }, t("Отмена")),
      h("span", { class: "sub" }, t("Прочитано {0} из {1}, обычно несколько секунд на скриншот. Окно можно свернуть или закрыть: результат сохранится и будет ждать вас здесь.", job.done, job.total))));
}

function reviewBlock(job) {
  const mode = R.mode || job.suggested;
  const rep = job.reports[mode];
  const unmatched = rep.review.filter((r) => r.kind === "unmatched");
  const checks = rep.review.filter((r) => r.kind !== "unmatched");
  const failed = job.files.filter((f) => f.state === "error");
  const marks = rep.mastery ? rep.mastery.applied : [];
  const box = h("div", { class: "review" });
  const joins = R.state.joins;
  const broken = joins && joins.available && (joins.state === "gaps" || joins.state === "unsure");
  const partial = endsNotes(joins, R.state.files, true, mode);
  box.append(h("div", { class: "review-head" },
    h("b", null, tn("Прочитано: # разная часть, всего {0} шт.|Прочитано: # разные части, всего {0} шт.|Прочитано: # разных частей, всего {0} шт.", rep.distinct_parts, rep.total_parts)),
    h("span", { class: "sub" }, t("за {0} с", job.seconds))));
  box.append(h("div", { class: "modes" },
    [["replace", t("Это весь мой список"), t("Частей, которых нет на скриншотах, в инвентаре не останется.")],
     ["merge", t("Только добавить и обновить"), t("Остальные части в инвентаре сохранятся как есть.")]].map(([value, title, text]) => {
      const r = job.reports[value];
      return h("button", { class: "mode", "aria-pressed": String(mode === value), onclick: () => { R.mode = value; renderDialog(); } },
        h("b", null, title), h("span", { class: "sub" }, text),
        h("span", { class: "sub num" }, [t("новых {0}", r.added), t("изменится {0}", r.changed), value === "replace" ? t("исчезнет {0}", r.removed) : null].filter(Boolean).join(" · ")));
    })));
  if (broken) {
    box.append(h("div", { class: "callout bad" }, icon("alert"), h("div", null,
      h("b", null, joins.state === "unsure" ? t("Соседние снимки не стыкуются ни в одной паре") : t("Похоже, при прокрутке пропущен ряд")),
      joins.state === "gaps" ? h("div", null, t("Список не стыкуется:")) : null,
      joins.state === "gaps" ? gapLines(joins, R.state.files) : null,
      h("div", { class: "gap-how" }, mode === "replace"
        ? t("Части из пропущенного ряда не прочитаны. В режиме «Это весь мой список» они исчезнут из инвентаря — безопаснее «Только добавить и обновить».")
        : t("Части из пропущенного ряда не прочитаны, поэтому выбран режим «Только добавить и обновить»: в нём они останутся в инвентаре как были.")),
      h("div", { class: "gap-how" }, t("Надёжнее всего — «Не заносить», доснять это место в игре (F6) и распознать заново.")))));
  }
  if (partial.length) box.append(...partial);
  if (rep.refused) box.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
    t("На снимках разных частей: {0}, а из инвентаря при этом исчезнет {1}: похоже, скриншоты покрывают не весь список. Если это только часть инвентаря, выберите «Только добавить и обновить». Кнопка «Всё равно заменить» оставит в инвентаре лишь то, что есть на снимках.", rep.distinct_parts, rep.removed))));
  if (mode === "replace" && rep.removed_list && rep.removed_list.length) {
    box.append(h("details", { class: "review-sec", open: rep.removed_list.length <= 12 || broken || partial.length > 0 },
      h("summary", null, tn("Исчезнут из инвентаря: # часть|Исчезнут из инвентаря: # части|Исчезнут из инвентаря: # частей", rep.removed)),
      h("div", { class: "sub" }, t("Их нет ни на одном снимке. Если вы их не продавали и не строили — возможно, пропущен экран или ряд.")),
      h("ul", null, rep.removed_list.map((r) => h("li", null, `${r.item} ×${r.count}`)),
        rep.removed > rep.removed_list.length ? h("li", { class: "sub" }, t("…и ещё {0}", rep.removed - rep.removed_list.length)) : null)));
  }
  if (failed.length) box.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
    t("Не прочитано скриншотов: {0} ({1}). Их части в список не попали.", failed.length, failed.map((f) => f.name).join(", ")))));
  if (unmatched.length >= 3 && unmatched.length * 2 >= unmatched.length + rep.matched.length) {
    box.append(h("div", { class: "callout" }, icon("alert"), h("div", null,
      h("div", null, t("Большинство названий не нашлось в каталоге. Если Warframe у вас включена не на том языке, что выбран в настройках, укажите там «Язык игры»: названия сопоставятся заново, перечитывать снимки не придётся.")),
      h("div", { class: "actions" }, h("button", { class: "btn subtle", onclick: () => openSettingsDialog() }, t("Открыть настройки"))))));
  }
  // A doubtful line is shown with the tile it was read from (when the place of the tile is known) and can
  // be put right at once: another number, the part it really is, or "leave it out".
  const fix = (payload) => recognizeAction("/api/recognize/fix", payload);
  const tilePic = (r) => (r.pos && r.shot ? h("button", { class: "tile-pic", title: t("Плитка, с которой прочитана эта строка. Нажмите, чтобы открыть весь снимок."), onclick: () => zoomShot(r.shot) },
    h("img", { src: `/api/tile?name=${encodeURIComponent(r.shot)}&row=${r.pos[0]}&col=${r.pos[1]}`, alt: "", loading: "lazy" })) : null);
  const line = (r, text, note, controls) => h("li", { class: "rev-line" }, tilePic(r),
    h("div", { class: "rev-text" }, h("div", null, text), note ? h("div", { class: "sub" }, note) : null,
      controls && controls.length ? h("div", { class: "rev-fix" }, controls) : null));
  if (unmatched.length) box.append(h("div", { class: "review-sec" }, h("b", null, t("Не нашлось в каталоге: {0}", unmatched.length)),
    h("ul", { class: "rev-list" }, unmatched.map((r) => line(r, `${quoted(r.name)} ×${r.count}`, r.note || "",
      r.entry == null ? [] : (r.suggestions || []).map((x) => h("button", { class: "btn subtle", title: t("Занести эту строку как «{0}»", x.item),
        onclick: () => fix({ entry: r.entry, slug: x.slug }) }, t("Это {0}", x.item))))))));
  if (checks.length) box.append(h("div", { class: "review-sec" }, h("b", null, t("Стоит проверить: {0}", checks.length)),
    h("ul", { class: "rev-list" }, checks.map((r) => line(r, `${quoted(r.name)} → ${r.item || ""} ×${r.count}`, r.note || "",
      r.entry == null || r.kind !== "check" ? [] : [
        h("label", { class: "rev-count" }, h("span", { class: "sub" }, t("Количество")),
          h("input", { class: "num-input small num", type: "number", min: "1", max: "9999", value: String(r.count), "aria-label": t("Количество"),
            onchange: (e) => { const n = Math.round(Number(e.target.value)); if (n >= 1) fix({ entry: r.entry, count: n }); } })),
        h("button", { class: "btn subtle", title: t("Название и количество прочитаны верно: больше не спрашивать об этой строке"),
          onclick: () => fix({ entry: r.entry, slug: r.slug, count: r.count }) }, icon("check"), t("Верно")),
        h("button", { class: "btn subtle", title: t("Не заносить эту строку в инвентарь"), onclick: () => fix({ entry: r.entry, skip: true }) }, t("Не заносить"))])))));
  if (marks.length || job.dropped_negative_marks) {
    const by = (state) => marks.filter((m) => m.state === state);
    const notMastered = by("none");
    box.append(h("div", { class: "review-sec" }, h("b", null, t("Отметки освоения: {0}", marks.length)),
      marks.length ? h("div", { class: "sub" }, t("освоено — {0}, есть в арсенале — {1}, не освоено — {2}", by("mastered").length, by("owned").length, notMastered.length)) : null,
      notMastered.length ? h("div", { class: "sub" }, t("Не освоено: {0}", notMastered.map((m) => m.item).join(", "))) : null,
      job.dropped_negative_marks ? h("div", { class: "sub" },
        t("Отметок «не освоено» пропущено: {0}. На этих скриншотах ни разу не встретилась надпись «Освоено», поэтому неясно, показывает ли её этот экран.", job.dropped_negative_marks)) : null));
  }
  if (job.notes && job.notes.length) box.append(h("details", { class: "review-sec" },
    h("summary", null, t("Заметки распознавания: {0}", job.notes.length)),
    h("ul", null, job.notes.map((n) => h("li", { class: "sub" }, n)))));
  box.append(h("div", { class: "review-sec" },
    h("button", { class: "link", onclick: () => { R.showAll = !R.showAll; renderDialog(); } }, R.showAll ? t("Скрыть список") : t("Показать всё прочитанное ({0})", rep.matched.length)),
    R.showAll ? h("div", { class: "table-view" }, h("table", null,
      h("thead", null, h("tr", null, h("th", null, t("На скриншоте")), h("th", null, t("В каталоге")), h("th", null, t("Шт.")))),
      h("tbody", null, rep.matched.map((m) => h("tr", null, h("td", null, m.name), h("td", { style: "text-align:left" }, m.item), h("td", null, String(m.count))))))) : null));
  box.append(h("div", { class: "actions" },
    h("button", { class: "btn primary", disabled: rep.distinct_parts === 0 && !marks.length,
      onclick: async () => {
        const res = await recognizeAction("/api/recognize/apply", { mode, force: Boolean(rep.refused) });
        if (res && res.ok) {
          R.mode = null; R.showAll = false;
          S.data = res.overview; S.parts.clear();
          render(); queueMarket(false);
          $("#dlg-update").close();
          toast(t("Инвентарь обновлён"));
        }
      } }, rep.refused ? t("Всё равно заменить") : t("Занести в инвентарь")),
    h("button", { class: "btn ghost", onclick: () => { R.mode = null; R.showAll = false; recognizeAction("/api/recognize/dismiss"); } }, t("Не заносить"))));
  return box;
}

/* Shooting with a second pair of eyes (primesets/live.py): while it is on, the app takes every new F6
   screenshot from the game's folder by itself, checks at once that it continues the previous one and
   says so with a sound -- the user stays in the game and learns about a skipped row in a second. */
const LIVE = { sound: true };
try { LIVE.sound = localStorage.getItem("primesets-live-sound") !== "0"; } catch (e) { /* ignore */ }
function liveBlock(live, files) {
  if (!live.on) {
    return h("div", { class: "live" },
      h("div", { class: "live-text" }, h("b", null, t("Съёмка с подсказками")),
        h("div", { class: "sub" }, t("Включите и переходите в игру: после каждого F6 программа сама заберёт снимок и проверит, стыкуется ли он с предыдущим. Короткий сигнал — всё в порядке, три низких — пропущен ряд: вернитесь на один экран и нажмите F6 ещё раз."))),
      h("div", { class: "live-side" },
        h("button", { class: "btn primary", onclick: () => recognizeAction("/api/live", { on: true, sound: LIVE.sound }) }, t("Включить подсказки")),
        h("label", { class: "check-line" },
          h("input", { type: "checkbox", checked: LIVE.sound, onchange: (e) => { LIVE.sound = e.target.checked; remember("primesets-live-sound", LIVE.sound ? 1 : 0); } }),
          h("span", null, t("со звуком")))));
  }
  let text = t("Жду первый снимок: откройте в игре «Инвентарь → Продать» и нажимайте F6 на каждом экране.");
  let cls = "";
  if (live.signal === "gap") {
    const g = live.gap;
    const where = g ? t(" Не стыкуются снимки {0} и {1}.", shotNo(shotNumber(files, g.after)), shotNo(shotNumber(files, g.before))) : "";
    text = t("Пропущен ряд: вернитесь в игре на один экран назад и нажмите F6 ещё раз.") + where;
    cls = " bad";
  } else if (live.signal === "end") text = t("Конец списка снят. Можно выключать подсказки и распознавать.");
  else if (live.signal === "other") text = t("Последний снимок — другой экран, не список частей. Он тоже добавлен.");
  else if (live.signal === "ok") text = live.gap ? t("Снимок принят, но выше остался разрыв: посмотрите на отмеченные снимки.") : t("Последний снимок стыкуется с предыдущим — листайте дальше.");
  return h("div", { class: "live on" + cls },
    h("span", { class: "live-dot", "aria-hidden": "true" }),
    h("div", { class: "live-text" },
      h("b", null, live.taken ? tn("Подсказки включены: принят # снимок|Подсказки включены: принято # снимка|Подсказки включены: принято # снимков", live.taken) : t("Подсказки включены")),
      h("div", { class: "sub" }, text)),
    h("div", { class: "live-side" },
      h("button", { class: "btn ghost", onclick: () => recognizeAction("/api/live", { on: false }) }, t("Выключить подсказки"))));
}

function renderDialog() {
  const dlg = $("#dlg-update");
  if (!dlg.open || !R.state) return;
  const { job, files } = R.state;
  const provider = R.state.provider || { id: "", kind: "", ready: false, reason: "error", error: "" };
  const joins = R.state.joins || null;        // absent when the page talks to an older running copy of the app
  const running = job && job.state === "running";
  const picker = h("input", { type: "file", accept: "image/*", multiple: true, hidden: true,
    onclick: (e) => e.stopPropagation(), onchange: async (e) => { await uploadScreenshots(e.target.files); refreshRecognize(false); } });
  const drop = h("div", { class: "drop", role: "button", tabindex: "0",
    onclick: () => picker.click(),
    onkeydown: (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); picker.click(); } },
    ondragover: (e) => { e.preventDefault(); drop.classList.add("over"); },
    ondragleave: () => drop.classList.remove("over"),
    ondrop: async (e) => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("over"); await uploadScreenshots(e.dataTransfer.files); refreshRecognize(false); },
  }, h("b", null, t("Вставьте из буфера — Ctrl+V")), h("span", null, t("или перетащите файлы сюда, или нажмите, чтобы выбрать")), picker);

  // the game's own F6 screenshots: picked up from its folder, no pasting needed
  const game = R.state.game || { new: 0, exists: false, dir: "" };
  const live = R.state.live || { on: false, available: false };
  const idle = !running && !(job && job.state === "review");
  const liveBox = idle && live.available ? liveBlock(live, files) : null;
  let fromGame = null;
  if (idle && !live.on) {
    fromGame = game.new > 0
      ? h("div", { class: "from-game" },
          h("div", null, h("b", null, tn("В папке игры # новый скриншот|В папке игры # новых скриншота|В папке игры # новых скриншотов", game.new)),
            h("div", { class: "sub" }, t("сделаны клавишей F6") + " · " + game.dir)),
          h("button", { class: "btn primary", onclick: () => recognizeAction("/api/screenshots/from-game") }, t("Добавить")),
          h("button", { class: "btn subtle", title: t("Не предлагать эти снимки"), onclick: () => recognizeAction("/api/screenshots/from-game", { skip: true }) }, t("Пропустить")))
      : h("div", { class: "sub tip" }, t("Проще всего: в игре нажимайте F6 на каждом экране списка — снимки сохранятся сами и появятся здесь, вставлять ничего не нужно."));
  }

  let work;
  if (running) work = jobProgress(job);
  else if (job && job.state === "review") work = reviewBlock(job);
  else {
    const count = files.length;
    work = h("div", null,
      job && job.state === "error" && job.error_code !== "login" ? h("div", { class: "callout" }, icon("alert"), h("div", null, job.error)) : null,
      providerLine(provider),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", disabled: !count || !provider.ready,
          onclick: () => { R.mode = null; recognizeAction("/api/recognize/start"); } },
          icon("image"), count ? tn("Распознать # скриншот|Распознать # скриншота|Распознать # скриншотов", count) : t("Распознать")),
        !count ? h("span", { class: "sub" }, t("Сначала добавьте скриншоты.")) : null));
  }

  const scroll = dlg.querySelector(".dlg-body") ? dlg.querySelector(".dlg-body").scrollTop : 0;
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, t("Обновить инвентарь")),
      h("button", { class: "btn ghost icon-only", "aria-label": t("Закрыть"), onclick: () => dlg.close() }, icon("close"))),
    h("div", { class: "dlg-body" },
      h("ol", { class: "steps" },
        h("li", null, h("div", null,
          h("h3", null, t("Скриншоты из игры")),
          h("p", null, t("Инвентарь → «Продать» → категория «Прайм части» (или поиск «прайм»). Нажимайте F6 на каждом экране и листайте по три ряда: обрезанный нижний ряд должен стать верхним. Курсор держите справа от списка. Кузница нужна только ради отметок «Освоено» — её достаточно снять один раз.")),
          liveBox,
          fromGame,
          running || (job && job.state === "review") ? null : drop,
          fileGrid(files, running || (job && job.state === "review"), joins),
          job && job.state === "review" ? null : joinsBlock(joins, files),
          running || !files.length ? null : h("div", { class: "actions" },
            h("button", { class: "btn subtle", onclick: () => post("/api/open-folder", { which: "screenshots" }).catch((e) => toast(e.message)) }, icon("folder"), t("Открыть папку")),
            job && job.state === "review" ? null : h("button", { class: "btn subtle", onclick: () => recognizeAction("/api/screenshots/remove", { all: true }) }, t("Убрать все"))))),
        h("li", null, h("div", null, h("h3", null, running ? t("Читаю скриншоты") : job && job.state === "review" ? t("Проверьте и занесите") : t("Распознавание")), work))),
      h("p", { class: "foot" }, t("Приложение не подключается к игре: оно видит только те картинки, которые вы сюда положили."))));
  const zoomed = lightbox(files);
  if (zoomed) dlg.append(zoomed);
  dlg.querySelector(".dlg-body").scrollTop = scroll;
}
async function openUpdateDialog() {
  const dlg = $("#dlg-update");
  if (!dlg.open) {
    dlg.replaceChildren(h("div", { class: "dlg-head" }, h("h2", null, t("Обновить инвентарь"))),
      h("div", { class: "dlg-body" }, h("span", { class: "skeleton", style: "width:100%;height:120px" })));
    dlg.showModal();
  }
  await refreshRecognize(false);
}

// ----------------------------------------------------------------- settings: language and who reads the screenshots
// Every user connects their own account: a subscription sign-in in a program on this computer, or
// their own API key.  Keys are typed here by the user and never come back from the server.
const SET = { data: null, error: "", busy: false, check: {}, keyOpen: new Set(), proxyOpen: false, loginUntil: 0, timer: 0 };
const KEY_PAGES = {
  anthropic_api: "https://console.anthropic.com/settings/keys",
  openai_api: "https://platform.openai.com/api-keys",
  deepseek_api: "https://platform.deepseek.com/api_keys",
  gemini_api: "https://aistudio.google.com/apikey",
};
const REASON = { no_cli: t("программа не найдена"), login: t("нужен вход"), no_key: t("нужен ключ"), no_sdk: t("нет библиотеки"), error: t("ошибка") };

async function loadSettings(force) {
  try { SET.data = await api("/api/settings" + (force ? "?refresh=1" : "")); SET.error = ""; }
  catch (err) { SET.error = err.message; }
  renderSettings();
  clearTimeout(SET.timer);
  const chosen = SET.data && SET.data.providers.find((p) => p.id === SET.data.provider);
  // after "Войти" keep checking for a few minutes, so the dialog notices the finished sign-in by itself
  if ($("#dlg-settings").open && Date.now() < SET.loginUntil && chosen && chosen.kind === "subscription" && !chosen.ready) {
    SET.timer = setTimeout(() => loadSettings(true), 4000);
  }
}
async function settingsCall(path, payload) {
  if (SET.busy) return null;
  SET.busy = true;
  try {
    const res = await post(path, payload);
    if (res && res.providers) SET.data = res;
    return res;
  } catch (err) {
    toast(err.message);
    return null;
  } finally {
    SET.busy = false;
    renderSettings();
  }
}
async function saveSettings(patch) {
  const res = await settingsCall("/api/settings", patch);
  if (!res) return;
  if (res.reload) {
    // another language: the page is drawn anew, and the dialog comes back where the user left it
    try { sessionStorage.setItem("primesets-open-settings", "1"); } catch (e) { /* ignore */ }
    location.reload();
    return;
  }
  if ("game_language" in patch) loadOverview();        // the catalog now carries the names of the other client
  if ($("#dlg-update").open) refreshRecognize(true);
}
async function checkProvider(p) {
  SET.check[p.id] = { state: "loading" };
  renderSettings();
  let res;
  try { res = await post("/api/settings/check", { provider: p.id }); }
  catch (err) { res = { ok: false, message: err.message, models: [] }; }
  SET.check[p.id] = Object.assign({ state: "done" }, res);
  await loadSettings(true);
  if ($("#dlg-update").open) refreshRecognize(true);
}

function field(label, ...kids) {
  return h("div", { class: "field" }, h("span", { class: "field-label" }, label), h("div", { class: "field-body" }, kids));
}
function keyRow(p) {
  if (p.has_key && !SET.keyOpen.has(p.id)) {
    return field(t("API-ключ"),
      h("span", { class: "key-saved" }, icon("lock"), p.key_source === "env" ? t("взят из переменной окружения ({0})", p.key_hint) : t("сохранён ({0})", p.key_hint)),
      h("button", { class: "btn subtle", onclick: () => { SET.keyOpen.add(p.id); renderSettings(); } }, t("Заменить")),
      p.key_source === "saved" ? h("button", { class: "btn subtle", disabled: SET.busy,
        onclick: async () => { delete SET.check[p.id]; await settingsCall("/api/settings/key", { provider: p.id, key: "" }); if ($("#dlg-update").open) refreshRecognize(true); } }, t("Удалить")) : null);
  }
  const input = h("input", { class: "input", type: "password", autocomplete: "off", spellcheck: "false", "data-keep": "key-" + p.id,
    placeholder: t("Вставьте сюда свой ключ"), "aria-label": t("API-ключ") });
  const save = async () => {
    const key = input.value.trim();
    if (!key) { toast(t("Сначала вставьте ключ в поле.")); return; }
    input.value = "";
    const res = await settingsCall("/api/settings/key", { provider: p.id, key });
    if (!res) return;
    SET.keyOpen.delete(p.id);
    delete SET.check[p.id];
    renderSettings();
    if ($("#dlg-update").open) refreshRecognize(true);
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
  return field(t("API-ключ"), input,
    h("button", { class: "btn primary", disabled: SET.busy, onclick: save }, t("Сохранить")),
    p.has_key ? h("button", { class: "btn subtle", onclick: () => { SET.keyOpen.delete(p.id); renderSettings(); } }, t("Отмена")) : null,
    KEY_PAGES[p.id] ? h("div", { class: "sub field-note" }, tx("Ключ создаётся в личном кабинете сервиса: {0}. Он хранится только на этом компьютере, в зашифрованном виде.",
      h("a", { class: "link", href: KEY_PAGES[p.id], target: "_blank", rel: "noopener" }, KEY_PAGES[p.id].replace("https://", "")))) : null);
}
function modelRow(p) {
  const checked = SET.check[p.id] && SET.check[p.id].models ? SET.check[p.id].models : [];
  const names = [...new Set([p.model, p.default_model, ...p.models, ...checked].filter(Boolean))];
  if (!names.length) return field(t("Модель"), h("span", { class: "sub" }, t("та, что выбрана в самой программе")));
  const own = Boolean(p.model) && p.model !== p.default_model;
  return field(t("Модель"),
    h("select", { class: "select", disabled: SET.busy, "aria-label": t("Модель"),
      onchange: (e) => saveSettings({ models: { [p.id]: e.target.value === p.default_model ? "" : e.target.value } }) },
      names.map((name) => h("option", { value: name, selected: name === (p.model || p.default_model) },
        name === p.default_model ? t("{0} (по умолчанию)", name) : name))),
    own ? null : h("span", { class: "sub" }, p.kind === "api" ? t("Список моделей вашего ключа появится после проверки.") : ""));
}
function checkRow(p) {
  const c = SET.check[p.id];
  const button = h("button", { class: "btn subtle", disabled: Boolean(c && c.state === "loading"), onclick: () => checkProvider(p) },
    icon("refresh", c && c.state === "loading" ? "spin" : ""), t("Проверить подключение"));
  let result = null;
  if (c && c.state === "done") {
    result = c.ok ? h("div", { class: "sub ok-line" }, icon("check"), c.message)
      : h("div", { class: "callout" }, icon("alert"), h("div", null, c.message));
  }
  return h("div", { class: "prov-check" }, h("div", { class: "actions" }, button), result);
}
function providerBody(p, meta) {
  const d = SET.data, rows = [];
  if (p.kind === "subscription") {
    if (p.ready) {
      rows.push(h("div", { class: "sub ok-line" }, icon("check"), t("Вход выполнен: скриншоты читаются по вашей подписке.")));
    } else if (p.reason === "login") {
      rows.push(h("div", { class: "callout" }, icon("alert"), h("div", null,
        h("div", null, t("Нужен разовый вход в {0} — своим аккаунтом. Откроется окно с командой входа и браузер; пароль приложение не видит.", meta.title)),
        h("div", { class: "actions" },
          h("button", { class: "btn primary", disabled: SET.busy, onclick: async () => {
            SET.loginUntil = Date.now() + 5 * 60000;
            await settingsCall("/api/settings/login", { provider: p.id });
            loadSettings(true);
          } }, meta.login || t("Войти"))))));
    } else if (p.reason === "no_cli") {
      rows.push(h("div", { class: "callout" }, icon("alert"), h("div", null, meta.missing || "")));
    } else {
      rows.push(h("div", { class: "callout" }, icon("alert"), h("div", null, p.error || t("Не удалось проверить подключение."))));
    }
  } else {
    if (p.reason === "no_sdk") {
      rows.push(h("div", { class: "callout" }, icon("alert"), h("div", null, t("Для Claude API нужна библиотека anthropic: выполните «pip install anthropic» или пользуйтесь готовым exe."))));
    }
    if (d.vault || p.has_key) rows.push(keyRow(p));
    else rows.push(h("div", { class: "callout" }, icon("alert"), h("div", null, t("На этой системе нет защищённого хранилища для ключа. Задайте ключ переменной окружения."))));
    if (p.id === "deepseek_api") rows.push(h("div", { class: "sub" }, t("API DeepSeek не умеет строго задавать формат ответа: приложение проверяет ответ само, но ошибок чтения может быть больше, чем у других.")));
  }
  rows.push(modelRow(p));
  if (p.kind === "api") {
    const url = h("input", { class: "input", type: "text", autocomplete: "off", spellcheck: "false", "data-keep": "url-" + p.id,
      value: p.base_url || "", placeholder: p.default_base_url || "", "aria-label": t("Адрес API") });
    rows.push(h("details", { class: "prov-more" }, h("summary", null, t("Дополнительно")),
      field(t("Адрес API"), url,
        h("button", { class: "btn subtle", disabled: SET.busy, onclick: () => saveSettings({ base_urls: { [p.id]: url.value.trim() } }) }, t("Сохранить")),
        h("div", { class: "sub field-note" }, t("Меняйте, только если пользуетесь совместимым шлюзом: ключ и скриншоты будут уходить на этот адрес. Пустое поле — адрес самого сервиса.")))));
  }
  if (d.proxy.set) {
    rows.push(h("label", { class: "check" },
      h("input", { type: "checkbox", checked: Boolean(p.use_proxy), disabled: SET.busy, onchange: (e) => saveSettings({ use_proxy: { [p.id]: e.target.checked } }) }),
      h("span", null, t("Подключаться через прокси"))));
  }
  rows.push(checkRow(p));
  return rows;
}
function providerCard(p) {
  const meta = PROVIDER[p.id] || { title: p.id, kind: "" };
  const chosen = SET.data.provider === p.id;
  const state = p.ready ? h("span", { class: "chip good" }, icon("check"), t("готово"))
    : h("span", { class: "chip" + (chosen ? " warn" : " quiet") }, REASON[p.reason] || REASON.error);
  const head = h("label", { class: "prov-head" },
    h("input", { type: "radio", name: "provider", checked: chosen, disabled: SET.busy, onchange: () => saveSettings({ provider: p.id }) }),
    h("span", { class: "prov-title" }, h("b", null, meta.title), h("span", { class: "sub" }, meta.kind)),
    state);
  return h("div", { class: "prov" + (chosen ? " chosen" : "") }, head, chosen ? h("div", { class: "prov-body" }, providerBody(p, meta)) : null);
}
function proxyRow() {
  const d = SET.data;
  const note = h("div", { class: "sub field-note" }, t("Нужен, только если сервис недоступен из вашей сети напрямую. Подходит HTTP-прокси вида http://логин:пароль@адрес:порт. Включается отдельно у каждого подключения."));
  if (d.proxy.set && !SET.proxyOpen) {
    return field(t("Прокси"),
      h("span", { class: "key-saved" }, icon("lock"), t("сохранён: {0}", d.proxy.hint)),
      h("button", { class: "btn subtle", onclick: () => { SET.proxyOpen = true; renderSettings(); } }, t("Изменить")),
      h("button", { class: "btn subtle", disabled: SET.busy, onclick: () => settingsCall("/api/settings/proxy", { url: "" }) }, t("Удалить")),
      note);
  }
  const input = h("input", { class: "input", type: "text", autocomplete: "off", spellcheck: "false", "data-keep": "proxy",
    placeholder: "http://", "aria-label": t("Прокси") });
  const save = async () => {
    const url = input.value.trim();
    if (!url) { toast(t("Сначала введите адрес прокси.")); return; }
    const res = await settingsCall("/api/settings/proxy", { url });
    if (res) { input.value = ""; SET.proxyOpen = false; renderSettings(); }
  };
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); save(); } });
  return field(t("Прокси (необязательно)"), input,
    h("button", { class: "btn subtle", disabled: SET.busy, onclick: save }, t("Сохранить")),
    d.proxy.set ? h("button", { class: "btn subtle", onclick: () => { SET.proxyOpen = false; renderSettings(); } }, t("Отмена")) : null,
    note);
}
function renderSettings() {
  const dlg = $("#dlg-settings");
  if (!dlg.open) return;
  // what the user is typing survives a redraw
  const typed = new Map();
  let focused = null;
  dlg.querySelectorAll("[data-keep]").forEach((el) => { typed.set(el.dataset.keep, el.value); if (el === document.activeElement) focused = el.dataset.keep; });
  const opened = new Set([...dlg.querySelectorAll("details[open]")].map((el) => el.dataset.id));
  const body = h("div", { class: "dlg-body" });
  const d = SET.data;
  if (!d) {
    body.append(SET.error ? h("div", { class: "callout" }, icon("alert"), h("div", null, SET.error))
      : h("span", { class: "skeleton", style: "width:100%;height:220px" }));
  } else {
    const subs = d.providers.filter((p) => p.kind === "subscription"), apis = d.providers.filter((p) => p.kind === "api");
    body.append(
      h("section", { class: "set-sec" }, h("h3", null, t("Язык")),
        field(t("Язык интерфейса"),
          h("select", { class: "select", disabled: SET.busy, "aria-label": t("Язык интерфейса"), onchange: (e) => saveSettings({ language: e.target.value }) },
            d.languages.map((l) => h("option", { value: l.code, selected: l.code === d.language }, l.name)))),
        field(t("Язык игры"),
          h("select", { class: "select", disabled: SET.busy, "aria-label": t("Язык игры"), onchange: (e) => saveSettings({ game_language: e.target.value }) },
            h("option", { value: "", selected: !d.game_language }, t("Как язык интерфейса")),
            d.languages.map((l) => h("option", { value: l.code, selected: l.code === d.game_language }, l.name))),
          h("div", { class: "sub field-note" }, t("Язык, на котором включена Warframe: на нём написаны названия на ваших скриншотах.")))),
      h("section", { class: "set-sec" }, h("h3", null, t("Распознавание скриншотов")),
        h("p", { class: "sub" }, t("Скриншоты читает нейросеть. Выберите, как к ней подключиться: по своей подписке или по своему API-ключу. Приложение работает только с вашим собственным аккаунтом и никому его не передаёт.")),
        h("div", { class: "prov-group" }, h("b", null, t("По подписке")),
          h("span", { class: "sub" }, t("Нужна программа на этом компьютере и вход в неё своим аккаунтом. Расходуются лимиты вашей подписки."))),
        subs.map(providerCard),
        h("div", { class: "prov-group" }, h("b", null, t("По API-ключу")),
          h("span", { class: "sub" }, t("Нужен ключ из личного кабинета сервиса. Запросы оплачиваются по его тарифам."))),
        apis.map(providerCard),
        d.vault ? proxyRow() : null),
      h("section", { class: "set-sec" }, h("h3", null, t("Данные и приватность")),
        h("p", { class: "sub" }, t("Скриншоты отправляются только выбранному сервису распознавания. Ключи и адрес прокси хранятся на этом компьютере, зашифрованные под вашей учётной записью Windows; на страницу и в журнал они не попадают.")),
        field(t("Папка с данными"), h("span", { class: "path" }, d.data_dir),
          h("button", { class: "btn subtle", onclick: () => post("/api/open-folder", { which: "data" }).catch((e) => toast(e.message)) }, icon("folder"), t("Открыть"))),
        d.homepage ? h("label", { class: "check-line top" },
          h("input", { type: "checkbox", checked: d.check_updates !== false, disabled: SET.busy, onchange: (e) => saveSettings({ check_updates: e.target.checked }) }),
          h("span", null, t("Сообщать о новой версии"),
            h("div", { class: "sub" }, t("При запуске программа один раз спрашивает страницу проекта на GitHub, какая версия последняя. Ничего не скачивается и не устанавливается.")))) : null,
        h("p", { class: "sub" }, t("Версия {0}. Приложение не связано с Digital Extremes и warframe.market и не подключается к игре.", d.version),
          " ", h("a", { class: "link", href: "/licenses", target: "_blank", rel: "noopener" }, t("Лицензии")),
          d.homepage ? " · " : null,
          d.homepage ? h("a", { class: "link", href: d.homepage, target: "_blank", rel: "noopener" }, t("Страница проекта")) : null)));
  }
  const prev = dlg.querySelector(".dlg-body");
  const scroll = prev ? prev.scrollTop : 0;
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, t("Настройки")),
      h("button", { class: "btn ghost icon-only", "aria-label": t("Закрыть"), onclick: () => dlg.close() }, icon("close"))),
    body);
  dlg.querySelectorAll("details.prov-more").forEach((el, i) => { el.dataset.id = "more-" + i; if (opened.has(el.dataset.id)) el.open = true; });
  dlg.querySelectorAll("[data-keep]").forEach((el) => {
    if (typed.has(el.dataset.keep) && typed.get(el.dataset.keep)) el.value = typed.get(el.dataset.keep);
    if (el.dataset.keep === focused) el.focus();
  });
  body.scrollTop = scroll;
}
async function openSettingsDialog() {
  const dlg = $("#dlg-settings");
  if (!dlg.open) {
    // one dialog at a time: the settings can be reached from the dialog of the screenshots
    const other = $("#dlg-update");
    SET.back = other.open;
    if (other.open) other.close();
    dlg.showModal();
    renderSettings();
  }
  await loadSettings(false);
}

// ----------------------------------------------------------------- the first start
/* Three short steps for someone who sees the program for the first time: the language, who will read
   the screenshots, how to shoot the inventory -- and a way to look at the program on a made-up
   inventory before adding one's own. */
const WELCOME = { step: 0 };
try { WELCOME.step = Math.min(2, Math.max(0, Number(sessionStorage.getItem("primesets-welcome-step")) || 0)); } catch (e) { /* ignore */ }
async function finishWelcome(then) {
  const dlg = $("#dlg-welcome");
  if (S.data) S.data.welcomed = true;
  try { sessionStorage.removeItem("primesets-welcome-step"); } catch (e) { /* ignore */ }
  if (dlg.open) dlg.close();
  try { await post("/api/settings", { welcomed: true }); } catch (e) { /* the guide will simply come up once more */ }
  if (typeof then === "function") then();
}
function renderWelcome() {
  const dlg = $("#dlg-welcome");
  if (!dlg.open) return;
  const step = WELCOME.step, d = SET.data;
  const go = (n) => {
    WELCOME.step = n;
    try { sessionStorage.setItem("primesets-welcome-step", String(n)); } catch (e) { /* ignore */ }
    renderWelcome();
  };
  let title, content;
  if (step === 0) {
    title = t("Добро пожаловать");
    const setLanguage = async (patch) => {
      try {
        const res = await post("/api/settings", patch);
        if (res.reload) { location.reload(); return; }        // another language: the page is drawn anew, the guide comes back
        SET.data = res;
        if ("game_language" in patch) loadOverview();
      } catch (err) { toast(err.message); }
      renderWelcome();
    };
    content = [
      h("p", null, t("По скриншотам ваших прайм-частей программа покажет, какие комплекты уже собраны, сколько они стоят на warframe.market и чего не хватает до следующих. К игре она не подключается: работает с картинками, которые вы сделали сами.")),
      field(t("Язык интерфейса"), h("select", { class: "select", "aria-label": t("Язык интерфейса"), onchange: (e) => setLanguage({ language: e.target.value }) },
        I18N.languages.map((l) => h("option", { value: l.code, selected: l.code === LANG }, l.name)))),
      d ? field(t("Язык игры"), h("select", { class: "select", "aria-label": t("Язык игры"), onchange: (e) => setLanguage({ game_language: e.target.value }) },
        h("option", { value: "", selected: !d.game_language }, t("Как язык интерфейса")),
        d.languages.map((l) => h("option", { value: l.code, selected: l.code === d.game_language }, l.name))),
      h("div", { class: "sub field-note" }, t("Язык, на котором включена Warframe: на нём написаны названия на ваших скриншотах."))) : null];
  } else if (step === 1) {
    title = t("Кто прочитает скриншоты");
    const cur = d ? d.providers.find((p) => p.id === d.provider) : null;
    const meta = cur ? PROVIDER[cur.id] || { title: cur.id } : null;
    content = [
      h("p", null, t("Названия и количество со скриншотов читает нейросеть — по вашей подписке (Claude Code, Codex) или по вашему API-ключу (Claude, OpenAI, DeepSeek, Gemini). Подключение настраивается один раз; аккаунт и ключ остаются на этом компьютере.")),
      !d ? h("span", { class: "skeleton", style: "width:100%;height:40px" })
        : cur && cur.ready ? h("div", { class: "sub ok-line" }, icon("check"), h("span", null, t("Подключение готово: {0}.", meta.title)))
          : h("div", { class: "callout" }, icon("alert"), h("div", null, t("Подключение пока не настроено. Это можно сделать сейчас или позже: программа напомнит, когда вы добавите скриншоты."))),
      h("div", { class: "actions" }, h("button", { class: "btn subtle", onclick: () => openSettingsDialog() }, icon("gear"), t("Настроить подключение")))];
  } else {
    title = t("Как снять инвентарь");
    content = [
      h("ol", { class: "welcome-list" },
        h("li", null, t("В игре откройте «Инвентарь» → «Продать» и выберите категорию «Прайм части».")),
        h("li", null, t("Нажимайте F6 на каждом экране и листайте по три ряда, пока список не кончится.")),
        h("li", null, t("Здесь нажмите «Обновить инвентарь»: снимки найдутся сами, останется их распознать."))),
      h("p", { class: "sub" }, t("Там же есть «Съёмка с подсказками»: программа проверяет каждый снимок, пока вы в игре, и звуком говорит, если пропущен ряд.")),
      h("div", { class: "actions" },
        h("button", { class: "btn primary", onclick: () => finishWelcome(openUpdateDialog) }, icon("image"), t("Добавить инвентарь")),
        h("button", { class: "btn ghost", onclick: () => finishWelcome(() => setDemo(true)) }, t("Посмотреть на примере")))];
  }
  dlg.replaceChildren(
    h("div", { class: "dlg-head" }, h("h2", null, title), closeButton(dlg)),
    h("div", { class: "dlg-body" }, content,
      h("div", { class: "welcome-foot" },
        h("span", { class: "welcome-dots", role: "img", "aria-label": t("Шаг {0} из {1}", step + 1, 3) }, [0, 1, 2].map((n) => h("span", { class: n === step ? "on" : "" }))),
        h("span", { class: "grow" }),
        step > 0 ? h("button", { class: "btn ghost", onclick: () => go(step - 1) }, t("Назад")) : null,
        step < 2 ? h("button", { class: "btn primary", onclick: () => go(step + 1) }, t("Далее")) : null)));
}
function openWelcome() {
  const dlg = $("#dlg-welcome");
  if (dlg.open) return;
  dlg.showModal();
  renderWelcome();
  loadSettings(false).then(renderWelcome);
}

// ----------------------------------------------------------------- theme
function currentTheme() {
  return document.documentElement.dataset.theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}
function renderThemeButton() {
  $("#btn-theme").replaceChildren(icon(currentTheme() === "dark" ? "sun" : "moon"));
}
$("#btn-theme").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("primesets-theme", next); } catch (e) { /* ignore */ }
  renderThemeButton();
});

// ----------------------------------------------------------------- boot
async function loadOverview() {
  try {
    S.data = await api("/api/overview");
  } catch (err) {
    if (!S.data) $("#inv-status").textContent = t("Не удалось получить данные: {0}", err.message);
    return;
  }
  // forget prices of sets that left the list
  const alive = new Set([...S.data.complete, ...S.data.partial].map((x) => x.slug));
  for (const slug of [...S.market.keys()]) if (!alive.has(slug)) S.market.delete(slug);
  render();
  queueMarket(false);
}

document.querySelectorAll("[data-ico]").forEach((el) => el.replaceWith(icon(el.dataset.ico)));
renderThemeButton();
$("#btn-update").addEventListener("click", openUpdateDialog);
$("#btn-history").addEventListener("click", openHistoryDialog);
$("#btn-settings").addEventListener("click", () => openSettingsDialog());
$("#dlg-settings").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
$("#dlg-settings").addEventListener("close", () => {
  clearTimeout(SET.timer);
  if (SET.back) { SET.back = false; openUpdateDialog(); }       // back to the screenshots the settings were opened from
});
for (const id of ["#dlg-history", "#dlg-listing", "#dlg-sellnow", "#dlg-goal", "#dlg-baro", "#dlg-sell"]) {
  $(id).addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
}
$("#dlg-baro").addEventListener("close", () => { if (BARO.queue.running) { BARO.queue.gen++; BARO.queue.running = false; } });
// the first-start guide closed in any way has been seen; the settings opened from it bring it up to date
$("#dlg-welcome").addEventListener("close", () => { if (S.data && !S.data.welcomed) finishWelcome(); });
$("#dlg-settings").addEventListener("close", () => { if ($("#dlg-welcome").open) loadSettings(true).then(renderWelcome); });
$("#dlg-history").addEventListener("close", renderChangesBanner);
$("#btn-prices").addEventListener("click", () => {
  if (S.tab === "ducats") { if (!D.queue.running) runDucatQueue(true); return; }
  S.parts.clear(); S.lite.clear(); queueMarket(true); toast(t("Запрашиваю свежие цены…"));
});
$("#search").addEventListener("input", (e) => { S.query = e.target.value; renderView(); });
$("#dlg-update").addEventListener("click", (e) => { if (e.target === e.currentTarget) e.currentTarget.close(); });
$("#dlg-update").addEventListener("close", () => { scheduleRecognizePoll(); checkPendingReading(); });
addEventListener("focus", () => {
  const job = R.state && R.state.job;
  if ($("#dlg-update").open && !(job && job.state === "running")) refreshRecognize(false);
});
// screenshots dropped anywhere on the window go to the inbox folder (and never replace the page)
addEventListener("dragover", (e) => { if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) e.preventDefault(); });
addEventListener("drop", async (e) => {
  if (!e.dataTransfer || !e.dataTransfer.files.length) return;
  e.preventDefault();
  if (await uploadScreenshots(e.dataTransfer.files)) openUpdateDialog();
});
// Ctrl+V anywhere in the window: a screenshot from the clipboard (PrintScreen, Win+Shift+S) or copied picture files
addEventListener("paste", async (e) => {
  const data = e.clipboardData;
  if (!data) return;
  let files = [...(data.files || [])];
  if (!files.length) files = [...(data.items || [])].filter((it) => it.kind === "file").map((it) => it.getAsFile()).filter(Boolean);
  files = files.filter((f) => /^image\//.test(f.type || "") || /\.(png|jpe?g|webp|bmp)$/i.test(f.name || ""));
  if (!files.length) return;                 // ordinary text paste: leave it to the focused field
  e.preventDefault();
  if (R.state && R.state.job && R.state.job.state === "running") { toast(t("Идёт распознавание — добавьте скриншот после него.")); return; }
  if (await uploadScreenshots(files)) openUpdateDialog();
});
document.addEventListener("click", (e) => {
  document.querySelectorAll(".add-box").forEach((box) => { if (!box.contains(e.target)) box.querySelector(".suggest").hidden = true; });
});

let lost = 0;
function connectEvents() {
  const es = new EventSource("/api/events");
  es.addEventListener("open", () => { lost = 0; $("#offline").hidden = true; });
  es.addEventListener("inventory", () => { S.parts.clear(); loadOverview().then(() => { toast(t("Инвентарь обновлён")); checkChanges(); }); });
  es.addEventListener("joins", () => { if ($("#dlg-update").open) refreshRecognize(false); });
  es.addEventListener("live", () => { if ($("#dlg-update").open) refreshRecognize(false); });
  es.addEventListener("update", () => loadOverview());
  es.addEventListener("catalog", (e) => {
    let info = {};
    try { info = JSON.parse(e.data); } catch (err) { /* ignore */ }
    if (S.data && info.building) { Object.assign(S.data.catalog, info); renderBanners(); }
    else loadOverview();
  });
  es.addEventListener("error", async () => {
    try { await api("/api/ping"); lost = 0; } catch (err) { if (++lost >= 3) $("#offline").hidden = false; }
  });
}
addEventListener("pagehide", () => { try { navigator.sendBeacon("/api/bye"); } catch (e) { /* ignore */ } });

async function checkPendingReading() {
  const banner = $("#pending-banner");
  try {
    const st = await api("/api/recognize");
    R.state = st;
    const job = st.job;
    if (job && job.state === "review" && !$("#dlg-update").open) {
      banner.replaceChildren(icon("image"),
        h("div", { class: "notice-body" },
          h("div", { class: "notice-title" }, t("Скриншоты прочитаны и ждут вашего решения: {0}", job.total)),
          h("div", { class: "notice-text" }, t("Результат сохранён. Посмотрите, что найдено, и занесите в инвентарь."))),
        h("button", { class: "btn primary", onclick: () => { banner.hidden = true; openUpdateDialog(); } }, t("Открыть")));
      banner.hidden = false;
      return;
    }
  } catch (err) { /* the dialog will report it when opened */ }
  banner.hidden = true;
}

let reopenSettings = startAt === "settings";
try {
  if (sessionStorage.getItem("primesets-open-settings")) { sessionStorage.removeItem("primesets-open-settings"); reopenSettings = true; }
} catch (e) { /* storage unavailable */ }
loadOverview().then(() => {
  checkPendingReading();
  checkChanges();
  // someone who has neither an inventory nor seen the guide gets the three first-start steps
  if (S.data && !S.data.welcomed && !S.data.demo && !S.data.inventory.distinct && !reopenSettings) openWelcome();
});
if (reopenSettings) openSettingsDialog();
connectEvents();
})();

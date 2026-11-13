/* Signal Web — vanilla JS client. All user content is inserted with textContent / DOM nodes. */
"use strict";

// ------------------------------------------------------------------ icons (Material, Apache-2.0)
const ICONS = {
  send: "M2.01 21L23 12 2.01 3 2 10l15 2-15 2z",
  attach: "M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5a2.5 2.5 0 0 1 5 0v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5a2.5 2.5 0 0 0 5 0V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z",
  back: "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
  more: "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
  search: "M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
  close: "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z",
  reply: "M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z",
  edit: "M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z",
  delete: "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
  mood: "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm3.5-9c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-7 0c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z",
  copy: "M16 1H4c-1.1 0-2 .9-2 2v14h2V3h12V1zm3 4H8c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h11c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm0 16H8V7h11v14z",
  archive: "M20.54 5.23l-1.39-1.68C18.88 3.21 18.47 3 18 3H6c-.47 0-.88.21-1.16.55L3.46 5.23C3.17 5.57 3 6.02 3 6.5V19c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V6.5c0-.48-.17-.93-.46-1.27zM12 17.5L6.5 12H10v-2h4v2h3.5L12 17.5zM5.12 5l.81-1h12l.94 1H5.12z",
  unarchive: "M20.55 5.22l-1.39-1.68C18.88 3.21 18.47 3 18 3H6c-.47 0-.88.21-1.15.55L3.46 5.22C3.17 5.57 3 6.01 3 6.5V19c0 1.1.89 2 2 2h14c1.1 0 2-.9 2-2V6.5c0-.49-.17-.93-.45-1.28zM12 9.5l5.5 5.5H14v2h-4v-2H6.5L12 9.5zM5.12 5l.82-1h12l.93 1H5.12z",
  bell: "M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z",
  bellOff: "M20 18.69L7.84 6.14 5.27 3.49 4 4.76l2.8 2.8v.01c-.52.99-.8 2.16-.8 3.42v5l-2 2v1h13.73l2 2L21 19.72l-1-1.03zM12 22c1.11 0 2-.89 2-2h-4c0 1.11.89 2 2 2zm6-7.32V11c0-3.08-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68c-.15.03-.29.08-.42.12-.1.03-.2.07-.3.11h-.01c-.01 0-.01 0-.02.01-.23.09-.46.2-.68.31 0 0-.01 0-.01.01L18 14.68z",
  check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  doneAll: "M18 7l-1.41-1.41-6.34 6.34 1.41 1.41L18 7zm4.24-1.41L11.66 16.17 7.48 12l-1.41 1.41L11.66 19l12-12-1.42-1.41zM.41 13.41L6 19l1.41-1.41L1.83 12 .41 13.41z",
  clock: "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
  error: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z",
  chat: "M20 2H4c-1.1 0-1.99.9-1.99 2L2 22l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-2 12H6v-2h12v2zm0-3H6V9h12v2zm0-3H6V6h12v2z",
  file: "M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z",
  timer: "M15 1H9v2h6V1zm-4 13h2V8h-2v6zm8.03-6.61l1.42-1.42c-.43-.51-.9-.99-1.41-1.41l-1.42 1.42A8.962 8.962 0 0 0 12 4c-4.97 0-9 4.03-9 9s4.02 9 9 9 9-4.03 9-9c0-2.12-.74-4.07-1.97-5.61zM12 20c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z",
  info: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z",
  down: "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6 1.41-1.41z",
  group: "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3zm0 2c-2.33 0-7 1.17-7 3.5V19h14v-2.5c0-2.33-4.67-3.5-7-3.5zm8 0c-.29 0-.62.02-.97.05 1.16.84 1.97 1.97 1.97 3.45V19h6v-2.5c0-2.33-4.67-3.5-7-3.5z",
  note: "M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-2 10H7v-2h10v2zm0-4H7V7h10v2zm-3 8H7v-2h7v2z",
  download: "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
  add: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  link: "M3.9 12c0-1.71 1.39-3.1 3.1-3.1h4V7H7c-2.76 0-5 2.24-5 5s2.24 5 5 5h4v-1.9H7c-1.71 0-3.1-1.39-3.1-3.1zM8 13h8v-2H8v2zm9-6h-4v1.9h4c1.71 0 3.1 1.39 3.1 3.1s-1.39 3.1-3.1 3.1h-4V17h4c2.76 0 5-2.24 5-5s-2.24-5-5-5z",
};
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("class", "ic");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "path");
  p.setAttribute("d", ICONS[name]);
  svg.appendChild(p);
  return svg;
}
function setIcon(el, name) { el.replaceChildren(icon(name)); }

// ------------------------------------------------------------------ tiny DOM helper
function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}
const $ = (id) => document.getElementById(id);

// ------------------------------------------------------------------ state
const S = {
  status: null,
  account: null,             // id of the Signal account being shown (its number, or ACI)
  accounts: [],              // [{id, number, name, unread, linked}] for every account
  addingAccount: false,      // link screen opened from the account menu
  linkGen: 0,                // which /link attempt we're waiting on
  notified: new Set(),       // "account|message id" already shown as a desktop notification
  convs: new Map(),          // id -> conversation
  showArchived: false,
  current: null,             // conversation id
  msgs: new Map(),           // conv id -> array of messages sorted by sent_ts
  hasMore: new Map(),
  loadingOlder: false,
  replyTo: null,             // message
  editing: null,             // message
  files: [],                 // File objects waiting to be sent
  typing: new Map(),         // conv id -> Map(author -> {name, timer})
  tempId: -1,
  searchTerm: "",
  searchHits: [],
  notify: lsGet("notify") === "1",
};
const QUICK_EMOJI = ["❤️", "👍", "👎", "😂", "😮", "😢"];

// ------------------------------------------------------------------ API
async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: {} };
  if (opts.json !== undefined) {
    init.method = opts.method || "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.json);
  } else if (opts.form) {
    init.method = "POST";
    init.body = opts.form;
  }
  const res = await fetch("/api" + path, init);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.status === 204 ? null : res.json();
}
const enc = (id) => id.split("/").map(encodeURIComponent).join("/");
// Everything about one account lives under /api/accounts/<id>/...
const abase = (acct = S.account) => `/api/accounts/${encodeURIComponent(acct)}`;
const aapi = (path, opts) => api(abase().slice(4) + path, opts);

// ------------------------------------------------------------------ formatting
const pad = (n) => String(n).padStart(2, "0");
function fmtTime(ts) { return new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }); }
function fmtListTime(ts) {
  const d = new Date(ts), now = new Date();
  if (d.toDateString() === now.toDateString()) return fmtTime(ts);
  const days = (now - d) / 864e5;
  if (days < 6) return d.toLocaleDateString([], { weekday: "short" });
  if (d.getFullYear() === now.getFullYear()) return d.toLocaleDateString([], { month: "short", day: "numeric" });
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}
function fmtDay(ts) {
  const d = new Date(ts), now = new Date();
  const y = new Date(now); y.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return "Today";
  if (d.toDateString() === y.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { weekday: "long", month: "long", day: "numeric", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}
function fmtSize(n) {
  if (!n && n !== 0) return "";
  const u = ["B", "KB", "MB", "GB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${u[i]}`;
}
const PALETTE = ["#c5221f", "#b06000", "#188038", "#1967d2", "#9334e6", "#d01884", "#007b83", "#5f6368", "#e8710a", "#3c4043"];
function colorFor(key) {
  let x = 0; for (const c of key || "") x = (x * 31 + c.charCodeAt(0)) | 0;
  return PALETTE[Math.abs(x) % PALETTE.length];
}
function initials(name) {
  const parts = (name || "?").replace(/[^\p{L}\p{N}\s]/gu, "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return (name || "?").trim().slice(0, 1) || "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
function avatarEl(conv, size = "") {
  const el = h("div", { class: `avatar ${size}` });
  el.style.background = colorFor(conv.id);
  if (conv.id === "u:self") { el.append(icon("note")); return el; }
  if (conv.kind === "group" && !conv.name) el.append(icon("group"));
  else el.append(initials(conv.name));
  const img = h("img", { alt: "", loading: "lazy", src: `${abase()}/avatars/${enc(conv.id)}` });
  img.addEventListener("error", () => img.remove());
  img.addEventListener("load", () => { if (!img.naturalWidth) img.remove(); });
  el.append(img);
  return el;
}
function personAvatar(rid, name, size = "sm") {
  const el = h("div", { class: `avatar ${size}` });
  el.style.background = colorFor("u:" + rid);
  el.append(initials(name));
  const img = h("img", { alt: "", loading: "lazy", src: `${abase()}/avatars/u:${enc(rid)}` });
  img.addEventListener("error", () => img.remove());
  el.append(img);
  return el;
}
function previewText(c) {
  let p = c.last_preview || "";
  if (c.last_author === "self" && p) p = "You: " + p;
  else if (c.kind === "group" && c.last_author_name && p) p = c.last_author_name.split(" ")[0] + ": " + p;
  return p;
}

// ------------------------------------------------------------------ rich text
const URL_RE = /\bhttps?:\/\/[^\s<>"']+[^\s<>"'.,;:!?)\]}]/g;
function linkify(text, parent, cls) {
  let last = 0;
  for (const m of text.matchAll(URL_RE)) {
    if (m.index > last) parent.append(styled(text.slice(last, m.index), cls));
    const a = h("a", { href: m[0], target: "_blank", rel: "noopener noreferrer" }, m[0]);
    if (cls) a.className = cls;
    parent.append(a);
    last = m.index + m[0].length;
  }
  if (last < text.length) parent.append(styled(text.slice(last), cls));
}
function styled(text, cls) {
  if (!cls) return document.createTextNode(text);
  const s = h("span", { class: cls }, text);
  if (cls.includes("st-SPOILER")) s.addEventListener("click", () => s.classList.toggle("revealed"));
  return s;
}
// Signal ranges are UTF-16 code units, which is exactly how JS strings index.
function renderBody(m, parent) {
  const text = m.body || "";
  const mentions = (m.mentions || []).slice().sort((a, b) => a.start - b.start);
  const styles = m.text_styles || [];
  const cuts = new Set([0, text.length]);
  for (const r of [...mentions, ...styles]) { cuts.add(r.start); cuts.add(Math.min(text.length, r.start + r.length)); }
  const points = [...cuts].filter((x) => x >= 0 && x <= text.length).sort((a, b) => a - b);
  let i = 0;
  while (i < points.length - 1) {
    const a = points[i];
    const mention = mentions.find((x) => x.start === a);
    if (mention) {
      const name = mention.rid === "self" ? "You" : (mention.name || nameFor(mention.rid));
      parent.append(h("span", { class: "mention" }, "@" + name));
      const end = mention.start + mention.length;
      while (i < points.length - 1 && points[i] < end) i++;
      continue;
    }
    const b = points[i + 1];
    const cls = styles.filter((s) => s.start <= a && s.start + s.length >= b).map((s) => "st-" + s.style).join(" ");
    linkify(text.slice(a, b), parent, cls);
    i++;
  }
}
const nameCache = new Map();
function nameFor(rid) { return nameCache.get(rid) || "someone"; }
function isJumbo(text) {
  if (!text || text.length > 24) return false;
  return /^(?:\p{Extended_Pictographic}|\p{Emoji_Component}|‍|️|\s)+$/u.test(text) && !/^[\d#*\s]+$/.test(text);
}

// ------------------------------------------------------------------ conversation list
function sortedConvs() {
  return [...S.convs.values()]
    .filter((c) => (S.showArchived ? c.archived : !c.archived) && c.last_ts > 0)
    .sort((a, b) => b.last_ts - a.last_ts);
}
function convRow(c, opts = {}) {
  const row = h("div", {
    class: "conv" + (c.id === S.current ? " selected" : "") + (c.unread ? " unread" : "") + (opts.cls ? " " + opts.cls : ""),
    role: "listitem",
    onclick: () => openConversation(c.id, opts.focusMsg),
  });
  row.append(
    avatarEl(c),
    h("div", { class: "meta" },
      h("div", { class: "row1" }, h("span", { class: "name" }, c.name), h("span", { class: "time" }, opts.time ?? (c.last_ts ? fmtListTime(c.last_ts) : ""))),
      h("div", { class: "row2" }, h("span", { class: "preview" }, opts.preview ?? previewText(c)), c.unread ? h("span", { class: "badge" }, c.unread > 99 ? "99+" : c.unread) : null),
    ),
  );
  return row;
}
function renderConvList() {
  const list = $("conv-list");
  const term = S.searchTerm.trim().toLowerCase();
  const items = [];
  let convs = sortedConvs();
  if (term) convs = [...S.convs.values()].filter((c) => c.name.toLowerCase().includes(term) || (c.number || "").includes(term)).sort((a, b) => b.last_ts - a.last_ts);
  if (S.showArchived) items.push(h("div", { class: "list-label" }, "Archived"));
  if (term && convs.length) items.push(h("div", { class: "list-label" }, "Conversations"));
  for (const c of convs) items.push(convRow(c));
  if (term && S.searchHits.length) {
    items.push(h("div", { class: "list-label" }, "Messages"));
    for (const m of S.searchHits) {
      const c = S.convs.get(m.conversation_id) || { id: m.conversation_id, name: m.conversation_name, kind: m.conversation_id.startsWith("g:") ? "group" : "direct" };
      items.push(convRow(c, { cls: "search-hit", preview: (m.outgoing ? "You: " : (c.kind === "group" ? m.author_name + ": " : "")) + m.body, time: fmtListTime(m.sent_ts), focusMsg: m.id }));
    }
  }
  if (!items.length || (items.length === 1 && S.showArchived)) {
    items.push(h("div", { class: "list-label", style: "text-transform:none" }, term ? "No results" : S.showArchived ? "No archived conversations" : "No conversations yet. New messages will appear here as they arrive."));
  }
  list.replaceChildren(...items);
  updateTitle();
}
function updateTitle() {
  let n = 0; for (const c of S.convs.values()) if (!c.archived) n += c.unread || 0;
  n += otherUnread();
  document.title = n ? `(${n}) Signal Web` : "Signal Web";
}
async function loadConversations() {
  const acct = S.account;
  const [active, archived] = await Promise.all([aapi("/conversations"), aapi("/conversations?archived=true")]);
  if (S.account !== acct) return;
  S.convs.clear();
  for (const c of [...active, ...archived]) { S.convs.set(c.id, c); cacheName(c); }
  renderConvList();
  if (S.current) renderThreadHeader();
}
function cacheName(c) { if (c.kind === "direct") nameCache.set(c.peer, c.name); }

// ------------------------------------------------------------------ thread
async function openConversation(id, focusMsgId) {
  if (S.current !== id) {
    S.current = id;
    S.replyTo = S.editing = null;
    S.files = [];
    renderComposerContext(); renderPendingFiles();
    $("input").value = "";
    autoGrow();
  }
  const acct = S.account;
  if (!S.convs.has(id)) {
    try { const c = await aapi(`/conversations/${enc(id)}`); if (S.account !== acct) return; S.convs.set(c.id, c); cacheName(c); } catch (e) { toast(e.message); return; }
  }
  setHash();
  $("app").classList.add("in-thread");
  $("empty-thread").hidden = true;
  $("thread-head").hidden = $("messages").hidden = $("composer").hidden = false;
  autoGrow();
  $("details").hidden = true;
  renderConvList();
  renderThreadHeader();
  $("message-items").replaceChildren();
  const msgs = await aapi(`/conversations/${enc(id)}/messages?limit=60`);
  if (S.current !== id || S.account !== acct) return;
  S.msgs.set(id, msgs);
  S.hasMore.set(id, msgs.length >= 60);
  renderMessages({ scroll: "bottom" });
  if (focusMsgId) {
    await ensureLoaded(id, focusMsgId);
    const el = document.querySelector(`[data-mid="${focusMsgId}"]`);
    if (el) { el.scrollIntoView({ block: "center" }); flash(el); }
  }
  markReadSoon();
  if (window.matchMedia("(min-width: 761px)").matches) $("input").focus();
}
async function ensureLoaded(convId, msgId) {
  for (let i = 0; i < 20 && !(S.msgs.get(convId) || []).some((m) => m.id === msgId) && S.hasMore.get(convId); i++) await loadOlder();
}
function flash(el) { const b = el.querySelector(".bubble"); if (!b) return; b.animate([{ filter: "brightness(1.4)" }, { filter: "none" }], { duration: 1200 }); }
function renderThreadHeader() {
  const c = S.convs.get(S.current);
  if (!c) return;
  $("thread-avatar").replaceChildren(avatarEl(c, "md"));
  $("thread-name").textContent = c.name;
  setIcon($("thread-archive"), c.archived ? "unarchive" : "archive");
  $("thread-archive").title = c.archived ? "Unarchive" : "Archive";
  const typers = S.typing.get(c.id);
  const sub = $("thread-sub");
  sub.classList.toggle("typing", !!(typers && typers.size));
  if (typers && typers.size) sub.textContent = c.kind === "group" ? [...typers.values()].map((t) => t.name.split(" ")[0]).join(", ") + " typing…" : "typing…";
  else if (c.kind === "group") sub.textContent = c.is_member === false ? "You're not a member of this group" : `${c.member_count || 0} members`;
  else if (c.id === "u:self") sub.textContent = "Messages synced to all your devices";
  else sub.textContent = c.number && c.number !== c.name ? c.number : "";
  if (c.expire_timer) sub.textContent += (sub.textContent ? " · " : "") + "⏱ disappearing messages";
  const composerOk = !(c.kind === "group" && c.is_member === false);
  $("composer").hidden = !composerOk;
  renderTyping();
}

function renderMessages({ scroll } = {}) {
  const box = $("messages");
  const list = S.msgs.get(S.current) || [];
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  const prevHeight = box.scrollHeight, prevTop = box.scrollTop;
  const conv = S.convs.get(S.current) || {};
  const nodes = [];
  let lastDay = null;
  const visible = list.filter((m) => true);
  // find the latest outgoing message to show its status
  let lastOutId = null;
  for (let i = visible.length - 1; i >= 0; i--) if (visible[i].outgoing && visible[i].kind === "message") { lastOutId = visible[i].id; break; }
  for (let i = 0; i < visible.length; i++) {
    const m = visible[i], prev = visible[i - 1], next = visible[i + 1];
    const day = new Date(m.sent_ts).toDateString();
    if (day !== lastDay) { nodes.push(h("div", { class: "day-sep" }, fmtDay(m.sent_ts))); lastDay = day; }
    if (m.kind === "system") { nodes.push(h("div", { class: "system-msg", dataset: { mid: m.id } }, m.body, " · ", fmtTime(m.sent_ts))); continue; }
    const groupable = (a, b) => a && b && a.kind === "message" && b.kind === "message" && a.author === b.author &&
      Math.abs(a.sent_ts - b.sent_ts) < 5 * 60e3 && new Date(a.sent_ts).toDateString() === new Date(b.sent_ts).toDateString() && !(a.reactions || []).length;
    const first = !groupable(prev, m), last = !groupable(m, next) || (m.reactions || []).length > 0;
    nodes.push(messageEl(m, conv, { first, last, showStatus: m.id === lastOutId || m.status === "failed" || m.status === "sending" }));
  }
  $("message-items").replaceChildren(...nodes);
  $("load-more").hidden = !S.hasMore.get(S.current);
  if (scroll === "bottom" || (scroll !== "keep-top" && atBottom)) box.scrollTop = box.scrollHeight;
  else if (scroll === "keep-top") box.scrollTop = box.scrollHeight - prevHeight + prevTop;
  else box.scrollTop = prevTop;
  updateJumpBtn();
}

function attUrl(a, download) { return `${abase()}/attachments/${encodeURIComponent(a.id)}${download ? "?download=true" : ""}`; }
function messageEl(m, conv, { first, last, showStatus }) {
  const isGroup = conv.kind === "group";
  const row = h("div", { class: `msg${m.outgoing ? " out" : ""}${first ? " first" : ""}${last ? " last" : ""}`, dataset: { mid: m.id } });
  if (isGroup && !m.outgoing) {
    row.append(h("div", { class: "avatar-col" }, last ? personAvatar(m.author, m.author_name) : null));
  }
  const stack = h("div", { class: "stack" });
  if (isGroup && !m.outgoing && first) {
    const s = h("div", { class: "sender" }, m.author_name);
    s.style.color = colorFor("u:" + m.author);
    stack.append(s);
  }
  const bubble = h("div", { class: "bubble" });
  if (m.deleted) {
    bubble.classList.add("deleted");
    bubble.append(m.outgoing ? "You deleted this message" : "This message was deleted");
  } else {
    if (m.quote) {
      const q = m.quote;
      const qa = (q.attachments || [])[0];
      bubble.append(h("div", { class: "quote", onclick: () => jumpToQuote(q) },
        h("div", { class: "q-author" }, q.author === "self" ? "You" : q.author_name),
        h("div", { class: "q-text" }, q.text || (qa ? "📎 " + (qa.filename || qa.contentType || "Attachment") : "")),
      ));
    }
    const atts = m.attachments || [];
    const visual = atts.filter((a) => /^(image|video)\//.test(a.contentType || "") && !/svg/.test(a.contentType));
    const others = atts.filter((a) => !visual.includes(a));
    if (visual.length) {
      const grid = h("div", { class: `media n${Math.min(visual.length, 4)}` });
      for (const a of visual) {
        if (a.contentType.startsWith("image/")) {
          const img = h("img", { src: attUrl(a), alt: a.caption || a.filename || "image", loading: "lazy" });
          if (a.width && a.height) { img.width = a.width; img.height = a.height; img.style.aspectRatio = `${a.width}/${a.height}`; }
          img.addEventListener("click", () => openLightbox(attUrl(a)));
          img.addEventListener("load", () => { if (S.stickToBottom) $("messages").scrollTop = $("messages").scrollHeight; });
          grid.append(img);
        } else {
          grid.append(h("video", { src: attUrl(a), controls: true, preload: "metadata" }));
        }
      }
      bubble.append(grid);
    }
    for (const a of others) {
      if ((a.contentType || "").startsWith("audio/")) {
        bubble.append(h("audio", { src: attUrl(a), controls: true, preload: "none" }));
      } else {
        bubble.append(h("a", { class: "file-chip", href: attUrl(a, true), download: a.filename || "" },
          icon("file"),
          h("div", {}, h("div", { class: "fname" }, a.filename || "Attachment"), h("div", { class: "fsize" }, [fmtSize(a.size), a.contentType].filter(Boolean).join(" · ")))));
      }
    }
    if (m.sticker) bubble.append(h("div", { class: "muted" }, "🖼 Sticker"));
    for (const p of m.previews || []) {
      if (!p.url) continue;
      bubble.append(h("a", { class: "preview-card", href: p.url, target: "_blank", rel: "noopener noreferrer" },
        p.image && p.image.id ? h("img", { src: attUrl(p.image), alt: "", loading: "lazy" }) : null,
        h("div", {}, h("div", { class: "p-title" }, p.title || p.url), p.description ? h("div", { class: "muted" }, p.description) : null)));
    }
    if (m.body) {
      const textEl = h("div", { class: visual.length || others.length ? "caption" : "" });
      renderBody(m, textEl);
      bubble.append(textEl);
      if (!atts.length && !m.quote && !(m.previews || []).length && isJumbo(m.body)) bubble.classList.add("jumbo");
    } else if (visual.length && !others.length && !m.quote) {
      bubble.classList.add("media-only");
    }
  }
  if (m.status === "sending") bubble.classList.add("sending");
  if (m.status === "failed") bubble.classList.add("failed");
  stack.append(bubble);

  if ((m.reactions || []).length) {
    const counts = new Map();
    for (const r of m.reactions) {
      const e = counts.get(r.emoji) || { n: 0, mine: false, names: [] };
      e.n++; e.names.push(r.author_name); if (r.author === "self") e.mine = true;
      counts.set(r.emoji, e);
    }
    const rx = h("div", { class: "reactions" });
    for (const [emoji, e] of counts) {
      rx.append(h("button", { class: e.mine ? "mine" : "", title: e.names.join(", "), onclick: () => react(m, emoji, e.mine) }, emoji, e.n > 1 ? " " + e.n : ""));
    }
    stack.append(rx);
  }

  if (last || showStatus) {
    const meta = h("div", { class: "msg-meta" });
    if (m.expires_in) meta.append(icon("timer"));
    meta.append(fmtTime(m.sent_ts));
    if (m.edited && !m.deleted) meta.append(" · Edited");
    if (m.outgoing && showStatus && !m.deleted) {
      const st = m.status || "sent";
      const [ic, label, cls] = {
        sending: ["clock", "Sending", ""], sent: ["check", "Sent", ""], delivered: ["doneAll", "Delivered", ""],
        read: ["doneAll", "Read", "read"], viewed: ["doneAll", "Viewed", "read"], failed: ["error", "Not sent", "failed"],
      }[st] || ["check", "Sent", ""];
      meta.append(" · ", h("span", { class: cls, title: label, style: "display:inline-flex;align-items:center;gap:2px" }, icon(ic), label));
    }
    stack.append(meta);
  }

  if (m.id > 0 && !m.deleted) {
    const actions = h("div", { class: "hover-actions" },
      h("button", { class: "icon-btn", title: "React", onclick: (e) => { e.stopPropagation(); openMenu(m, e.currentTarget, true); } }, icon("mood")),
      h("button", { class: "icon-btn", title: "Reply", onclick: () => startReply(m) }, icon("reply")),
      h("button", { class: "icon-btn", title: "More", onclick: (e) => { e.stopPropagation(); openMenu(m, e.currentTarget, false); } }, icon("more")),
    );
    stack.append(actions);
    bubble.addEventListener("contextmenu", (e) => { e.preventDefault(); openMenu(m, { getBoundingClientRect: () => ({ left: e.clientX, right: e.clientX, top: e.clientY, bottom: e.clientY }) }, false); });
    let pressTimer;
    bubble.addEventListener("touchstart", () => { pressTimer = setTimeout(() => openMenu(m, bubble, false), 450); }, { passive: true });
    for (const ev of ["touchend", "touchmove", "touchcancel"]) bubble.addEventListener(ev, () => clearTimeout(pressTimer), { passive: true });
  }
  row.append(stack);
  return row;
}
function jumpToQuote(q) {
  const list = S.msgs.get(S.current) || [];
  const target = list.find((m) => m.sent_ts === q.id && m.author === q.author);
  if (!target) return toast("Original message isn't available on this device");
  const el = document.querySelector(`[data-mid="${target.id}"]`);
  if (el) { el.scrollIntoView({ block: "center", behavior: "smooth" }); flash(el); }
}

async function loadOlder() {
  if (S.loadingOlder || !S.hasMore.get(S.current)) return;
  const id = S.current, acct = S.account, list = S.msgs.get(id) || [];
  if (!list.length) return;
  S.loadingOlder = true;
  try {
    const older = await aapi(`/conversations/${enc(id)}/messages?before=${list[0].sent_ts}&limit=60`);
    if (S.current !== id || S.account !== acct) return;
    const known = new Set(list.map((m) => m.id));
    S.msgs.set(id, [...older.filter((m) => !known.has(m.id)), ...list]);
    S.hasMore.set(id, older.length >= 60);
    renderMessages({ scroll: "keep-top" });
  } finally { S.loadingOlder = false; }
}

function upsertMessage(m) {
  const list = S.msgs.get(m.conversation_id);
  if (!list) return false;
  const idx = list.findIndex((x) => x.id === m.id);
  if (idx >= 0) list[idx] = m;
  else {
    list.push(m);
    list.sort((a, b) => a.sent_ts - b.sent_ts || a.id - b.id);
  }
  return true;
}

// ------------------------------------------------------------------ menus
function closeMenu() {
  $("msg-menu").hidden = true;
  document.querySelectorAll(".msg.menu-open").forEach((el) => el.classList.remove("menu-open"));
}
function openMenu(m, anchor, emojiOnly) {
  closeMenu();
  const menu = $("msg-menu");
  const mine = (m.reactions || []).find((r) => r.author === "self");
  const items = [];
  items.push(h("div", { class: "emoji-row" }, QUICK_EMOJI.map((e) =>
    h("button", { class: mine && mine.emoji === e ? "mine" : "", title: e, onclick: () => { closeMenu(); react(m, e, mine && mine.emoji === e); } }, e)),
    h("button", { title: "Other emoji", onclick: () => { closeMenu(); const e = prompt("React with emoji:"); if (e && e.trim()) react(m, e.trim(), false); } }, "＋")));
  if (!emojiOnly) {
    const item = (ic, label, fn, cls) => h("button", { class: "item" + (cls ? " " + cls : ""), onclick: () => { closeMenu(); fn(); } }, icon(ic), label);
    items.push(item("reply", "Reply", () => startReply(m)));
    if (m.body) items.push(item("copy", "Copy text", () => navigator.clipboard.writeText(m.body).then(() => toast("Copied"))));
    if (m.outgoing && m.body && !m.deleted && Date.now() - m.sent_ts < 24 * 3600e3) items.push(item("edit", "Edit", () => startEdit(m)));
    for (const a of m.attachments || []) items.push(item("download", `Download ${a.filename || "attachment"}`, () => { location.href = attUrl(a, true); }));
    items.push(item("delete", "Delete for me", () => deleteMsg(m, false), "danger"));
    if (m.outgoing && Date.now() - m.sent_ts < 24 * 3600e3) items.push(item("delete", "Delete for everyone", () => deleteMsg(m, true), "danger"));
  }
  menu.replaceChildren(...items);
  menu.hidden = false;
  const r = anchor.getBoundingClientRect();
  const mw = menu.offsetWidth, mh = menu.offsetHeight;
  let left = Math.min(window.innerWidth - mw - 8, Math.max(8, r.left));
  let top = r.bottom + 6;
  if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
  menu.style.left = left + "px"; menu.style.top = top + "px";
  const row = document.querySelector(`[data-mid="${m.id}"]`);
  if (row) row.classList.add("menu-open");
}
document.addEventListener("click", (e) => {
  if (!$("msg-menu").contains(e.target)) closeMenu();
  if (!$("account-menu").contains(e.target)) closeAccountMenu();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    closeMenu(); closeAccountMenu();
    if (!$("lightbox").hidden) $("lightbox").hidden = true;
    else if (S.replyTo || S.editing) cancelContext();
  }
});

// ------------------------------------------------------------------ actions
async function react(m, emoji, remove) {
  try { await aapi(`/messages/${m.id}/react`, { json: { emoji, remove } }); } catch (e) { toast("Reaction failed: " + e.message); }
}
async function deleteMsg(m, everyone) {
  if (everyone && !confirm("Delete this message for everyone?")) return;
  if (!everyone && !confirm("Delete this message from Signal Web? (It stays on your other devices.)")) return;
  try { await aapi(`/messages/${m.id}/delete`, { json: { everyone } }); } catch (e) { toast("Delete failed: " + e.message); }
}
function startReply(m) { S.editing = null; S.replyTo = m; renderComposerContext(); $("input").focus(); }
function startEdit(m) { S.replyTo = null; S.editing = m; S.files = []; renderPendingFiles(); $("input").value = m.body || ""; autoGrow(); renderComposerContext(); $("input").focus(); }
function cancelContext() { if (S.editing) $("input").value = ""; S.replyTo = S.editing = null; renderComposerContext(); autoGrow(); }
function renderComposerContext() {
  const m = S.replyTo || S.editing;
  $("compose-context").hidden = !m;
  if (!m) return;
  $("ctx-label").textContent = S.editing ? "Editing message" : `Replying to ${m.outgoing ? "yourself" : m.author_name}`;
  $("ctx-body").textContent = m.body || (m.attachments.length ? "📎 Attachment" : "");
  updateSendBtn();
}

async function sendCurrent() {
  const convId = S.current, acct = S.account;
  const input = $("input");
  const text = input.value.trim();
  if (!convId || (!text && !S.files.length)) return;
  const form = new FormData();
  form.append("text", text);
  if (S.replyTo) form.append("quote_id", S.replyTo.id);
  if (S.editing) form.append("edit_id", S.editing.id);
  for (const f of S.files) form.append("files", f, f.name);
  const editing = S.editing, replyTo = S.replyTo, files = S.files;

  let temp = null;
  if (!editing) {
    temp = {
      id: S.tempId--, conversation_id: convId, author: "self", author_name: "You", outgoing: true, kind: "message",
      sent_ts: Date.now(), body: text, status: "sending", reactions: [], deleted: false, edited: false,
      attachments: files.map((f) => ({ id: "", filename: f.name, contentType: "application/x-pending", size: f.size })),
      quote: replyTo ? { id: replyTo.sent_ts, author: replyTo.author, author_name: replyTo.author_name, text: replyTo.body } : null,
    };
    upsertMessage(temp);
  }
  input.value = ""; autoGrow();
  S.replyTo = S.editing = null; S.files = [];
  renderComposerContext(); renderPendingFiles();
  if (convId === S.current) renderMessages({ scroll: "bottom" });
  stopTyping();
  try {
    const msg = await aapi(`/conversations/${enc(convId)}/messages`, { form });
    if (S.account !== acct) return;
    if (temp) removeMessage(convId, temp.id, false);
    upsertMessage(msg);
  } catch (e) {
    if (S.account !== acct) return toast("Message not sent: " + e.message);
    if (temp) { temp.status = "failed"; upsertMessage(temp); }
    toast("Message not sent: " + e.message);
    if (!temp) { $("input").value = text; }
  }
  if (convId === S.current) renderMessages({ scroll: "bottom" });
}
function removeMessage(convId, id, render = true) {
  const list = S.msgs.get(convId);
  if (!list) return;
  const i = list.findIndex((m) => m.id === id);
  if (i >= 0) list.splice(i, 1);
  if (render && convId === S.current) renderMessages();
}

let readTimer = null;
function markReadSoon() {
  clearTimeout(readTimer);
  readTimer = setTimeout(() => {
    const c = S.convs.get(S.current);
    if (c && c.unread && document.visibilityState === "visible" && document.hasFocus()) {
      aapi(`/conversations/${enc(c.id)}/read`, { method: "POST" }).catch(() => {});
    }
  }, 400);
}
window.addEventListener("focus", markReadSoon);
document.addEventListener("visibilitychange", markReadSoon);

// typing indicator (outgoing)
let typingActive = false, typingTimer = null;
function onTypingInput() {
  if (!S.current || S.current === "u:self") return;
  if (!typingActive && $("input").value.trim()) {
    typingActive = true;
    aapi(`/conversations/${enc(S.current)}/typing`, { json: { started: true } }).catch(() => {});
  }
  clearTimeout(typingTimer);
  typingTimer = setTimeout(stopTyping, 5000);
}
function stopTyping() {
  clearTimeout(typingTimer);
  if (typingActive && S.current) aapi(`/conversations/${enc(S.current)}/typing`, { json: { started: false } }).catch(() => {});
  typingActive = false;
}
// typing indicator (incoming)
function onTypingEvent(ev) {
  let m = S.typing.get(ev.conversation_id);
  if (!m) { m = new Map(); S.typing.set(ev.conversation_id, m); }
  const prev = m.get(ev.author);
  if (prev) clearTimeout(prev.timer);
  if (ev.started) {
    m.set(ev.author, { name: ev.author_name, timer: setTimeout(() => { m.delete(ev.author); refreshTyping(ev.conversation_id); }, 15000) });
  } else m.delete(ev.author);
  refreshTyping(ev.conversation_id);
}
function refreshTyping(convId) { if (convId === S.current) { renderThreadHeader(); } }
function renderTyping() {
  const typers = S.typing.get(S.current);
  const show = !!(typers && typers.size);
  const box = $("messages");
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 80;
  $("typing-row").hidden = !show;
  $("typing-who").textContent = show && S.convs.get(S.current)?.kind === "group" ? [...typers.values()].map((t) => t.name).join(", ") : "";
  if (show && atBottom) box.scrollTop = box.scrollHeight;
}

// ------------------------------------------------------------------ composer wiring
function autoGrow() {
  const t = $("input");
  t.style.height = "auto";
  // scrollHeight is 0 while the composer is hidden; leave the natural height in that case
  if (t.scrollHeight) t.style.height = Math.min(t.scrollHeight, 180) + "px";
  updateSendBtn();
}
function updateSendBtn() { $("send-btn").disabled = !($("input").value.trim() || S.files.length); }
function addFiles(list) {
  if (S.editing) return toast("Can't add attachments while editing");
  for (const f of list) S.files.push(f);
  renderPendingFiles();
}
function renderPendingFiles() {
  const box = $("pending-files");
  box.hidden = !S.files.length;
  box.replaceChildren(...S.files.map((f, i) => {
    const el = h("div", { class: "pending-file", title: f.name }, f.type.startsWith("image/") ? null : f.name);
    if (f.type.startsWith("image/")) {
      const url = URL.createObjectURL(f);
      const img = h("img", { src: url, alt: f.name }); img.onload = () => URL.revokeObjectURL(url);
      el.append(img);
    }
    el.append(h("button", { title: "Remove", onclick: () => { S.files.splice(i, 1); renderPendingFiles(); } }, icon("close")));
    return el;
  }));
  updateSendBtn();
}

// ------------------------------------------------------------------ details panel
async function showDetails() {
  const c = await aapi(`/conversations/${enc(S.current)}`);
  const body = $("details-body");
  const kids = [h("div", { class: "big-avatar" }, avatarEl(c)), h("h3", {}, c.name)];
  if (c.number && c.kind === "direct") kids.push(h("p", { class: "muted", style: "text-align:center" }, c.number));
  if (c.description) kids.push(h("p", { class: "muted" }, c.description));
  if (c.expire_timer) kids.push(h("p", { class: "muted" }, `⏱ Disappearing messages: ${fmtDuration(c.expire_timer)}`));
  if (c.members && c.members.length) {
    kids.push(h("div", { class: "list-label" }, `${c.members.length} members`));
    for (const mem of c.members) kids.push(h("div", { class: "member" }, personAvatar(mem.rid, mem.name), h("span", {}, mem.name)));
  }
  body.replaceChildren(...kids);
  $("details").hidden = false;
}
function fmtDuration(s) {
  for (const [u, n] of [["week", 604800], ["day", 86400], ["hour", 3600], ["minute", 60]]) if (s >= n && s % n === 0) return `${s / n} ${u}${s / n > 1 ? "s" : ""}`;
  return `${s} seconds`;
}

// ------------------------------------------------------------------ new chat dialog
let contactsCache = null;
async function openNewChat() {
  const dlg = $("new-chat");
  $("new-chat-input").value = "";
  dlg.showModal();
  $("new-chat-input").focus();
  try { contactsCache = await aapi("/contacts"); } catch (_) { contactsCache = { people: [], groups: [] }; }
  renderPickList();
}
function renderPickList() {
  const term = $("new-chat-input").value.trim().toLowerCase();
  const items = [];
  const phone = term.replace(/[\s\-()]/g, "");
  if (/^\+\d{6,15}$/.test(phone)) items.push(convRowLike({ id: "u:" + phone, name: phone, kind: "direct" }, "Message " + phone, () => startChatWith({ recipient: phone })));
  items.push(convRowLike({ id: "u:self", name: "Note to Self", kind: "direct" }, "", () => startChatWith({ recipient: "self" }), term && !"note to self".includes(term)));
  const people = (contactsCache?.people || []).filter((p) => !term || p.name.toLowerCase().includes(term) || (p.number || "").includes(phone));
  const groups = (contactsCache?.groups || []).filter((g) => !term || (g.name || "").toLowerCase().includes(term));
  if (groups.length) items.push(h("div", { class: "list-label" }, "Groups"));
  for (const g of groups.slice(0, 50)) items.push(convRowLike({ id: "g:" + g.id, name: g.name || "Unnamed group", kind: "group" }, "", () => startChatWith({ group_id: g.id })));
  if (people.length) items.push(h("div", { class: "list-label" }, "Contacts"));
  for (const p of people.slice(0, 200)) items.push(convRowLike({ id: "u:" + p.rid, name: p.name, kind: "direct" }, p.number || "", () => startChatWith({ recipient: p.rid })));
  if (!items.filter(Boolean).length) items.push(h("p", { class: "muted", style: "padding: 0 16px" }, "Type a phone number in international format, e.g. +15551234567"));
  $("new-chat-list").replaceChildren(...items.filter(Boolean));
}
function convRowLike(c, sub, onclick, hide) {
  if (hide) return null;
  return h("div", { class: "conv", onclick }, avatarEl(c, "md"), h("div", { class: "meta" }, h("div", { class: "row1" }, h("span", { class: "name" }, c.name)), sub ? h("div", { class: "row2" }, h("span", { class: "preview" }, sub)) : null));
}
async function startChatWith(body) {
  try {
    const c = await aapi("/conversations", { json: body });
    S.convs.set(c.id, c); cacheName(c);
    $("new-chat").close();
    openConversation(c.id);
  } catch (e) { toast(e.message); }
}

// ------------------------------------------------------------------ notifications / misc UI
function toast(text) {
  const b = $("banner");
  b.className = "banner error"; b.textContent = text; b.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => { if (b.textContent === text) renderBanner(); }, 4000);
}
function renderBanner() {
  const b = $("banner");
  const st = S.status?.state;
  b.className = "banner";
  if (!wsOpen) { b.textContent = "Reconnecting to Signal Web…"; b.hidden = false; }
  else if (st === "disconnected") { b.textContent = "signal-cli is not running — retrying" + (S.status.error ? ` (${S.status.error})` : ""); b.className = "banner error"; b.hidden = false; }
  else if (st === "starting") { b.textContent = "Starting signal-cli…"; b.hidden = false; }
  else b.hidden = true;
}
function renderNotifBtn() {
  setIcon($("notif-btn"), S.notify ? "bell" : "bellOff");
  $("notif-btn").classList.toggle("active", S.notify);
  $("notif-btn").title = S.notify ? "Desktop notifications on" : "Desktop notifications off";
}
async function toggleNotify() {
  if (!S.notify) {
    if (!("Notification" in window)) return toast("This browser doesn't support notifications (or the page isn't on HTTPS)");
    const p = await Notification.requestPermission();
    if (p !== "granted") return toast("Notifications were blocked by the browser");
  }
  S.notify = !S.notify;
  lsSet("notify", S.notify ? "1" : "0");
  renderNotifBtn();
}
function maybeNotify(m, acct) {
  if (!S.notify || m.outgoing || m.kind !== "message" || m.is_read || m.deleted) return;
  const key = acct + "|" + m.id;
  if (S.notified.has(key)) return; // later updates (reactions, receipts) re-send the same message
  const here = acct === S.account;
  if (here && document.visibilityState === "visible" && document.hasFocus() && S.current === m.conversation_id) return;
  const c = here ? S.convs.get(m.conversation_id) : null;
  if (c && c.archived) return;
  S.notified.add(key);
  try {
    let title = c ? (c.kind === "group" ? `${m.author_name} · ${c.name}` : c.name) : m.author_name;
    if (S.accounts.length > 1) title += ` → ${accountLabel(accountById(acct))}`;
    const n = new Notification(title, { body: m.body || (m.attachments.length ? "📎 Attachment" : ""), tag: acct + "|" + m.conversation_id, renotify: true });
    n.onclick = () => { window.focus(); switchAccount(acct, m.conversation_id); n.close(); };
  } catch (_) {}
}
function openLightbox(src) { $("lightbox-img").src = src; $("lightbox").hidden = false; }
function updateJumpBtn() {
  const box = $("messages");
  const dist = box.scrollHeight - box.scrollTop - box.clientHeight;
  S.stickToBottom = dist < 80;
  $("jump-btn").hidden = dist < 400;
}

// ------------------------------------------------------------------ link screen
async function startLink() {
  $("link-msg").textContent = "";
  $("qr").replaceChildren(h("p", { class: "muted" }, "Generating…"));
  try {
    const res = await api("/link", { method: "POST" });
    S.linkGen = res.gen;
    const wrap = h("div");
    wrap.innerHTML = res.qr_svg; // server-generated SVG from segno (no user content)
    $("qr").replaceChildren(wrap);
    $("link-msg").textContent = "Waiting for you to scan… The code expires after a few minutes.";
  } catch (e) {
    $("qr").replaceChildren(h("button", { class: "btn primary", onclick: startLink }, "Try again"));
    $("link-msg").textContent = "Could not start linking: " + e.message;
  }
}
function showLinkScreen(adding) {
  S.addingAccount = adding;
  $("link-title").textContent = adding ? "Link another Signal account" : "Link Signal Web to your account";
  $("link-cancel").hidden = !adding;
  $("qr").replaceChildren(h("button", { class: "btn primary", onclick: startLink }, "Show QR code"));
  $("link-msg").textContent = "";
  renderScreens();
}
function cancelAddAccount() {
  if (S.status?.linking) api("/link", { method: "DELETE" }).catch(() => {});
  S.addingAccount = false;
  renderScreens();
}
function renderScreens() {
  const st = S.status;
  if (!st) return;
  const hasAccounts = S.accounts.length > 0;
  const linkScreen = st.state !== "starting" && (!hasAccounts || S.addingAccount);
  $("link-screen").hidden = !linkScreen;
  // With accounts on disk the history is readable even while signal-cli is still starting.
  $("app").hidden = linkScreen || !hasAccounts;
}
function applyStatus(st) {
  const prev = S.status;
  S.status = st;
  S.accounts = st.accounts || [];
  if (S.addingAccount && st.last_linked && st.last_linked.gen === S.linkGen) {
    S.addingAccount = false;
    switchAccount(st.last_linked.account);
  }
  if ((S.addingAccount || !S.accounts.length) && prev?.linking && !st.linking) {
    $("qr").replaceChildren(h("button", { class: "btn primary", onclick: startLink }, "Show a new QR code"));
    $("link-msg").textContent = st.link_error ? "Linking didn't finish: " + st.link_error : "";
  }
  if (S.accounts.length && !accountById(S.account)) {
    // first load, or the shown account is gone: hash, then last used, then the first one
    const want = parseHash(), saved = lsGet("account");
    const pick = accountById(want.a) || accountById(saved) || S.accounts[0];
    switchAccount(pick.id, pick.id === want.a ? want.c : null);
  } else if (st.state === "ready" && prev && prev.state !== "ready" && S.account) {
    loadConversations().then(() => S.current && openConversation(S.current));
  }
  renderScreens();
  renderAccounts();
  renderBanner();
}

// ------------------------------------------------------------------ accounts
function lsGet(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
function lsSet(k, v) { try { localStorage.setItem(k, v); } catch (_) {} }
function accountById(id) { return id ? S.accounts.find((a) => a.id === id) : undefined; }
function accountLabel(a) { return a ? a.name || a.number || "Signal account" : "Signal account"; }
function otherUnread() { return S.accounts.reduce((n, a) => n + (a.id === S.account ? 0 : a.unread || 0), 0); }
function parseHash() {
  const raw = location.hash.slice(1);
  if (!raw) return {};
  const p = new URLSearchParams(raw);
  if (p.has("a") || p.has("c")) return { a: p.get("a"), c: p.get("c") };
  return { c: decodeURIComponent(raw) }; // links from before multi-account
}
function setHash() {
  const p = new URLSearchParams();
  if (S.account) p.set("a", S.account);
  if (S.current) p.set("c", S.current);
  history.replaceState(null, "", S.account ? "#" + p.toString() : location.pathname);
}
function accountAvatar(a, size = "sm") {
  const el = h("div", { class: `avatar ${size}` });
  el.style.background = colorFor("acct:" + a.id);
  el.append(a.name ? initials(a.name) : "#");
  const img = h("img", { alt: "", loading: "lazy", src: `${abase(a.id)}/avatars/u:self` });
  img.addEventListener("error", () => img.remove());
  img.addEventListener("load", () => { if (!img.naturalWidth) img.remove(); });
  el.append(img);
  return el;
}
function closeThread() {
  stopTyping();
  S.current = null; S.replyTo = S.editing = null; S.files = [];
  $("app").classList.remove("in-thread");
  $("empty-thread").hidden = false;
  $("thread-head").hidden = $("messages").hidden = $("composer").hidden = true;
  $("details").hidden = true;
  $("input").value = "";
  renderComposerContext(); renderPendingFiles();
  setHash();
}
async function switchAccount(id, convId) {
  closeAccountMenu();
  if (S.account !== id) {
    if (S.account) closeThread();
    S.account = id;
    lsSet("account", id);
    S.convs.clear(); S.msgs.clear(); S.hasMore.clear(); S.typing.clear(); nameCache.clear();
    S.searchHits = []; S.searchTerm = ""; $("search").value = ""; contactsCache = null;
    S.showArchived = false; $("archive-btn").classList.remove("active"); $("side-title").textContent = "Messages";
    renderConvList();
    setHash();
  }
  renderAccounts();
  try { await loadConversations(); } catch (e) { toast(e.message); return; }
  if (convId && S.account === id) openConversation(convId);
  refreshAccounts();
}
function renderAccounts() {
  const cur = accountById(S.account);
  const btn = $("account-btn");
  if (!cur) { btn.hidden = true; return; }
  btn.hidden = false;
  btn.title = `${accountLabel(cur)}${cur.number && cur.name ? " (" + cur.number + ")" : ""} · switch or add account`;
  btn.replaceChildren(accountAvatar(cur));
  if (otherUnread()) btn.append(h("span", { class: "acct-dot", title: "Unread messages in another account" }));
  const sub = $("side-account");
  sub.hidden = S.accounts.length < 2;
  sub.textContent = cur.name && cur.number ? `${cur.name} · ${cur.number}` : accountLabel(cur);
  updateTitle();
}
let accountsTimer = null;
function refreshAccounts() {
  // Unread counts for the accounts not on screen; debounced because events come in bursts.
  clearTimeout(accountsTimer);
  accountsTimer = setTimeout(async () => {
    try { S.accounts = await api("/accounts"); renderAccounts(); } catch (_) {}
  }, 300);
}
function closeAccountMenu() { $("account-menu").hidden = true; }
function openAccountMenu() {
  closeMenu();
  const menu = $("account-menu");
  const items = S.accounts.map((a) => h("button", { class: "item acct" + (a.id === S.account ? " current" : ""), role: "menuitem", onclick: () => switchAccount(a.id) },
    accountAvatar(a, "md"),
    h("div", { class: "acct-text" },
      h("div", { class: "acct-name" }, accountLabel(a)),
      h("div", { class: "acct-sub" }, a.linked === false ? "Not linked · history only" : (a.name ? a.number || "" : ""))),
    a.id !== S.account && a.unread ? h("span", { class: "badge" }, a.unread > 99 ? "99+" : a.unread) : null,
    a.id === S.account ? icon("check") : null));
  items.push(h("div", { class: "menu-sep" }),
    h("button", { class: "item", role: "menuitem", onclick: openWebhookDialog }, icon("link"), "Webhook sending…"),
    h("button", { class: "item", role: "menuitem", onclick: () => { closeAccountMenu(); showLinkScreen(true); } }, icon("add"), "Link another account"));
  menu.replaceChildren(...items);
  menu.hidden = false;
  const r = $("account-btn").getBoundingClientRect();
  menu.style.top = r.bottom + 6 + "px";
  menu.style.left = Math.max(8, Math.min(window.innerWidth - menu.offsetWidth - 8, r.right - menu.offsetWidth)) + "px";
  refreshAccounts();
}

// ------------------------------------------------------------------ webhook sending
// Lets the webhook relay (python -m app.webhook) send as the current account. The server refuses
// relay requests for an account unless it's enabled here; the token says which account sends.
const webhookUI = { acct: null, hook: null, reveal: false };
async function openWebhookDialog() {
  closeAccountMenu();
  Object.assign(webhookUI, { acct: S.account, hook: null, reveal: false });
  renderWebhook();
  $("webhook-dlg").showModal();
  try { webhookUI.hook = await aapi("/webhook"); renderWebhook(); } catch (e) { toast(e.message); }
}
async function updateWebhook(body) {
  try { webhookUI.hook = await api(abase(webhookUI.acct).slice(4) + "/webhook", { method: "PUT", json: body }); }
  catch (e) { toast("Couldn't save: " + e.message); }
  renderWebhook();
}
function copyText(text, input) {
  const done = () => toast("Copied");
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text).then(done, () => toast("Copy failed"));
  // Plain-http LAN pages have no clipboard API: fall back to selecting the field.
  input.type = "text"; input.select();
  try { document.execCommand("copy"); done(); } catch (_) { toast("Select the token and copy it"); }
}
function renderWebhook() {
  const { hook, reveal } = webhookUI;
  const label = accountLabel(accountById(webhookUI.acct));
  const kids = [h("p", { class: "muted" }, `Lets your webhook system send Signal messages as ${label} through the webhook relay. They appear here like any message you send.`)];
  if (!hook) { kids.push(h("p", { class: "muted" }, "Loading…")); $("webhook-body").replaceChildren(...kids); return; }
  const toggle = h("input", { type: "checkbox", id: "webhook-enabled", checked: hook.enabled, onchange: (e) => updateWebhook({ enabled: e.target.checked }) });
  kids.push(h("label", { class: "switch-row", for: "webhook-enabled" }, toggle, h("span", {}, `Allow webhook sending from ${label}`)));
  if (hook.token) {
    const field = h("input", { class: "token", readonly: true, type: reveal ? "text" : "password", value: hook.token, "aria-label": "Webhook token" });
    kids.push(
      h("div", { class: "list-label" }, "Token"),
      h("div", { class: "token-row" }, field,
        h("button", { type: "button", class: "btn small", onclick: () => { webhookUI.reveal = !reveal; renderWebhook(); } }, reveal ? "Hide" : "Show"),
        h("button", { type: "button", class: "btn small", onclick: () => copyText(hook.token, field) }, "Copy")),
      h("button", { type: "button", class: "btn small danger", onclick: () => { if (confirm("Make a new token? Anything using the current one stops working.")) updateWebhook({ regenerate: true }); } }, "Make a new token"),
      hook.enabled ? null : h("p", { class: "muted small" }, "Turned off: requests with this token are refused."),
      h("div", { class: "list-label" }, "Example"),
      h("pre", { class: "code" }, `curl -X POST http://YOUR-HOST:8081/send \\
  -H "Authorization: Bearer ${reveal ? hook.token : "<token>"}" \\
  -H "Content-Type: application/json" \\
  -d '{"recipient": "+15551234567", "message": "Backup finished"}'`),
      h("p", { class: "muted small" }, "recipient: a number in international format, or \"self\" for your Note to Self. Use \"group_id\" to send to a group. Keep the token secret: it can send messages as this number."));
  }
  $("webhook-body").replaceChildren(...kids.filter(Boolean)); // replaceChildren would print "null"
}

// ------------------------------------------------------------------ websocket
let ws = null, wsOpen = false, wsBackoff = 1000;
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => {
    const reconnect = wsBackoff > 1000 || S.status;
    wsOpen = true; wsBackoff = 1000; renderBanner();
    if (reconnect && S.account) {
      // catch up on anything missed while disconnected
      loadConversations().then(() => S.current && openConversation(S.current));
    }
  };
  ws.onclose = () => {
    wsOpen = false; renderBanner();
    setTimeout(connectWs, wsBackoff);
    wsBackoff = Math.min(wsBackoff * 2, 15000);
  };
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
}
setInterval(() => { if (ws && ws.readyState === 1) ws.send("ping"); }, 25000);

function handleEvent(ev) {
  if (ev.account && ev.account !== S.account) {
    // Another account: keep its unread badge current and still notify.
    if (ev.type === "message" && !ev.message.outgoing) maybeNotify(ev.message, ev.account);
    if (ev.type !== "typing") refreshAccounts();
    return;
  }
  switch (ev.type) {
    case "status": applyStatus(ev.status); break;
    case "conversation": {
      const c = ev.conversation;
      S.convs.set(c.id, c); cacheName(c);
      renderConvList();
      if (c.id === S.current) { renderThreadHeader(); if (c.unread) markReadSoon(); }
      refreshAccounts();
      break;
    }
    case "conversations_changed": loadConversations(); break;
    case "message": {
      const m = ev.message;
      const known = (S.msgs.get(m.conversation_id) || []).some((x) => x.id === m.id);
      if (upsertMessage(m) && m.conversation_id === S.current) {
        if (!m.outgoing) { const t = S.typing.get(m.conversation_id); if (t && t.has(m.author)) { clearTimeout(t.get(m.author).timer); t.delete(m.author); renderThreadHeader(); } }
        renderMessages();
      }
      if (!known && !m.outgoing) maybeNotify(m, S.account);
      break;
    }
    case "message_removed": removeMessage(ev.conversation_id, ev.id); break;
    case "typing": onTypingEvent(ev); break;
  }
}

// ------------------------------------------------------------------ boot
function wire() {
  setIcon(document.querySelector(".search-icon"), "search");
  setIcon($("archive-btn"), "archive");
  setIcon($("back-btn"), "back");
  setIcon($("thread-info"), "info");
  setIcon($("attach-btn"), "attach");
  setIcon($("send-btn"), "send");
  setIcon($("ctx-close"), "close");
  setIcon($("details-close"), "close");
  setIcon($("new-chat-close"), "close");
  setIcon($("webhook-close"), "close");
  setIcon($("lightbox-close"), "close");
  setIcon($("jump-btn"), "down");
  setIcon(document.querySelector(".empty-art"), "chat");
  document.querySelector(".fab-icon").replaceChildren(icon("chat"));
  renderNotifBtn();

  $("link-btn").addEventListener("click", startLink);
  $("link-cancel").addEventListener("click", cancelAddAccount);
  $("account-btn").addEventListener("click", (e) => { e.stopPropagation(); $("account-menu").hidden ? openAccountMenu() : closeAccountMenu(); });
  $("notif-btn").addEventListener("click", toggleNotify);
  $("archive-btn").addEventListener("click", () => {
    S.showArchived = !S.showArchived;
    $("archive-btn").classList.toggle("active", S.showArchived);
    $("side-title").textContent = S.showArchived ? "Archived" : "Messages";
    renderConvList();
  });
  $("back-btn").addEventListener("click", () => { $("app").classList.remove("in-thread"); S.current = null; setHash(); renderConvList(); });
  $("thread-info").addEventListener("click", showDetails);
  $("details-close").addEventListener("click", () => { $("details").hidden = true; });
  $("thread-archive").addEventListener("click", async () => {
    const c = S.convs.get(S.current); if (!c) return;
    await aapi(`/conversations/${enc(c.id)}/archive`, { json: { archived: !c.archived } });
  });
  $("new-chat-btn").addEventListener("click", openNewChat);
  $("new-chat-input").addEventListener("input", renderPickList);
  $("new-chat-form").addEventListener("submit", (e) => {
    if (e.submitter && e.submitter.value === "cancel") return;
    e.preventDefault();
    const first = $("new-chat-list").querySelector(".conv"); if (first) first.click();
  });

  let searchTimer;
  $("search").addEventListener("input", (e) => {
    S.searchTerm = e.target.value;
    clearTimeout(searchTimer);
    if (S.searchTerm.trim().length < 2) { S.searchHits = []; renderConvList(); return; }
    renderConvList();
    searchTimer = setTimeout(async () => {
      const q = S.searchTerm.trim();
      try { const hits = await aapi(`/search?q=${encodeURIComponent(q)}`); if (q === S.searchTerm.trim()) { S.searchHits = hits; renderConvList(); } } catch (_) {}
    }, 250);
  });

  const input = $("input");
  input.addEventListener("input", () => { autoGrow(); onTypingInput(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && window.matchMedia("(min-width: 761px)").matches) { e.preventDefault(); sendCurrent(); }
    if (e.key === "ArrowUp" && !input.value) {
      const mine = (S.msgs.get(S.current) || []).filter((m) => m.outgoing && m.body && !m.deleted && m.id > 0).pop();
      if (mine) { e.preventDefault(); startEdit(mine); }
    }
  });
  input.addEventListener("paste", (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); addFiles(files); }
  });
  $("send-btn").addEventListener("click", sendCurrent);
  $("ctx-close").addEventListener("click", cancelContext);
  $("attach-btn").addEventListener("click", () => $("file-input").click());
  $("file-input").addEventListener("change", (e) => { addFiles([...e.target.files]); e.target.value = ""; });

  const thread = $("thread");
  let dragDepth = 0;
  thread.addEventListener("dragenter", (e) => { if (S.current && e.dataTransfer.types.includes("Files")) { dragDepth++; $("drop-overlay").hidden = false; } });
  thread.addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("drop-overlay").hidden = true; } });
  thread.addEventListener("dragover", (e) => { if (S.current) e.preventDefault(); });
  thread.addEventListener("drop", (e) => { e.preventDefault(); dragDepth = 0; $("drop-overlay").hidden = true; if (S.current) addFiles([...e.dataTransfer.files]); });

  const box = $("messages");
  box.addEventListener("scroll", () => { if (box.scrollTop < 200) loadOlder(); updateJumpBtn(); }, { passive: true });
  $("jump-btn").addEventListener("click", () => { box.scrollTo({ top: box.scrollHeight, behavior: "smooth" }); });
  $("lightbox").addEventListener("click", () => { $("lightbox").hidden = true; });
}

wire();
api("/status").then(applyStatus).catch(() => {});
connectWs();

// MultiDrop web build (GitHub Pages). The same screens as daemon/web/app.js,
// on AnEntrypoint/wireweave instead of the local daemon. Peer-supplied strings
// (device and file names, texts) are always inserted as text, never as HTML.
import { createWire } from "./wire.js";
import qrcode from "qrcode-generator";

const $ = (sel) => document.querySelector(sel);
const LS_ALIAS = "multidrop-alias";
const LS_ROOM = "multidrop-room";
const jobs = new Map();        // job id -> {info, files: Map(name -> {done,size}), state, error}
const unchecked = new Map();   // offer id -> Set of file ids the user unticked
let offers = [];               // incoming offers, oldest first
let devices = [];              // reachable devices in this room
let wire = null;
let room = "";
let alias = "";

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children) e.append(c instanceof Node ? c : String(c ?? ""));
  return e;
}

function human(n) {
  if (n === null || n === undefined) return "size unknown";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++; }
  return i ? `${n.toFixed(1)} ${units[i]}` : `${n} B`;
}

function randomId(n, alphabet = "abcdefghjkmnpqrstuvwxyz23456789") {
  return [...crypto.getRandomValues(new Uint8Array(n))].map((b) => alphabet[b % alphabet.length]).join("");
}

// A room link (#room=…) joins that room and remembers it; without one the last room is reused.
function roomId() {
  const fromLink = location.hash.match(/room=([\w-]+)/);
  if (fromLink) {
    localStorage.setItem(LS_ROOM, fromLink[1]);
    history.replaceState(null, "", location.pathname);
  }
  let id = localStorage.getItem(LS_ROOM);
  if (!id) { id = randomId(12); localStorage.setItem(LS_ROOM, id); }
  return id;
}

function aliasName() {
  let name = localStorage.getItem(LS_ALIAS);
  if (!name) { name = `Browser ${randomId(4, "ABCDEFGHJKLMNPQRSTUVWXYZ23456789")}`; localStorage.setItem(LS_ALIAS, name); }
  return name;
}

// -- status, offers -------------------------------------------------------

function showStatus(text) {
  $("#status").textContent = text;
}

function renderOffers() {
  const box = $("#offers");
  box.replaceChildren();
  $("#offers-section").hidden = offers.length === 0;
  for (const o of offers) {
    const selectable = o.files.length > 1;
    const off = unchecked.get(o.id) || new Set();
    unchecked.set(o.id, off);
    const items = el("ul", { class: selectable ? "files selectable" : "files" });
    for (const f of o.files) {
      const label = `${f.name} (${human(f.size)})`;
      if (!selectable) { items.append(el("li", {}, label)); continue; }
      const cb = el("input", { type: "checkbox", "data-file": f.id, onchange: (ev) => {
        if (ev.target.checked) off.delete(f.id); else off.add(f.id);
      } });
      cb.checked = !off.has(f.id);
      items.append(el("li", {}, el("label", {}, cb, " ", label)));
    }
    const answer = (accept, ids) => {
      wire.answer(o.id, accept, ids);
      offers = offers.filter((x) => x.id !== o.id);
      unchecked.delete(o.id);
      renderOffers();
    };
    const everyFile = o.files.map((f) => f.id);
    const chosen = () => everyFile.filter((id) => !off.has(id));
    box.append(el("div", { class: "card offer" },
      el("div", { class: "name" }, `${o.from} wants to send`),
      el("div", { class: "meta" }, `Browser (WebRTC) · ${human(o.total_size)}`),
      items,
      el("div", { class: "row" },
        el("button", { class: "primary", type: "button", onclick: () => answer(true, everyFile) },
           selectable ? "Accept all" : "Accept"),
        selectable ? el("button", { type: "button", "data-action": "accept-selected", onclick: () => {
          const ids = chosen();
          if (ids.length) answer(true, ids); else answer(false);
        } }, "Accept selected") : "",
        el("button", { class: "danger", type: "button", onclick: () => answer(false) }, "Decline"))));
  }
}

// -- devices and sending --------------------------------------------------

function refreshDevices() {
  devices = wire ? wire.devices() : [];
  renderDevices();
}

function renderDevices() {
  const box = $("#devices");
  box.replaceChildren();
  const select = $("#text-target");
  const previous = select.value;
  select.replaceChildren();
  for (const d of devices) {
    const card = el("div", { class: "card drop" },
      el("div", { class: "name" }, d.name),
      el("div", { class: "meta" }, "Browser (WebRTC)"),
      el("span", { class: "badge" }, "WebRTC"));
    makeDropTarget(card, (files) => sendFiles(d, files));
    box.append(card);
    select.append(el("option", { value: d.pubkey }, d.name));
  }
  if (previous) select.value = previous;
  if (!devices.length) {
    box.append(el("p", { class: "hint" }, "No devices yet. Open the QR link below on another phone or computer; it joins this room."));
  }
}

function makeDropTarget(card, onFiles) {
  card.addEventListener("dragover", (ev) => { ev.preventDefault(); card.classList.add("over"); });
  card.addEventListener("dragleave", () => card.classList.remove("over"));
  card.addEventListener("drop", async (ev) => {
    ev.preventDefault();
    card.classList.remove("over");
    const files = await filesFromDrop(ev.dataTransfer);
    if (files.length) onFiles(files);
  });
  card.addEventListener("click", () => {
    const input = $("#pick-files");
    input.value = "";
    input.onchange = () => {
      const files = [...input.files].map((f) => ({ file: f, path: f.name }));
      if (files.length) onFiles(files);
    };
    input.click();
  });
}

// Folders arrive as directory entries; walk them to keep relative paths.
async function filesFromDrop(dt) {
  const entries = [...dt.items].map((i) => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!entries.length) return [...dt.files].map((f) => ({ file: f, path: f.name }));
  const out = [];
  async function walk(entry, prefix) {
    if (entry.isFile) {
      const file = await new Promise((res, rej) => entry.file(res, rej));
      out.push({ file, path: prefix + file.name });
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      for (;;) {
        const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
        if (!batch.length) break;
        for (const e of batch) await walk(e, `${prefix}${entry.name}/`);
      }
    }
  }
  for (const e of entries) await walk(e, "");
  return out;
}

function sendFiles(device, files) {
  const total = files.reduce((s, f) => s + f.file.size, 0);
  addLog(`Handing over ${files.length} file(s), ${human(total)} to ${device.name} …`);
  try {
    wire.sendFiles(device.pubkey, files, device.name);
  } catch (e) {
    addLog(`Sending to ${device.name} failed: ${e.message}`);
  }
}

// -- join code ------------------------------------------------------------

function showJoinCode() {
  const url = `${location.origin}${location.pathname}#room=${room}`;
  const link = $("#join-url");
  link.textContent = url;
  link.href = url;
  const qr = qrcode(0, "M");
  qr.addData(url);
  qr.make();
  const svg = new DOMParser().parseFromString(qr.createSvgTag(4, 2), "image/svg+xml");
  $("#qr").replaceChildren(document.importNode(svg.documentElement, true));
}

// -- jobs -----------------------------------------------------------------

function renderJobs() {
  const box = $("#jobs");
  box.replaceChildren();
  const list = [...jobs.entries()].reverse().slice(0, 10);
  if (!list.length) box.append(el("p", { class: "hint" }, "Nothing sent yet."));
  for (const [id, j] of list) {
    let done = 0, size = 0;
    for (const f of j.files.values()) { done += f.done; size += f.size; }
    const label = { running: "running", waiting: "waiting for acceptance", done: "done",
                    failed: "failed", cancelled: "cancelled" }[j.state] || j.state;
    const row = el("div", { class: `job card ${j.state}` },
      el("span", { class: "what" }, `${j.info.items.join(", ")} → ${j.info.to}`),
      size ? el("progress", { max: size, value: done }) : "",
      el("span", { class: "state" }, j.error ? `${label}: ${j.error}` : label));
    if (["running", "waiting"].includes(j.state)) {
      row.append(el("button", { type: "button", onclick: () => wire.cancel(id) }, "Cancel"));
    }
    box.append(row);
  }
}

function onJobEvent(ev) {
  if (ev.event === "job_started") {
    jobs.set(ev.job, { info: ev.info, files: new Map(), state: "waiting" });
    if (jobs.size > 50) jobs.delete(jobs.keys().next().value);
  }
  const j = jobs.get(ev.job);
  if (!j) return;
  switch (ev.event) {
    case "progress": j.state = "running"; j.files.set(ev.file, { done: ev.done, size: ev.size }); break;
    case "job_done": j.state = "done"; break;
    case "job_failed": j.state = "failed"; j.error = ev.error; break;
    case "job_cancelled": j.state = "cancelled"; break;
  }
  renderJobs();
}

// -- events and history ---------------------------------------------------

function addLog(content) {
  const log = $("#log");
  log.prepend(el("li", {}, el("time", {}, new Date().toLocaleTimeString()), content));
  while (log.children.length > 200) log.lastChild.remove();
}

function onEvent(ev) {
  switch (ev.event) {
    case "connected":
      showStatus(`Ready – visible as “${alias}” in this room`);
      break;
    case "devices":
      refreshDevices();
      break;
    case "offer":
      offers.push(ev.offer);
      renderOffers();
      addLog(`${ev.offer.from} wants to send ${ev.offer.files.length} item(s)`);
      break;
    case "offer_withdrawn":
      offers = offers.filter((o) => o.id !== ev.id);
      renderOffers();
      break;
    case "file_received":
      addLog(el("span", {}, `received ${ev.file} from ${ev.from} (${human(ev.size)}) · `,
        el("a", { href: ev.url, download: ev.file }, "save")));
      break;
    case "message":
      addLog(`${ev.kind === "url" ? "Link" : "Text"} from ${ev.from}: ${ev.text}`);
      break;
    case "job_started":
    case "progress":
    case "job_done":
    case "job_failed":
    case "job_cancelled":
      onJobEvent(ev);
      if (ev.event === "job_failed") addLog(`sending failed: ${ev.error}`);
      break;
    case "error":
      addLog(`Error: ${ev.message}`);
      break;
  }
}

// -- init -----------------------------------------------------------------

function init() {
  room = roomId();
  alias = aliasName();
  document.querySelectorAll(".alias").forEach((e) => { e.textContent = `“${alias}”`; });
  showStatus("connecting …");

  $("#refresh").addEventListener("click", refreshDevices);
  $("#text-form").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const pk = $("#text-target").value;
    if (!pk) { addLog("No device selected"); return; }
    const select = $("#text-target");
    const label = select.selectedOptions[0].textContent;
    const text = $("#text").value.trim();
    if (!text) return;
    wire.sendText(pk, text, label);
    $("#text").value = "";
  });

  showJoinCode();
  renderOffers();
  renderJobs();

  wire = createWire({ alias, room, onEvent });
  window.addEventListener("pagehide", () => { wire.leave(); });
  wire.join().catch((e) => showStatus(`Could not join the room: ${e.message}`));
}

init();

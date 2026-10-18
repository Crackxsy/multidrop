// Browser transport for the GitHub Pages build. AnEntrypoint/wireweave carries
// presence and WebRTC signalling for one room over nostr relays; the file bytes
// go over its ordered data channel as JSON control frames plus binary chunks.
import { createWireweave } from "./vendor/wireweave/src/wireweave.js";
import * as NostrTools from "nostr-tools";
import * as xstate from "xstate";

const NAMESPACE = "multidrop";
const CHUNK = 64 * 1024;                 // well under the message limit browsers accept
const MAX_BUFFERED = 4 * 1024 * 1024;    // pause sending while the channel is this full

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const newId = () => crypto.randomUUID().slice(0, 12);
const baseName = (p) => p.split(/[\\/]/).filter(Boolean).pop() || "file";

export function createWire({ alias, room, onEvent }) {
  const ww = createWireweave({ nostrTools: NostrTools, xstate });
  const data = ww.ensureData({ namespace: NAMESPACE });
  const emit = (ev) => onEvent(ev);

  const outgoing = new Map();        // job id -> {id, pubkey, info, files: [{fid, name, file}], state}
  const incoming = new Map();        // offer id -> {pubkey, files}
  const receiving = new Map();       // pubkey -> file currently arriving {id, fid, name, size, parts, got}
  const queues = new Map();          // pubkey -> tail of that peer's transfer queue
  const cancelled = new Set();

  const nameOf = (pk) => data.participants.get("nostr-" + pk.slice(0, 12))?.identity || pk.slice(0, 8);

  const sendControl = (pk, msg) => {
    if (!data.send(pk, JSON.stringify(msg))) throw new Error("device is not connected");
  };

  const drain = async (pk) => {
    for (;;) {
      const dc = data.peers.get(pk)?.dc;
      if (!dc || dc.readyState !== "open") throw new Error("device disconnected");
      if (dc.bufferedAmount <= MAX_BUFFERED) return;
      await sleep(25);
    }
  };

  const enqueue = (pk, task) => {
    const next = (queues.get(pk) || Promise.resolve()).then(task);
    queues.set(pk, next.catch(() => {}));
    return next;
  };

  async function transfer(job, files) {
    job.state = "running";
    try {
      for (const f of files) {
        sendControl(job.pubkey, { k: "file", id: job.id, fid: f.fid, name: f.name, size: f.file.size });
        let done = 0;
        for (let off = 0; off < f.file.size; off += CHUNK) {
          if (cancelled.has(job.id)) throw new Error("cancelled");
          await drain(job.pubkey);
          const buf = await f.file.slice(off, off + CHUNK).arrayBuffer();
          if (!data.send(job.pubkey, buf)) throw new Error("device disconnected");
          done += buf.byteLength;
          emit({ event: "progress", job: job.id, file: f.name, done, size: f.file.size });
        }
        sendControl(job.pubkey, { k: "end", id: job.id, fid: f.fid });
      }
      emit({ event: "job_done", job: job.id, info: job.info });
    } catch (e) {
      if (cancelled.has(job.id)) emit({ event: "job_cancelled", job: job.id });
      else emit({ event: "job_failed", job: job.id, error: e.message });
    } finally {
      outgoing.delete(job.id);
      cancelled.delete(job.id);
    }
  }

  function onControl(pk, msg) {
    switch (msg.k) {
      case "offer": {
        incoming.set(msg.id, { pubkey: pk, files: msg.files });
        const files = msg.files.map((f) => ({ id: f.id, name: baseName(f.name), size: f.size }));
        emit({ event: "offer", offer: {
          id: msg.id, from: msg.from || nameOf(pk), files,
          total_size: files.reduce((s, f) => s + f.size, 0),
        } });
        return;
      }
      case "accept": {
        const job = outgoing.get(msg.id);
        if (!job || job.pubkey !== pk) return;
        const chosen = job.files.filter((f) => msg.files.includes(f.fid));
        if (!chosen.length) { outgoing.delete(job.id); emit({ event: "job_failed", job: job.id, error: "nothing accepted" }); return; }
        enqueue(pk, () => transfer(job, chosen));
        return;
      }
      case "decline": {
        const job = outgoing.get(msg.id);
        if (!job || job.pubkey !== pk) return;
        outgoing.delete(msg.id);
        emit({ event: "job_failed", job: msg.id, error: "declined by receiver" });
        return;
      }
      case "file":
        receiving.set(pk, { id: msg.id, fid: msg.fid, name: baseName(msg.name), size: msg.size, parts: [], got: 0 });
        return;
      case "end": {
        const rx = receiving.get(pk);
        receiving.delete(pk);
        if (!rx || rx.fid !== msg.fid) return;
        const blob = new Blob(rx.parts, { type: "application/octet-stream" });
        emit({ event: "file_received", from: nameOf(pk), file: rx.name, size: blob.size, url: URL.createObjectURL(blob) });
        return;
      }
      case "text":
        emit({ event: "message", from: nameOf(pk), kind: /^https?:\/\//i.test(msg.text) ? "url" : "text", text: msg.text });
        return;
      case "cancel":
        incoming.delete(msg.id);
        if (receiving.get(pk)?.id === msg.id) receiving.delete(pk);
        emit({ event: "offer_withdrawn", id: msg.id });
        return;
    }
  }

  function onChunk(pk, buf) {
    const rx = receiving.get(pk);
    if (!rx) return;
    rx.parts.push(buf);
    rx.got += buf.byteLength;
    if (rx.got > rx.size) {
      receiving.delete(pk);
      emit({ event: "error", message: `${rx.name}: more data than announced` });
    }
  }

  data.addEventListener("data", (e) => {
    const { peerPubkey: pk, data: payload } = e.detail;
    if (typeof payload !== "string") { onChunk(pk, payload); return; }
    let msg;
    try { msg = JSON.parse(payload); } catch { return; }
    onControl(pk, msg);
  });

  data.addEventListener("connected", () => emit({ event: "connected" }));
  data.addEventListener("participants", () => emit({ event: "devices" }));
  data.addEventListener("error", (e) => emit({ event: "error", message: e.detail.message }));
  data.addEventListener("peer-open", (e) => { if (!e.detail.unreliable) emit({ event: "devices" }); });
  data.addEventListener("peer-close", (e) => {
    const pk = e.detail.peerPubkey;
    if (e.detail.unreliable) return;
    for (const [id, o] of incoming) if (o.pubkey === pk) { incoming.delete(id); emit({ event: "offer_withdrawn", id }); }
    for (const job of outgoing.values()) {
      if (job.pubkey !== pk) continue;
      cancelled.add(job.id);
      outgoing.delete(job.id);
      emit({ event: "job_failed", job: job.id, error: "connection closed" });
    }
    receiving.delete(pk);
    emit({ event: "devices" });
  });

  function startJob(pk, info, files) {
    const job = { id: newId(), pubkey: pk, info, files, state: "waiting" };
    outgoing.set(job.id, job);
    emit({ event: "job_started", job: job.id, info });
    return job;
  }

  return {
    pubkey: () => ww.auth.pubkey,

    async join() {
      ww.auth.loadFromStorage() || ww.auth.generateKey();
      ww.pool.connect();
      await data.connect(room, { displayName: alias });
    },

    leave() { return data.disconnect(); },

    devices() {
      return [...data.peers.keys()]
        .filter((pk) => data.peers.get(pk).dc?.readyState === "open")
        .map((pk) => ({ pubkey: pk, name: nameOf(pk) }));
    },

    sendFiles(pk, entries, label) {
      const files = entries.map((e, i) => ({ fid: String(i), name: e.path, file: e.file }));
      const job = startJob(pk, { items: files.map((f) => f.name), to: label }, files);
      try {
        sendControl(pk, { k: "offer", id: job.id, from: alias, files: files.map((f) => ({ id: f.fid, name: f.name, size: f.file.size })) });
      } catch (e) {
        outgoing.delete(job.id);
        emit({ event: "job_failed", job: job.id, error: e.message });
      }
      return job.id;
    },

    sendText(pk, text, label) {
      const job = startJob(pk, { items: [text.slice(0, 60)], to: label }, []);
      outgoing.delete(job.id);
      try {
        sendControl(pk, { k: "text", text });
        emit({ event: "job_done", job: job.id, info: job.info });
      } catch (e) {
        emit({ event: "job_failed", job: job.id, error: e.message });
      }
    },

    answer(id, accept, fileIds = []) {
      const offer = incoming.get(id);
      if (!offer) return;
      incoming.delete(id);
      try {
        sendControl(offer.pubkey, accept && fileIds.length ? { k: "accept", id, files: fileIds } : { k: "decline", id });
      } catch (e) {
        emit({ event: "error", message: `answer failed: ${e.message}` });
      }
    },

    cancel(id) {
      const job = outgoing.get(id);
      if (!job) return;
      cancelled.add(id);
      try { sendControl(job.pubkey, { k: "cancel", id }); } catch {}
      if (job.state === "waiting") {
        outgoing.delete(id);
        cancelled.delete(id);
        emit({ event: "job_cancelled", job: id });
      }
    },
  };
}

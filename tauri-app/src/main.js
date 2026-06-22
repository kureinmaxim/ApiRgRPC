// ApiRgRPC frontend — talks to the Rust backend via the global Tauri API
// (withGlobalTauri = true), which in turn drives the rns-engine sidecar.

const { invoke } = window.__TAURI__.core;
const { listen } = window.__TAURI__.event;

const $ = (id) => document.getElementById(id);

const els = {
  dot: $("engine-dot"),
  state: $("engine-state"),
  start: $("btn-start"),
  stop: $("btn-stop"),
  address: $("my-address"),
  copy: $("btn-copy"),
  announce: $("btn-announce"),
  name: $("my-name"),
  saveName: $("btn-name"),
  status: $("status-line"),
  peersCount: $("peers-count"),
  peersList: $("peers-list"),
  peerHash: $("peer-hash"),
  msgText: $("msg-text"),
  send: $("btn-send"),
  log: $("log"),
};

const peers = new Map(); // hash -> name

function logLine(text, cls = "l-muted") {
  const time = new Date().toLocaleTimeString();
  const div = document.createElement("div");
  div.className = cls;
  div.textContent = `[${time}] ${text}`;
  els.log.appendChild(div);
  els.log.scrollTop = els.log.scrollHeight;
}

function setRunning(running) {
  els.dot.className = "dot " + (running ? "on" : "off");
  els.state.textContent = running ? "движок запущен" : "движок остановлен";
  els.start.disabled = running;
  els.stop.disabled = !running;
}

function renderPeers() {
  els.peersCount.textContent = String(peers.size);
  els.peersList.innerHTML = "";
  for (const [hash, name] of peers) {
    const li = document.createElement("li");
    const left = document.createElement("div");
    left.innerHTML = `<div class="peer-name">${name || "(без имени)"}</div><div class="peer-hash">${hash}</div>`;
    const btn = document.createElement("button");
    btn.className = "btn";
    btn.textContent = "Выбрать";
    btn.onclick = () => { els.peerHash.value = hash; els.msgText.focus(); };
    li.appendChild(left);
    li.appendChild(btn);
    els.peersList.appendChild(li);
  }
}

// ---- engine events ----------------------------------------------------------
listen("rns-event", (event) => {
  const e = event.payload || {};
  switch (e.event) {
    case "ready":
      setRunning(true);
      els.address.value = e.address || "";
      if (e.name) els.name.value = e.name;
      logLine(`движок готов · адрес ${e.address}`, "l-ok");
      invoke("engine_status").catch(() => {});
      break;
    case "address":
      els.address.value = e.address || "";
      break;
    case "status":
      els.status.textContent =
        `адрес: ${e.address || "—"} · transport: ${e.transport ? "да" : "нет"} ` +
        `· интерфейсов: ${(e.interfaces || []).length} · пиров: ${e.peers ?? peers.size}`;
      break;
    case "announce":
      if (e.hash) { peers.set(e.hash, e.name || ""); renderPeers(); logLine(`анонс пира ${e.name || ""} ${e.hash}`); }
      break;
    case "rx":
      logLine(`RX от ${e.name || e.from}: ${e.title ? "[" + e.title + "] " : ""}${e.text}`, "l-rx");
      break;
    case "sent":
      logLine(`отправка → ${e.peer}: ${e.state}`, e.state === "delivered" ? "l-ok" : e.state === "failed" ? "l-err" : "l-muted");
      break;
    case "log":
      logLine(e.message, e.level === "error" ? "l-err" : e.level === "warn" ? "l-warn" : "l-muted");
      break;
    case "error":
      logLine("ОШИБКА: " + e.message, "l-err");
      break;
    default:
      logLine(JSON.stringify(e));
  }
});

// ---- controls ---------------------------------------------------------------
els.start.onclick = async () => {
  els.start.disabled = true;
  try {
    await invoke("engine_start", { name: els.name.value || "ApiRgRPC" });
  } catch (err) {
    logLine("не удалось запустить движок: " + err, "l-err");
    els.start.disabled = false;
  }
};

els.stop.onclick = async () => {
  try { await invoke("engine_stop"); } catch (err) { logLine(String(err), "l-err"); }
  setRunning(false);
  els.status.textContent = "—";
};

els.announce.onclick = () => invoke("engine_announce").catch((e) => logLine(String(e), "l-err"));

els.saveName.onclick = () => {
  const name = els.name.value.trim();
  if (name) invoke("engine_set_name", { name }).catch((e) => logLine(String(e), "l-err"));
};

els.copy.onclick = async () => {
  if (els.address.value) {
    await navigator.clipboard.writeText(els.address.value);
    logLine("адрес скопирован", "l-ok");
  }
};

els.send.onclick = async () => {
  const peer = els.peerHash.value.trim();
  const text = els.msgText.value;
  if (!peer || !text) { logLine("укажи адрес получателя и текст", "l-warn"); return; }
  try {
    await invoke("engine_send", { peer, text });
    els.msgText.value = "";
  } catch (err) {
    logLine("ошибка отправки: " + err, "l-err");
  }
};

els.msgText.addEventListener("keydown", (e) => { if (e.key === "Enter") els.send.click(); });

// ---- init -------------------------------------------------------------------
(async () => {
  try {
    const running = await invoke("engine_is_running");
    setRunning(running);
    if (running) invoke("engine_status").catch(() => {});
  } catch (_) {
    setRunning(false);
  }
  logLine("UI готов. Нажми «Запустить», чтобы поднять Reticulum-движок.", "l-muted");
})();

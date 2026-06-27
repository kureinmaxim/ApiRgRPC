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
  // device-control
  devHash: $("dev-hash"),
  devHashSet: $("btn-dev-hash"),
  devStatusBtn: $("btn-dev-status"),
  devStatusLine: $("dev-status-line"),
  devDevice: $("dev-device"),
  devRead: $("btn-dev-read"),
  devWriteOn: $("btn-dev-write-on"),
  devWriteOff: $("btn-dev-write-off"),
  devPing: $("btn-dev-ping"),
  devStream: $("btn-dev-stream"),
  devStreamMax: $("dev-stream-max"),
  // interfaces
  ifTcpHost: $("if-tcp-host"),
  ifTcpPort: $("if-tcp-port"),
  ifI2p: $("if-i2p"),
  ifI2pPort: $("if-i2p-port"),
  ifApply: $("btn-if-apply"),
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
    case "dev_hash":
      els.devStatusLine.textContent = `мост: ${e.hash || "(не задан)"}`;
      logLine(`HA-мост задан: ${e.hash}`, "l-muted");
      break;
    case "dev_status": {
      const path = e.has_path ? `да${e.hops != null ? ` (hops=${e.hops})` : ""}` : "нет";
      els.devStatusLine.textContent = `мост: ${e.hash || "—"} · путь: ${path}`;
      break;
    }
    case "dev_result": {
      const tag = `[${e.action}]`;
      if (e.action === "ping") {
        logLine(`${tag} ${e.ok ? "✅" : "❌"} ${e.ms ?? "?"} ms: ${e.message}`, e.ok ? "l-ok" : "l-err");
      } else if (e.action === "read") {
        logLine(`${tag} ${e.device}: ${e.message}${e.read_data ? " · data=" + e.read_data : ""}`, e.ok ? "l-ok" : "l-err");
      } else {
        logLine(`${tag} ${e.message}`, e.ok ? "l-ok" : "l-err");
      }
      break;
    }
    case "dev_event":
      logLine(`event ${e.device} ${e.type} ts=${e.ts} '${e.payload}'`, "l-rx");
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

// ---- device-control ---------------------------------------------------------
const devInvoke = (cmd, args = {}) => invoke(cmd, args).catch((e) => logLine(String(e), "l-err"));

els.devHashSet.onclick = () => {
  const hash = els.devHash.value.trim();
  if (hash) devInvoke("engine_dev_hash", { hash });
};
els.devStatusBtn.onclick = () => devInvoke("engine_dev_status");
els.devPing.onclick = () => { logLine("dev ping…", "l-muted"); devInvoke("engine_dev_ping"); };
els.devRead.onclick = () => {
  const device = els.devDevice.value.trim();
  if (device) devInvoke("engine_dev_read", { device });
};
els.devWriteOn.onclick = () => {
  const device = els.devDevice.value.trim();
  if (device) devInvoke("engine_dev_write", { device, on: true });
};
els.devWriteOff.onclick = () => {
  const device = els.devDevice.value.trim();
  if (device) devInvoke("engine_dev_write", { device, on: false });
};
els.devStream.onclick = () => {
  const max = parseInt(els.devStreamMax.value, 10) || 5;
  logLine(`dev stream (max=${max})…`, "l-muted");
  devInvoke("engine_dev_stream", { max });
};

// ---- interfaces (RNS config) ------------------------------------------------
els.ifApply.onclick = async () => {
  const tcpHost = els.ifTcpHost.value.trim();
  const tcpPort = parseInt(els.ifTcpPort.value, 10) || 50061;
  const useI2p = els.ifI2p.checked;
  const i2pPort = parseInt(els.ifI2pPort.value, 10) || 50061;
  if (!tcpHost && !useI2p) { logLine("укажи TCP host и/или включи I2P", "l-warn"); return; }
  try {
    const path = await invoke("engine_set_config", {
      tcpHost, tcpPort, useI2p, i2pPort,
    });
    logLine("RNS-config записан: " + path, "l-ok");
    // Перезапуск движка, чтобы интерфейсы применились.
    const running = await invoke("engine_is_running").catch(() => false);
    if (running) {
      logLine("перезапуск движка для применения интерфейсов…", "l-muted");
      await invoke("engine_stop").catch(() => {});
      setRunning(false);
      await invoke("engine_start", { name: els.name.value || "ApiRgRPC" });
    } else {
      logLine("интерфейсы применятся при следующем запуске движка", "l-muted");
    }
  } catch (err) {
    logLine("ошибка записи config: " + err, "l-err");
  }
};

async function prefillInterfaces() {
  try {
    const text = await invoke("engine_get_config");
    if (!text) return;
    const host = text.match(/target_host\s*=\s*([^\s]+)/);
    const port = text.match(/target_port\s*=\s*([0-9]+)/);
    if (host && host[1] !== "127.0.0.1") els.ifTcpHost.value = host[1];
    if (port) els.ifTcpPort.value = port[1];
    if (/\[\[I2P\]\]/.test(text)) els.ifI2p.checked = true;
  } catch (_) { /* нет config — ладно */ }
}

// ---- init -------------------------------------------------------------------
(async () => {
  try {
    const running = await invoke("engine_is_running");
    setRunning(running);
    if (running) invoke("engine_status").catch(() => {});
  } catch (_) {
    setRunning(false);
  }
  prefillInterfaces();
  logLine("UI готов. Задай интерфейс (TCP/I2P) и нажми «Запустить».", "l-muted");
})();

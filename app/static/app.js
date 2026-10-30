const $ = (s) => document.querySelector(s);
let devices = [];
let sortKey = "ip", sortDir = 1;
let current = null;
let wasRunning = false;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (iso) => (iso ? new Date(iso).toLocaleString() : "—");
const ipNum = (ip) => (ip || "").split(".").reduce((a, o) => a * 256 + Number(o), 0);
const name = (d) => d.alias || d.hostname || "";

function sortVal(d, key) {
  switch (key) {
    case "ip": return ipNum(d.ip);
    case "name": return name(d).toLowerCase();
    case "ports": return d.ports.length;
    case "online": return d.online;
    default: return (d[key] || "").toString().toLowerCase();
  }
}

function matches(d, q) {
  if (!q) return true;
  const hay = [d.ip, d.mac, d.vendor, d.hostname, d.alias, d.notes, d.os,
    ...d.ports.flatMap((p) => [p.port, p.service, p.product, p.version])].join(" ").toLowerCase();
  return q.split(/\s+/).every((t) => hay.includes(t));
}

function render() {
  const q = $("#search").value.trim().toLowerCase();
  const onlyOnline = $("#onlyOnline").checked;
  const rows = devices
    .filter((d) => (!onlyOnline || d.online) && matches(d, q))
    .sort((a, b) => {
      const x = sortVal(a, sortKey), y = sortVal(b, sortKey);
      return (x < y ? -1 : x > y ? 1 : 0) * sortDir;
    });

  $("#devices").querySelectorAll("tbody").forEach((b) => b.remove());
  $("#devices").insertAdjacentHTML("beforeend", rows.map((d) => `
    <tbody class="dev ${d.online ? "on" : ""}">
    <tr data-id="${d.id}" class="main ${d.online ? "" : "offline"}">
      <td><span class="dot ${d.online ? "on" : ""}" title="${d.online ? "online" : "offline"}"></span></td>
      <td class="mono">${esc(d.ip)}</td>
      <td>${esc(name(d))}${d.alias && d.hostname ? `<div class="sub">${esc(d.hostname)}</div>` : ""}</td>
      <td class="mono">${esc(d.mac || "—")}</td>
      <td>${esc(d.vendor || "")}</td>
      <td>${fmt(d.last_seen)}</td>
    </tr>
    <tr data-id="${d.id}" class="ports-row ${d.online ? "" : "offline"}">
      <td></td>
      <td colspan="5" class="ports-line">${d.ports.length
        ? d.ports.map((p) => `<span title="${esc([p.product, p.version].filter(Boolean).join(" "))}">${p.port}/${p.protocol}${p.service ? " " + esc(p.service) : ""}</span>`).join("")
        : `<span class="none">Nessuna porta aperta</span>`}</td>
    </tr>
    </tbody>`).join(""));
  $("#empty").hidden = devices.length > 0;

  $("#statTotal").textContent = devices.length;
  $("#statOnline").textContent = devices.filter((d) => d.online).length;
  $("#statPorts").textContent = devices.reduce((n, d) => n + (d.online ? d.ports.length : 0), 0);
}

async function loadDevices() {
  devices = await (await fetch("/api/devices")).json();
  render();
}

async function loadScans() {
  const scans = await (await fetch("/api/scans")).json();
  $("#scans tbody").innerHTML = scans.map((s) => `
    <tr>
      <td>${s.id}</td><td>${fmt(s.started_at)}</td><td>${fmt(s.finished_at)}</td>
      <td class="mono">${esc(s.targets)}</td>
      <td class="st-${s.status}" title="${esc(s.error || "")}">${esc(s.status)}${s.error ? " ⚠" : ""}</td>
      <td>${s.hosts_up}</td>
    </tr>`).join("");
  const last = scans.find((s) => s.status === "done");
  $("#statLast").textContent = last ? fmt(last.finished_at) : "—";
}

async function loadStatus() {
  const s = await (await fetch("/api/status")).json();
  const el = $("#status");
  el.classList.toggle("running", s.running);
  el.textContent = s.running
    ? s.progress
    : `Target: ${s.targets} · scansione automatica ${s.interval_minutes > 0 ? "ogni " + s.interval_minutes + " min" : "disattivata"}`;
  $("#scanBtn").disabled = s.running;
  if (wasRunning && !s.running) { loadDevices(); loadScans(); }
  if (s.running && !wasRunning) loadScans();
  wasRunning = s.running;
}

function openDetail(id) {
  const d = devices.find((x) => x.id === id);
  if (!d) return;
  current = d;
  $("#dTitle").textContent = `${name(d) || d.ip}`;
  const info = { IP: d.ip, MAC: d.mac, Vendor: d.vendor, Hostname: d.hostname, OS: d.os,
    Stato: d.online ? "online" : "offline", "Primo avvistamento": fmt(d.first_seen), "Ultimo avvistamento": fmt(d.last_seen) };
  $("#dInfo").innerHTML = Object.entries(info).filter(([, v]) => v)
    .map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
  $("#dAlias").value = d.alias || "";
  $("#dNotes").value = d.notes || "";
  $("#dPorts").innerHTML = d.ports.length
    ? d.ports.map((p) => `<tr><td class="mono">${p.port}</td><td>${p.protocol}</td><td>${esc(p.service || "")}</td><td>${esc([p.product, p.version].filter(Boolean).join(" "))}</td></tr>`).join("")
    : `<tr><td colspan="4" class="sub">Nessuna porta aperta rilevata</td></tr>`;
  $("#detail").showModal();
}

$("#devices").addEventListener("click", (e) => {
  const tr = e.target.closest("tr[data-id]");
  if (tr) openDetail(Number(tr.dataset.id));
});

// Le due righe di un dispositivo si evidenziano insieme
$("#devices").addEventListener("mouseover", (e) => {
  const tr = e.target.closest("tr[data-id]");
  document.querySelectorAll("#devices tr.hover").forEach((r) => r.classList.remove("hover"));
  if (tr) document.querySelectorAll(`#devices tr[data-id="${tr.dataset.id}"]`).forEach((r) => r.classList.add("hover"));
});
$("#devices").addEventListener("mouseleave", () => {
  document.querySelectorAll("#devices tr.hover").forEach((r) => r.classList.remove("hover"));
});

$("#devices thead").addEventListener("click", (e) => {
  const k = e.target.dataset.sort;
  if (!k) return;
  sortDir = sortKey === k ? -sortDir : 1;
  sortKey = k;
  render();
});

$("#dSave").addEventListener("click", async () => {
  await fetch(`/api/devices/${current.id}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ alias: $("#dAlias").value, notes: $("#dNotes").value }),
  });
  $("#detail").close();
  loadDevices();
});

$("#dDelete").addEventListener("click", async () => {
  if (!confirm("Eliminare il dispositivo dal catalogo?")) return;
  await fetch(`/api/devices/${current.id}`, { method: "DELETE" });
  $("#detail").close();
  loadDevices();
});

$("#scanBtn").addEventListener("click", async () => {
  $("#scanBtn").disabled = true;
  await fetch("/api/scan", { method: "POST" });
  loadStatus();
});

$("#search").addEventListener("input", render);
$("#onlyOnline").addEventListener("change", render);

loadDevices();
loadScans();
loadStatus();
setInterval(loadStatus, 3000);

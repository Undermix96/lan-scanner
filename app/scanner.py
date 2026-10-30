import ipaddress
import logging
import os
import shlex
import subprocess
import threading
import xml.etree.ElementTree as ET

import db

log = logging.getLogger("scanner")

SCAN_TARGETS = os.environ.get("SCAN_TARGETS", "auto")
NMAP_PORT_ARGS = os.environ.get("NMAP_PORT_ARGS", "--top-ports 1000 -sV --version-light -T4")
NMAP_OS_DETECT = os.environ.get("NMAP_OS_DETECT", "false").lower() == "true"
HOST_TIMEOUT = os.environ.get("NMAP_HOST_TIMEOUT", "5m")


class ScanState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.phase = "idle"
        self.progress = ""


state = ScanState()


def detect_networks():
    """Return the IPv4 networks of the host's non-loopback, non-docker interfaces."""
    out = subprocess.run(
        ["ip", "-o", "-4", "addr", "show", "scope", "global"],
        capture_output=True, text=True, check=True,
    ).stdout
    nets = []
    for line in out.splitlines():
        parts = line.split()
        iface, cidr = parts[1], parts[3]
        if iface.startswith(("docker", "br-", "veth", "virbr", "lo", "tun", "wg")):
            continue
        net = ipaddress.ip_interface(cidr).network
        # Avoid scanning gigantic ranges by accident.
        if net.prefixlen < 22:
            log.warning("Network %s on %s is larger than /22, limiting to /24", net, iface)
            net = ipaddress.ip_interface(f"{cidr.split('/')[0]}/24").network
        if str(net) not in nets:
            nets.append(str(net))
    return nets


def resolve_targets():
    if SCAN_TARGETS.strip().lower() == "auto":
        return detect_networks()
    return [t.strip() for t in SCAN_TARGETS.split(",") if t.strip()]


def run_nmap(args):
    cmd = ["nmap", "-oX", "-", *args]
    log.info("Running: %s", " ".join(shlex.quote(c) for c in cmd))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"nmap exited with {proc.returncode}")
    return ET.fromstring(proc.stdout)


def parse_hosts(root):
    hosts = []
    for h in root.findall("host"):
        status = h.find("status")
        if status is None or status.get("state") != "up":
            continue
        host = {"ports": []}
        for addr in h.findall("address"):
            if addr.get("addrtype") == "ipv4":
                host["ip"] = addr.get("addr")
            elif addr.get("addrtype") == "mac":
                host["mac"] = addr.get("addr").upper()
                host["vendor"] = addr.get("vendor")
        if "ip" not in host:
            continue
        hn = h.find("hostnames/hostname")
        if hn is not None:
            host["hostname"] = hn.get("name")
        osmatch = h.find("os/osmatch")
        if osmatch is not None:
            host["os"] = f"{osmatch.get('name')} ({osmatch.get('accuracy')}%)"
        for p in h.findall("ports/port"):
            st = p.find("state")
            if st is None or st.get("state") != "open":
                continue
            svc = p.find("service")
            host["ports"].append({
                "port": int(p.get("portid")),
                "protocol": p.get("protocol"),
                "state": st.get("state"),
                "service": svc.get("name") if svc is not None else None,
                "product": svc.get("product") if svc is not None else None,
                "version": " ".join(
                    v for v in (svc.get("version"), svc.get("extrainfo")) if v
                ) if svc is not None else None,
            })
        hosts.append(host)
    return hosts


def scan():
    """Discover hosts, then port-scan the live ones. Returns False if a scan is already running."""
    with state.lock:
        if state.running:
            return False
        state.running = True

    scan_id = None
    try:
        targets = resolve_targets()
        if not targets:
            raise RuntimeError("No networks to scan (set SCAN_TARGETS)")
        scan_id = db.start_scan(", ".join(targets))

        state.phase = "discovery"
        state.progress = f"Host discovery on {', '.join(targets)}"
        discovered = parse_hosts(run_nmap(["-sn", "-PR", "-PE", "-PS22,80,443,445,3389,8080",
                                           "-PA80,443", *targets]))
        log.info("Discovery found %d hosts", len(discovered))

        state.phase = "ports"
        state.progress = f"Port scan of {len(discovered)} hosts"
        hosts = []
        if discovered:
            ips = [h["ip"] for h in discovered]
            args = ["-Pn", "--host-timeout", HOST_TIMEOUT, *shlex.split(NMAP_PORT_ARGS)]
            if NMAP_OS_DETECT:
                args.append("-O")
            scanned = {h["ip"]: h for h in parse_hosts(run_nmap([*args, *ips]))}
            # Keep MAC/vendor/hostname from discovery when the port scan lacks them.
            for d in discovered:
                s = scanned.get(d["ip"], {"ports": []})
                hosts.append({**d, **{k: v for k, v in s.items() if v}})

        db.save_results(hosts)
        db.finish_scan(scan_id, "done", hosts_up=len(hosts))
        log.info("Scan %s completed: %d hosts", scan_id, len(hosts))
    except Exception as e:
        log.exception("Scan failed")
        if scan_id:
            db.finish_scan(scan_id, "error", error=str(e))
    finally:
        state.running = False
        state.phase = "idle"
        state.progress = ""
    return True


def scan_async():
    if state.running:
        return False
    threading.Thread(target=scan, daemon=True).start()
    return True


def scheduler(interval_minutes):
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            scan()
            stop.wait(interval_minutes * 60)

    threading.Thread(target=loop, daemon=True).start()
    return stop

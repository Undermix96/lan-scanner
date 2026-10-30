import csv
import io
import logging
import os

from flask import Flask, Response, jsonify, render_template, request

import db
import scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_MINUTES", "60"))
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))

app = Flask(__name__)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/devices")
def api_devices():
    return jsonify(db.list_devices())


@app.patch("/api/devices/<int:dev_id>")
def api_update_device(dev_id):
    data = request.get_json(force=True) or {}
    db.update_device(dev_id, alias=data.get("alias") or None, notes=data.get("notes") or None)
    return jsonify(ok=True)


@app.delete("/api/devices/<int:dev_id>")
def api_delete_device(dev_id):
    db.delete_device(dev_id)
    return jsonify(ok=True)


@app.get("/api/scans")
def api_scans():
    return jsonify(db.list_scans())


@app.get("/api/status")
def api_status():
    return jsonify(
        running=scanner.state.running,
        phase=scanner.state.phase,
        progress=scanner.state.progress,
        interval_minutes=SCAN_INTERVAL,
        targets=scanner.SCAN_TARGETS,
    )


@app.post("/api/scan")
def api_scan():
    started = scanner.scan_async()
    return jsonify(started=started), (202 if started else 409)


@app.get("/api/export.csv")
def api_export():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ip", "mac", "vendor", "hostname", "alias", "online", "first_seen",
                "last_seen", "port", "protocol", "service", "product", "version"])
    for d in db.list_devices():
        base = [d["ip"], d["mac"], d["vendor"], d["hostname"], d["alias"], d["online"],
                d["first_seen"], d["last_seen"]]
        if not d["ports"]:
            w.writerow(base + [""] * 5)
        for p in d["ports"]:
            w.writerow(base + [p["port"], p["protocol"], p["service"], p["product"], p["version"]])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=lan-devices.csv"})


def main():
    from waitress import serve

    db.init()
    if SCAN_INTERVAL > 0:
        scanner.scheduler(SCAN_INTERVAL)
    logging.getLogger("main").info("Web UI on http://0.0.0.0:%d", WEB_PORT)
    serve(app, host="0.0.0.0", port=WEB_PORT, threads=8)


if __name__ == "__main__":
    main()

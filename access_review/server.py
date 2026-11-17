"""Tiny web UI (standard library only) for approving or rejecting findings.

Decisions are saved to out/decisions.json. Nothing else is written.
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .agent import savings_summary, write_report

STATIC = Path(__file__).parent / "static"


class App:
    def __init__(self, review, out_dir):
        self.review = review
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.decisions_file = self.out / "decisions.json"
        self.decisions = (json.loads(self.decisions_file.read_text())
                          if self.decisions_file.exists() else {})
        self.ids = {f["id"] for f in review["findings"]}

    def decide(self, fid, decision):
        if fid not in self.ids or decision not in ("approved", "rejected", "pending"):
            raise ValueError("bad id or decision")
        if decision == "pending":
            self.decisions.pop(fid, None)
        else:
            self.decisions[fid] = decision
        self.decisions_file.write_text(json.dumps(self.decisions, indent=2))
        (self.out / "report.md").write_text(write_report(self.review, self.decisions))

    def state(self):
        return {**self.review, "decisions": self.decisions,
                "savings": savings_summary(self.review["findings"], self.decisions)}


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html")
            elif self.path == "/api/review":
                self._send(200, json.dumps(app.state()))
            elif self.path == "/report.md":
                self._send(200, write_report(app.review, app.decisions), "text/markdown")
            else:
                self._send(404, '{"error":"not found"}')

        def do_POST(self):
            if self.path != "/api/decision":
                return self._send(404, '{"error":"not found"}')
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                app.decide(body.get("id"), body.get("decision"))
            except (ValueError, json.JSONDecodeError) as e:
                return self._send(400, json.dumps({"error": str(e)}))
            self._send(200, json.dumps(app.state()))

    return Handler


def serve(review, out_dir, port=8000):
    app = App(review, out_dir)
    (app.out / "report.md").write_text(write_report(review, app.decisions))
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    print(f"Access review UI on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    httpd.serve_forever()

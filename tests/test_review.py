import json
import tempfile
import threading
import unittest
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from access_review.agent import run_review, savings_summary, write_report
from access_review.llm import ClaudeExplainer
from access_review.server import App, make_handler

DATA = Path(__file__).resolve().parent.parent / "data"


def by(review, kind, user=None, app=None):
    return [f for f in review["findings"] if f["kind"] == kind
            and (user is None or f["user_id"] == user)
            and (app is None or f["app_id"] == app)]


class RuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = run_review(DATA)

    def test_orphaned_leaver_flagged_high(self):
        hits = by(self.r, "orphaned", "u004")
        self.assertEqual(len(hits), 3)
        self.assertTrue(all(f["severity"] == "high" for f in hits))

    def test_disabled_user_flagged(self):
        self.assertEqual(len(by(self.r, "orphaned", "u006")), 2)

    def test_service_account_with_leaver_owner(self):
        f = by(self.r, "no_owner", "svc02")[0]
        self.assertEqual(f["facts"]["owner_status"], "left")

    def test_idle_admin(self):
        self.assertTrue(by(self.r, "idle_admin", "u007", "cloud"))
        self.assertTrue(by(self.r, "idle_admin", "u008", "analytics"))

    def test_never_used_and_unused(self):
        self.assertTrue(by(self.r, "never_used", "u005", "design"))
        self.assertTrue(by(self.r, "unused", "u001", "analytics"))

    def test_active_users_not_flagged(self):
        flagged = {f["user_id"] for f in self.r["findings"]}
        for uid in ("u010", "u011", "u013", "u014"):
            self.assertNotIn(uid, flagged)

    def test_app_without_owner(self):
        self.assertTrue(by(self.r, "app_no_owner", app="analytics"))

    def test_sorted_high_first_and_explained(self):
        sev = [f["severity"] for f in self.r["findings"]]
        self.assertEqual(sev, sorted(sev, key={"high": 0, "medium": 1, "low": 2}.get))
        self.assertTrue(all(f["explanation"] and f["suggested_action"]
                            for f in self.r["findings"]))

    def test_inactivity_depends_on_date(self):
        early = run_review(DATA, today=date(2026, 5, 1))
        self.assertFalse(by(early, "unused", "u001", "analytics"))


class SavingsTests(unittest.TestCase):
    def test_totals_and_approved(self):
        r = run_review(DATA)
        fs = r["findings"]
        s = savings_summary(fs)
        self.assertAlmostEqual(s["monthly"], sum(f["monthly_saving"] for f in fs))
        self.assertAlmostEqual(s["annual"], s["monthly"] * 12, places=2)
        self.assertEqual(s["approved_monthly"], 0)
        top = max(fs, key=lambda f: f["monthly_saving"])
        s2 = savings_summary(fs, {top["id"]: "approved"})
        self.assertEqual(s2["approved_monthly"], top["monthly_saving"])

    def test_report_lists_every_item(self):
        r = run_review(DATA)
        text = write_report(r, {r["findings"][0]["id"]: "approved"})
        for f in r["findings"]:
            self.assertIn(f["id"], text)
        self.assertIn("approved", text)
        self.assertIn("changed nothing", text)


class ClaudeModeTests(unittest.TestCase):
    def test_needs_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError):
                ClaudeExplainer()

    def test_parses_reply_and_falls_back(self):
        f = run_review(DATA)["findings"][0]
        from access_review.rules import Finding
        fobj = Finding(**f)
        reply = {"content": [{"type": "text", "text":
                 'Sure: {"explanation": "E", "action": "A"}'}]}
        resp = mock.MagicMock()
        resp.__enter__.return_value = resp
        resp.read.return_value = json.dumps(reply).encode()
        ex = ClaudeExplainer(api_key="test")
        with mock.patch("urllib.request.urlopen", return_value=resp):
            with mock.patch("json.load", return_value=reply):
                self.assertEqual(ex.explain(fobj), ("E", "A"))
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertEqual(ex.explain(fobj)[1], f["suggested_action"])


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_before = {p.name: p.read_text() for p in DATA.glob("*.csv")}
        app = App(run_review(DATA), self.tmp.name)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def post(self, body):
        req = urllib.request.Request(self.base + "/api/decision",
                                     data=json.dumps(body).encode(), method="POST")
        return json.load(urllib.request.urlopen(req))

    def test_decision_saved_and_data_untouched(self):
        state = json.load(urllib.request.urlopen(self.base + "/api/review"))
        fid = state["findings"][0]["id"]
        state = self.post({"id": fid, "decision": "approved"})
        self.assertEqual(state["decisions"][fid], "approved")
        saved = json.loads(Path(self.tmp.name, "decisions.json").read_text())
        self.assertEqual(saved, {fid: "approved"})
        self.assertEqual(self.data_before,
                         {p.name: p.read_text() for p in DATA.glob("*.csv")})

    def test_bad_decision_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.post({"id": "nope", "decision": "approved"})
        self.assertEqual(cm.exception.code, 400)

    def test_ui_served(self):
        html = urllib.request.urlopen(self.base + "/").read().decode()
        self.assertIn("Access Review Agent", html)


if __name__ == "__main__":
    unittest.main()

"""Explainers: turn a finding's facts into a short, plain-English reason.

* MockExplainer  - no key, no network, same output every time (default).
* ClaudeExplainer - calls the Claude API (Messages endpoint) using the key in
  the ANTHROPIC_API_KEY environment variable. Standard library only.

Both return (explanation, suggested_action). The model only writes words;
it cannot approve, revoke or edit anything.
"""
import json
import os
import urllib.request

ACTIONS = {
    "orphaned": "Remove access and reclaim the licence.",
    "no_owner": "Assign an owner, or switch the account off if nobody claims it.",
    "idle_admin": "Remove the admin rights; keep normal access if still needed.",
    "never_used": "Remove the seat; the person can ask again if needed.",
    "unused": "Ask the person if they still need it, then remove the seat.",
    "duplicate": "Keep one membership and remove the extra one.",
    "app_no_owner": "Name a business owner for the app.",
}


class MockExplainer:
    name = "mock"

    def explain(self, f):
        x = f.facts
        who = f"{f.user_name} ({x.get('department', '')})"
        if f.kind == "orphaned":
            text = (f"{who} is marked '{x['user_status']}' but still has access "
                    f"to {f.app_name}. Last login: {x['last_login']}. Access for "
                    "people who are gone is a common way in for attackers.")
        elif f.kind == "no_owner":
            text = (f"Service account '{f.user_name}' can use {f.app_name}"
                    f"{' with admin rights' if x['privileged'] else ''}, but its "
                    f"owner is {x['owner']} ({x['owner_status']}). Nobody is "
                    "responsible if it is misused.")
        elif f.kind == "idle_admin":
            text = (f"{who} is in the admin group '{f.group}' on {f.app_name} "
                    f"but has not logged in for {x['days_since_login']} days. "
                    "Unused admin rights add risk with no benefit.")
        elif f.kind == "never_used":
            text = (f"{who} has a paid {f.app_name} seat "
                    f"({x['seat_cost']:.2f}/month) and has never logged in.")
        elif f.kind == "unused":
            text = (f"{who} last used {f.app_name} {x['days_since_login']} days "
                    f"ago ({x['last_login']}). The seat costs "
                    f"{x['seat_cost']:.2f}/month.")
        elif f.kind == "duplicate":
            text = (f"{who} is in two groups on {f.app_name} ('{f.group}' and "
                    f"'{x['other_group']}'). One is enough.")
        else:
            text = (f"{f.app_name} has no active owner but {x['seats']} "
                    "people have access. Nobody is reviewing who should be in it.")
        return text, ACTIONS[f.kind]


class ClaudeExplainer:
    name = "claude"
    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise RuntimeError("Set ANTHROPIC_API_KEY to use --llm claude")
        self.model = model or os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")
        self.fallback = MockExplainer()

    def explain(self, f):
        prompt = (
            "You are helping an IT team review user access. Explain this flag "
            "in 2 short sentences of plain English for a non-technical "
            "manager, then suggest one action. Do not invent facts.\n"
            f"Flag type: {f.kind}\nSeverity: {f.severity}\nUser: {f.user_name}\n"
            f"App: {f.app_name}\nGroup: {f.group}\nFacts: {json.dumps(f.facts)}\n"
            'Reply as JSON: {"explanation": "...", "action": "..."}')
        body = json.dumps({"model": self.model, "max_tokens": 300,
                           "messages": [{"role": "user", "content": prompt}]})
        req = urllib.request.Request(self.URL, data=body.encode(), headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01",
            "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                text = json.load(r)["content"][0]["text"]
            data = json.loads(text[text.index("{"): text.rindex("}") + 1])
            return data["explanation"], data["action"]
        except Exception:  # network or format problem: never block the review
            return self.fallback.explain(f)


def get_explainer(mode):
    return ClaudeExplainer() if mode == "claude" else MockExplainer()

"""The review agent: load data -> run rules -> explain -> summarise -> report.

It is read-only. It produces findings and a report; a human decides.
"""
from collections import Counter
from datetime import date

from .llm import get_explainer
from .rules import find_issues, load_data

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def run_review(data_dir, llm="mock", today=None):
    today = today or date(2026, 11, 1)  # fixed date so the demo is repeatable
    users, apps, access = load_data(data_dir)
    findings = find_issues(users, apps, access, today)
    explainer = get_explainer(llm)
    for f in findings:
        f.explanation, f.suggested_action = explainer.explain(f)
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.id))
    return {"as_of": today.isoformat(), "llm": explainer.name,
            "counts": {"users": len(users), "apps": len(apps),
                       "grants": len(access)},
            "findings": [f.to_dict() for f in findings]}


def savings_summary(findings, decisions=None):
    """Monthly/annual savings, overall and for items a human approved."""
    decisions = decisions or {}
    total = sum(f["monthly_saving"] for f in findings)
    approved = sum(f["monthly_saving"] for f in findings
                   if decisions.get(f["id"]) == "approved")
    by_app = Counter()
    for f in findings:
        by_app[f["app_name"]] += f["monthly_saving"]
    return {"monthly": round(total, 2), "annual": round(total * 12, 2),
            "approved_monthly": round(approved, 2),
            "approved_annual": round(approved * 12, 2),
            "by_app": {k: round(v, 2) for k, v in by_app.most_common() if v}}


def write_report(review, decisions=None):
    decisions = decisions or {}
    fs = review["findings"]
    s = savings_summary(fs, decisions)
    sev = Counter(f["severity"] for f in fs)
    lines = [
        "# Access review report", "",
        f"As of **{review['as_of']}** - explanations by `{review['llm']}` "
        f"- {review['counts']['users']} users, {review['counts']['apps']} apps, "
        f"{review['counts']['grants']} access grants checked.", "",
        f"**{len(fs)} items flagged:** {sev['high']} high, {sev['medium']} "
        f"medium, {sev['low']} low.", "",
        "## Cost savings", "",
        f"- Possible: **{s['monthly']:.2f}/month** ({s['annual']:.2f}/year)",
        f"- Approved so far: **{s['approved_monthly']:.2f}/month** "
        f"({s['approved_annual']:.2f}/year)", ""]
    for app, v in s["by_app"].items():
        lines.append(f"  - {app}: {v:.2f}/month")
    lines += ["", "## Items", "",
              "| ID | Severity | Type | User | App | Saving/mo | Decision |",
              "|---|---|---|---|---|---|---|"]
    for f in fs:
        lines.append(f"| {f['id']} | {f['severity']} | {f['kind']} | "
                     f"{f['user_name']} | {f['app_name']} | "
                     f"{f['monthly_saving']:.2f} | "
                     f"{decisions.get(f['id'], 'pending')} |")
    lines += ["", "## Why each item was flagged", ""]
    for f in fs:
        lines += [f"**{f['id']} - {f['user_name']} / {f['app_name']}**  ",
                  f"{f['explanation']}  ",
                  f"Suggested: {f['suggested_action']}", ""]
    lines += ["---", "The agent changed nothing. Approved items are a to-do "
              "list for a person with the right access."]
    return "\n".join(lines)

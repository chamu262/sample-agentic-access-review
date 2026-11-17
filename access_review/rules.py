"""Rule checks: plain Python that finds suspicious access.

The rules decide *what* gets flagged. The LLM only explains a flag in plain
words; it never decides whether something is flagged and never changes data.
"""
import csv
from dataclasses import dataclass, field, asdict
from datetime import date
from pathlib import Path

INACTIVE_DAYS = 90          # no login for this long = unused seat
PRIVILEGED_IDLE_DAYS = 30   # admin rights unused for this long = risky


@dataclass
class Finding:
    id: str
    kind: str            # orphaned | unused | never_used | idle_admin | no_owner | duplicate
    severity: str        # high | medium | low
    user_id: str
    user_name: str
    app_id: str
    app_name: str
    group: str
    facts: dict = field(default_factory=dict)
    monthly_saving: float = 0.0
    explanation: str = ""
    suggested_action: str = ""

    def to_dict(self):
        return asdict(self)


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_data(data_dir):
    d = Path(data_dir)
    users = {u["user_id"]: u for u in load_csv(d / "users.csv")}
    apps = {a["app_id"]: a for a in load_csv(d / "apps.csv")}
    access = load_csv(d / "access.csv")
    return users, apps, access


def _days_since(day_str, today):
    if not day_str:
        return None
    return (today - date.fromisoformat(day_str)).days


def find_issues(users, apps, access, today):
    findings = []
    seen_seats = {}  # (user, app) -> first row, to spot paid duplicates

    def add(kind, severity, row, facts, saving=0.0):
        u, a = users[row["user_id"]], apps[row["app_id"]]
        findings.append(Finding(
            id=f"F{len(findings) + 1:03d}", kind=kind, severity=severity,
            user_id=u["user_id"], user_name=u["name"], app_id=a["app_id"],
            app_name=a["name"], group=row["group"], facts=facts,
            monthly_saving=round(saving, 2)))

    for row in access:
        u, a = users[row["user_id"]], apps[row["app_id"]]
        cost = float(a["monthly_cost_per_seat"] or 0)
        privileged = row["group"] in (a["privileged_groups"] or "").split(";")
        idle = _days_since(row["last_login"], today)
        base = {"department": u["department"], "user_status": u["status"],
                "last_login": row["last_login"] or "never",
                "days_since_login": idle, "privileged": privileged,
                "seat_cost": cost}

        key = (row["user_id"], row["app_id"])
        if key in seen_seats:
            add("duplicate", "low", row,
                {**base, "other_group": seen_seats[key]["group"]})
            continue
        seen_seats[key] = row

        # 1. Orphaned: the person has left or is disabled, access still live.
        if u["status"] in ("left", "disabled"):
            add("orphaned", "high", row, base, cost)
            continue
        # 2. Service account with no owner, or owned by someone who left.
        if u["type"] == "service":
            mgr = users.get(u["manager"])
            if not mgr or mgr["status"] != "active":
                sev = "high" if privileged else "medium"
                add("no_owner", sev, row,
                    {**base, "owner": mgr["name"] if mgr else "none",
                     "owner_status": mgr["status"] if mgr else "n/a"})
                continue
        # 3. Admin rights that are not being used.
        if privileged and idle is not None and idle > PRIVILEGED_IDLE_DAYS:
            add("idle_admin", "high", row, base,
                cost if idle > INACTIVE_DAYS else 0.0)
            continue
        # 4. Paid seat never used / not used for a long time.
        if idle is None:
            add("never_used", "medium", row, base, cost)
        elif idle > INACTIVE_DAYS:
            add("unused", "medium" if cost else "low", row, base, cost)

    # 5. Apps with nobody responsible for them (one finding per app).
    for a in apps.values():
        if not a["owner"] or users.get(a["owner"], {}).get("status") != "active":
            findings.append(Finding(
                id=f"F{len(findings) + 1:03d}", kind="app_no_owner",
                severity="medium", user_id="-", user_name="-",
                app_id=a["app_id"], app_name=a["name"], group="-",
                facts={"seats": sum(r["app_id"] == a["app_id"] for r in access),
                       "seat_cost": float(a["monthly_cost_per_seat"] or 0)}))
    return findings

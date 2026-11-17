# data/ - demo input

**Everything here is made up**: people, apps, groups, dates and prices. The demo treats "today" as 2026-11-01.

| File | Columns | What it is |
|---|---|---|
| `users.csv` | user_id, name, department, status (`active`/`left`/`disabled`), manager, type (`human`/`service`) | Everyone who can log in. For a service account, `manager` is its owner. |
| `apps.csv` | app_id, name, owner, monthly_cost_per_seat, privileged_groups | Each app, who owns it, seat price and which groups count as admin (separate several with `;`). |
| `access.csv` | user_id, app_id, group, last_login (YYYY-MM-DD, blank = never) | Who is in which group on which app. |

## Using your own export

Export the same columns from your identity system or licence tool (rename headers to match), put the three files in a folder and run:

```bash
python3 -m access_review --data path/to/folder
```

The agent only reads these files.

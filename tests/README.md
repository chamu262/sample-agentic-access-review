# tests/

`test_review.py` holds 16 unit tests, run with `python3 -m unittest -v` from the repo root. No network or key needed.

- **RuleTests** - each flag fires on the right demo rows, active users stay clean, results are sorted and explained, and the date changes what counts as unused.
- **SavingsTests** - monthly/annual totals, approved-only savings, every item appears in the report.
- **ClaudeModeTests** - Claude mode needs a key, reads a JSON reply, and falls back to mock text when offline (the API call is faked).
- **ServerTests** - starts the web server on a free port, checks a decision is saved, bad input gets a 400, and the input CSVs are unchanged.

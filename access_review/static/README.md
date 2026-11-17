# access_review/static/ - the web page

`index.html` is the whole approval UI: HTML, CSS and a little JavaScript, no build step and no libraries. `server.py` serves it at `/`.

It reads findings from `GET /api/review`, sends each Approve/Reject click to `POST /api/decision`, and links to `/report.md`. Clicking the same button again sets the item back to pending. Tiles at the top show counts and possible vs approved savings; the pills filter by severity or pending.

![Review queue](../../docs/screenshots/01-review-queue.jpg)
![Decisions and savings](../../docs/screenshots/02-decisions-and-savings.jpg)
![Medium filter](../../docs/screenshots/03-medium-filter.jpg)
<img src="../../docs/screenshots/05-mobile.jpg" width="300" alt="Mobile view">

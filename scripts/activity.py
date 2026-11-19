"""Render a rolling contribution dashboard from GitHub's contribution calendar."""

from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PALETTE = ["#293949", "#315e64", "#398881", "#5fbca4", "#9aefd1"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""

def fetch_days(owner, start, now):
    variables = {"login": owner, "from": f"{start}T00:00:00Z",
                 "to": now.isoformat(timespec="seconds")}
    req = Request("https://api.github.com/graphql",
                  data=json.dumps({"query": QUERY, "variables": variables}).encode(),
                  headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                           "Content-Type": "application/json", "User-Agent": "profile-activity"})
    with urlopen(req, timeout=30) as response:
        payload = json.load(response)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"][0]["message"])
    weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return {date.fromisoformat(day["date"]): day["contributionCount"]
            for week in weeks for day in week["contributionDays"]}

def label(x, y, text, size=16, color="#bed1da", weight=400):
    return (f'<text x="{x}" y="{y}" fill="{color}" font-family="Arial,Helvetica,sans-serif" '
            f'font-size="{size}" font-weight="{weight}">{escape(str(text))}</text>')

def draw(counts, end):
    start = end - timedelta(days=364)
    days = [start + timedelta(days=i) for i in range(365)]
    values = [counts[day] for day in days]  # Missing data must not silently become zero.
    total = sum(values)
    active = sum(n > 0 for n in values)
    longest = streak = 0
    for n in values:
        streak = streak + 1 if n else 0
        longest = max(longest, streak)
    date_range = f"{start:%d %b %Y} – {end:%d %b %Y}"
    desc = (f"{total} contributions across {active} days. Longest streak {longest} days. "
            f"{sum(values[-30:])} contributions in the last 30 days. {date_range}.")
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="960" height="480" '
             'viewBox="0 0 960 480" role="img" aria-labelledby="t d">',
             '<title id="t">GitHub contribution activity</title>',
             f'<desc id="d">{desc}</desc>',
             '<rect x="1" y="1" width="958" height="478" rx="20" fill="#101b29" stroke="#354857"/>',
             label(35, 46, "GitHub activity", 28, "#f4f9fa", 700),
             label(654, 44, date_range, 18)]
    metrics = [(total, "Contributions"), (active, "Active days"), (longest, "Longest streak · days"),
               (sum(values[-30:]), "Last 30 days")]
    for i, (value, name) in enumerate(metrics):
        x = 35 + 228 * i
        parts.extend([label(x, 111, value, 42, "#9aefd1", 700), label(x, 139, name, 17)])
    parts.append('<path d="M35 158H925" stroke="#324451"/>')
    monday = start - timedelta(days=start.weekday())
    for day in days:
        col = (day - monday).days // 7
        x, y = 76 + col * 16, 202 + day.weekday() * 15
        if day.day == 1 and col < 52:
            parts.append(label(x, 187, day.strftime("%b"), 13))
        n = counts[day]
        level = sum(n >= boundary for boundary in [1, 3, 6, 12])
        parts.append(f'<rect x="{x}" y="{y}" width="12" height="12" rx="3" fill="{PALETTE[level]}">'
                     f'<title>{day.isoformat()} · {n}</title></rect>')
    for row in [0, 2, 4, 6]:
        parts.append(label(35, 213 + row * 15, WEEKDAYS[row], 13))
    parts.append(label(35, 338, "Daily contributions", 14))
    for i, name in enumerate(["0", "1–2", "3–5", "6–11", "12+"]):
        x = 194 + i * 75
        parts.extend([f'<rect x="{x}" y="327" width="12" height="12" rx="3" fill="{PALETTE[i]}"/>',
                      label(x + 17, 338, name, 13)])
    parts.append('<path d="M35 360H925" stroke="#324451"/>')
    parts.extend([label(35, 390, "Last 12 weeks", 18, "#e9f5f5", 700),
                  label(35, 417, "Contributions per week", 15),
                  label(35, 439, "Current week included", 13, "#95aeb9")])
    weekly = []
    for i in range(12):
        week_start = end - timedelta(days=end.weekday() + (11-i)*7)
        weekly.append(sum(counts.get(week_start + timedelta(days=d), 0)
                          for d in range(7) if week_start + timedelta(days=d) <= end))
    for i, value in enumerate(weekly):
        x = 255 + i*56
        h = 47 * value / max(1, max(weekly))
        parts.append(f'<rect x="{x}" y="{438-max(h,2):.1f}" width="34" height="{max(h,2):.1f}" '
                     f'rx="2" fill="{PALETTE[4] if value else PALETTE[0]}"/>')
        parts.append(label(x, 454, value, 13))
    return "".join(parts) + "</svg>\n"

if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    today = now.date()
    counts = fetch_days(os.environ["GITHUB_REPOSITORY_OWNER"], today - timedelta(days=364), now)
    (ROOT / "assets/activity.svg").write_text(draw(counts, today), encoding="utf-8")

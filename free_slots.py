#!/usr/bin/env python3
"""
free_slots.py

Find open time windows on the "Henry@imatest.com" Google Calendar over the next N days,
excluding: (1) existing events, (2) 15 min before/after each event, (3) times before 08:30 MT
on Mon/Tue/Thu/Fri, (4) times before 09:30 MT on Wed, and (5) weekends.  Results are
translated to an attendee's timezone.

Usage examples:
  python free_slots.py --attendee-tz "America/New_York"
  python free_slots.py --attendee-tz "Europe/London" --days 7 --calendar-id "Henry@imatest.com"
  python free_slots.py --attendee-tz "America/Los_Angeles" --slot-min 30

First time, place your OAuth client file as credentials.json in the same folder. The script will
create token.json after you authenticate.
"""

import argparse
import datetime as dt
import json
import sys
from dataclasses import dataclass
from typing import List, Tuple, Optional

try:
    # Python 3.9+
    from zoneinfo import ZoneInfo
except Exception:
    print("ERROR: This script requires Python 3.9+ (zoneinfo).", file=sys.stderr)
    sys.exit(1)

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

MOUNTAIN_TZ = ZoneInfo("America/Denver")  # Mountain Time (handles DST)
DEFAULT_CALENDAR_ID = "Henry@imatest.com"

@dataclass
class Interval:
    start: dt.datetime  # timezone-aware
    end: dt.datetime    # timezone-aware

    def __post_init__(self):
        if self.end < self.start:
            raise ValueError("Interval end is before start")

def load_credentials() -> Credentials:
    creds = None
    try:
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    except Exception:
        creds = None
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return creds

def rfc3339(dt_obj: dt.datetime) -> str:
    # Google API expects RFC3339 with timezone offset
    return dt_obj.isoformat()

def parse_google_dt(d: dict, tz_fallback: ZoneInfo) -> Tuple[dt.datetime, bool]:
    """Parse a Google Calendar event start/end dict.
    Returns (datetime, is_all_day). If 'date' is present, it's an all-day date (no time)."""
    if "dateTime" in d:
        # Example: 2025-10-04T10:00:00-06:00
        return dt.datetime.fromisoformat(d["dateTime"]), False
    elif "date" in d:
        # All-day: interpret as midnight at tz_fallback, spanning whole day in that zone.
        date = dt.date.fromisoformat(d["date"])
        return dt.datetime.combine(date, dt.time(0, 0)).replace(tzinfo=tz_fallback), True
    else:
        raise ValueError("Unknown event time format: " + json.dumps(d))

def merge_intervals(intervals: List[Interval]) -> List[Interval]:
    if not intervals:
        return []
    intervals_sorted = sorted(intervals, key=lambda x: x.start)
    merged = [intervals_sorted[0]]
    for cur in intervals_sorted[1:]:
        last = merged[-1]
        if cur.start <= last.end:
            # overlap/adjacent
            merged[-1] = Interval(start=last.start, end=max(last.end, cur.end))
        else:
            merged.append(cur)
    return merged

def subtract_intervals(whole: Interval, blocks: List[Interval]) -> List[Interval]:
    """Subtract union of blocks from whole, return free intervals."""
    free = []
    cursor = whole.start
    for b in blocks:
        if b.end <= cursor:
            continue
        if b.start > whole.end:
            break
        start_block = max(b.start, whole.start)
        end_block = min(b.end, whole.end)
        if start_block > cursor:
            free.append(Interval(cursor, start_block))
        cursor = max(cursor, end_block)
    if cursor < whole.end:
        free.append(Interval(cursor, whole.end))
    return free

def clamp_to_day_window(day: dt.date) -> Interval:
    """Create the allowed window in Mountain Time for the given day:
       - Exclude weekends entirely
       - Earliest start 08:30 MT on Mon/Tue/Thu/Fri; 09:30 MT on Wed
       - No upper bound specified (open until 23:59:59.999999 of that day)
    """
    weekday = day.weekday()  # Mon=0 ... Sun=6
    if weekday in (5, 6):  # Sat, Sun
        # Empty window (start==end) to signal "no availability"
        start = dt.datetime.combine(day, dt.time(0, 0, 0), tzinfo=MOUNTAIN_TZ)
        return Interval(start=start, end=start)

    if weekday == 2:  # Wednesday
        start_local = dt.datetime.combine(day, dt.time(9, 30), tzinfo=MOUNTAIN_TZ)
    else:
        start_local = dt.datetime.combine(day, dt.time(8, 30), tzinfo=MOUNTAIN_TZ)

    # End of day at 23:59:59.999999 local time
    end_local = dt.datetime.combine(day, dt.time(23, 59, 59, 999999), tzinfo=MOUNTAIN_TZ)
    return Interval(start_local, end_local)

def expand_with_buffer(intervals: List[Interval], pre_minutes: int = 15, post_minutes: int = 15) -> List[Interval]:
    expanded = []
    delta_pre = dt.timedelta(minutes=pre_minutes)
    delta_post = dt.timedelta(minutes=post_minutes)
    for iv in intervals:
        expanded.append(Interval(iv.start - delta_pre, iv.end + delta_post))
    return merge_intervals(expanded)


def minutes_between(a: dt.datetime, b: dt.datetime) -> int:
    return int((b - a).total_seconds() // 60)

def filter_min_duration(intervals: List[Interval], min_minutes: int) -> List[Interval]:
    return [iv for iv in intervals if minutes_between(iv.start, iv.end) >= min_minutes]

def uses_24h_by_timezone(tz_name: str) -> bool:
    """
    Heuristic for 24-hour clock usage based on IANA timezone region.
    Defaults to 24h unless the zone is commonly 12h in everyday use.
    Common 12-hour locales: US/Canada, UK/Ireland, Australia/NZ, Philippines.
    Users can override via --time-format.
    """
    # Explicit 12-hour common locales
    twelve_hour_prefixes = [
        "America/",            # US, Canada, LatAm (many use 12h in practice)
    ]
    twelve_hour_exact = {
        "Europe/London", "Europe/Dublin",
        "Pacific/Auckland", "Pacific/Chatham",
        "Australia/Sydney", "Australia/Melbourne", "Australia/Brisbane",
        "Australia/Perth", "Australia/Adelaide", "Australia/Darwin",
        "Asia/Manila"
    }
    if tz_name in twelve_hour_exact:
        return False
    if any(tz_name.startswith(p) for p in twelve_hour_prefixes):
        return False
    return True  # everyone else → 24h

def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"

def format_time_range(start: dt.datetime, end: dt.datetime, use_24h: bool) -> str:
    if use_24h:
        s = start.strftime("%H:%M")
        e = end.strftime("%H:%M")
        return f"{s}-{e}"
    # 12-hour with shared am/pm when possible
    s_ampm = start.strftime("%p").lower()
    e_ampm = end.strftime("%p").lower()
    s_time = start.strftime("%-I:%M")
    e_time = end.strftime("%-I:%M")
    if s_ampm == e_ampm:
        return f"{s_time}-{e_time}{s_ampm}"
    else:
        return f"{s_time}{s_ampm}-{e_time}{e_ampm}"

def discretize_slots(free_windows: List[Interval], slot_minutes: int, attendee_tz: ZoneInfo) -> List[Interval]:
    """Turn free windows into fixed-size slots, aligned to the minute (no rounding). Enforces ≥45 minutes."""
    out = []
    min_minutes = max(45, slot_minutes)
    slot_delta = dt.timedelta(minutes=min_minutes)
    for w in free_windows:
        # Work in attendee_tz for slot boundaries
        start_att = w.start.astimezone(attendee_tz)
        end_att = w.end.astimezone(attendee_tz)
        # Only consider windows with at least min_minutes
        if (end_att - start_att) < slot_delta:
            continue
        cursor = start_att
        while cursor + slot_delta <= end_att:
            out.append(Interval(cursor, cursor + slot_delta))
            cursor += slot_delta
    return out

def get_events(service, calendar_id: str, time_min: dt.datetime, time_max: dt.datetime) -> List[dict]:
    events = []
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            timeMin=rfc3339(time_min),
            timeMax=rfc3339(time_max),
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()
        events.extend(resp.get("items", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return events


def compute_availability(attendee_tz_name: str,
                         calendar_id: str = DEFAULT_CALENDAR_ID,
                         days: int = 7,
                         slot_min: int = 0,
                         output: str = "text",
                         time_format_pref: str = "auto",
                         now_override: Optional[str] = None) -> str:
    # --- Begin logic equivalent to main(), but parameterized and returning a string ---
    try:
        attendee_tz = ZoneInfo(attendee_tz_name)
    except Exception as e:
        return f"ERROR: Invalid attendee time zone '{attendee_tz_name}': {e}"

    now_mt = (dt.datetime.fromisoformat(now_override) if now_override else dt.datetime.now(tz=MOUNTAIN_TZ))
    time_min_mt = now_mt
    time_max_mt = now_mt + dt.timedelta(days=days)

    creds = load_credentials()
    try:
        service = build("calendar", "v3", credentials=creds)
    except HttpError as e:
        return f"ERROR building Google Calendar service: {e}"

    events = get_events(service, calendar_id, time_min_mt, time_max_mt)

    busy_raw: List[Interval] = []
    for ev in events:
        start_raw = ev.get("start", {})
        end_raw = ev.get("end", {})
        if not start_raw or not end_raw:
            continue
        start_dt, _ = parse_google_dt(start_raw, MOUNTAIN_TZ)
        end_dt, _ = parse_google_dt(end_raw, MOUNTAIN_TZ)
        start_mt = start_dt.astimezone(MOUNTAIN_TZ)
        end_mt = end_dt.astimezone(MOUNTAIN_TZ)
        if end_mt <= start_mt:
            continue
        busy_raw.append(Interval(start=start_mt, end=end_mt))

    busy_expanded = expand_with_buffer(busy_raw, 15, 15)
    busy_expanded = merge_intervals(busy_expanded)

    day_cursor = time_min_mt.date()
    end_date = time_max_mt.date()

    free_windows_mt: List[Interval] = []
    while day_cursor <= end_date:
        day_window = clamp_to_day_window(day_cursor)
        if day_window.start == day_window.end:
            day_cursor += dt.timedelta(days=1)
            continue
        day_window = Interval(
            start=max(day_window.start, time_min_mt),
            end=min(day_window.end, time_max_mt)
        )
        if day_window.start >= day_window.end:
            day_cursor += dt.timedelta(days=1)
            continue
        day_busy = [b for b in busy_expanded if not (b.end <= day_window.start or b.start >= day_window.end)]
        day_busy = merge_intervals(day_busy)
        free_segments = subtract_intervals(day_window, day_busy)
        free_windows_mt.extend(free_segments)
        day_cursor += dt.timedelta(days=1)

    attendee_tz = ZoneInfo(attendee_tz_name)
    free_windows_att = [Interval(iv.start.astimezone(attendee_tz), iv.end.astimezone(attendee_tz)) for iv in free_windows_mt]
    free_windows_att = filter_min_duration(free_windows_att, 45)

    # Decide time format
    if time_format_pref == "12":
        use_24h = False
    elif time_format_pref == "24":
        use_24h = True
    else:
        use_24h = uses_24h_by_timezone(attendee_tz_name)

    # Discretize if requested
    if slot_min and slot_min > 0:
        slots = discretize_slots(free_windows_att, slot_min, attendee_tz)
        slots = filter_min_duration(slots, 45)
    else:
        slots = []

    if output == "json":
        if slot_min and slot_min > 0:
            free_for_json = [{"start": s.start.isoformat(), "end": s.end.isoformat()} for s in slots]
        else:
            free_for_json = [{"start": iv.start.isoformat(), "end": iv.end.isoformat()} for iv in free_windows_att]
        return json.dumps({
            "calendar_id": calendar_id,
            "attendee_tz": attendee_tz_name,
            "window_start_mt": time_min_mt.isoformat(),
            "window_end_mt": time_max_mt.isoformat(),
            "slot_minutes": slot_min,
            "time_format": "24" if use_24h else "12",
            "free": free_for_json
        }, indent=2)

    # Text output
    from collections import defaultdict
    by_date = defaultdict(list)
    series = (slots if (slot_min and slot_min > 0) else free_windows_att)
    for iv in series:
        local_start = iv.start.astimezone(attendee_tz)
        by_date[local_start.date()].append(iv)

    lines = [f"Availability ({attendee_tz_name}):"]
    for day in sorted(by_date.keys()):
        day_ivs = sorted(by_date[day], key=lambda x: x.start)
        day_dt = dt.datetime.combine(day, dt.time(0,0)).replace(tzinfo=attendee_tz)
        weekday = day_dt.strftime("%A")
        month = day_dt.strftime("%B")
        day_ordinal = ordinal(day_dt.day)
        ranges = [format_time_range(iv.start.astimezone(attendee_tz), iv.end.astimezone(attendee_tz), use_24h) for iv in day_ivs]
        if ranges:
            lines.append(f"{weekday} {month} {day_ordinal}: " + "; ".join(ranges))

    if len(lines) == 1:
        return "No qualifying availability (≥45 minutes) in the requested window."
    return "\n".join(lines)


def launch_gui():
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog

    # Curated common time zones; combobox is also editable for custom entries.
    COMMON_TZS = sorted([
        "America/Denver","America/Los_Angeles","America/Chicago","America/New_York","America/Phoenix",
        "America/Toronto","America/Vancouver","America/Mexico_City","America/Bogota","America/Sao_Paulo",
        "Europe/London","Europe/Dublin","Europe/Paris","Europe/Berlin","Europe/Madrid","Europe/Rome",
        "Europe/Amsterdam","Europe/Zurich","Europe/Stockholm","Europe/Helsinki","Europe/Athens",
        "Europe/Warsaw","Europe/Prague","Europe/Lisbon",
        "Africa/Cairo","Africa/Johannesburg","Africa/Nairobi",
        "Asia/Dubai","Asia/Jerusalem","Asia/Istanbul","Asia/Tehran","Asia/Kolkata","Asia/Bangkok",
        "Asia/Singapore","Asia/Hong_Kong","Asia/Shanghai","Asia/Tokyo","Asia/Seoul",
        "Australia/Sydney","Australia/Melbourne","Australia/Perth","Pacific/Auckland"
    ])

    root = tk.Tk()
    root.title("Free Slots Finder")

    # Vars
    tz_var = tk.StringVar(value="America/New_York")
    cal_var = tk.StringVar(value=DEFAULT_CALENDAR_ID)
    days_var = tk.IntVar(value=7)
    slot_var = tk.IntVar(value=0)
    out_var = tk.StringVar(value="text")
    tf_var = tk.StringVar(value="auto")

    # Layout
    frm = ttk.Frame(root, padding=12)
    frm.grid(row=0, column=0, sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    # Row 0: Calendar ID
    ttk.Label(frm, text="Calendar ID:").grid(row=0, column=0, sticky="w")
    cal_entry = ttk.Entry(frm, textvariable=cal_var, width=40)
    cal_entry.grid(row=0, column=1, columnspan=2, sticky="ew", padx=6, pady=4)

    # Row 1: Time zone
    ttk.Label(frm, text="Attendee Time Zone:").grid(row=1, column=0, sticky="w")
    tz_combo = ttk.Combobox(frm, textvariable=tz_var, values=COMMON_TZS, width=37)
    tz_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=4)
    tz_combo['state'] = 'normal'  # editable for custom TZ

    # Row 2: Days & Slot minutes
    ttk.Label(frm, text="Days ahead:").grid(row=2, column=0, sticky="w")
    days_spin = ttk.Spinbox(frm, from_=1, to=30, textvariable=days_var, width=6)
    days_spin.grid(row=2, column=1, sticky="w", padx=6, pady=4)

    ttk.Label(frm, text="Slot minutes (0 = continuous):").grid(row=2, column=2, sticky="e")
    slot_spin = ttk.Spinbox(frm, from_=0, to=240, increment=5, textvariable=slot_var, width=8)
    slot_spin.grid(row=2, column=3, sticky="w", padx=6, pady=4)

    # Row 3: Output & Time format
    ttk.Label(frm, text="Output:").grid(row=3, column=0, sticky="w")
    out_combo = ttk.Combobox(frm, textvariable=out_var, values=["text","json"], width=10, state="readonly")
    out_combo.grid(row=3, column=1, sticky="w", padx=6, pady=4)

    ttk.Label(frm, text="Time format:").grid(row=3, column=2, sticky="e")
    tf_combo = ttk.Combobox(frm, textvariable=tf_var, values=["auto","12","24"], width=8, state="readonly")
    tf_combo.grid(row=3, column=3, sticky="w", padx=6, pady=4)

    # Buttons
    btns = ttk.Frame(frm)
    btns.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8,4))
    btns.columnconfigure(0, weight=1)
    btns.columnconfigure(1, weight=1)
    btns.columnconfigure(2, weight=1)

    def do_auth():
        try:
            _ = load_credentials()
            messagebox.showinfo("Authentication", "Authentication complete.")
        except Exception as e:
            messagebox.showerror("Authentication Error", str(e))

    def run_availability():
        tz_name = tz_var.get().strip()
        if not tz_name:
            messagebox.showerror("Input Error", "Please enter a valid IANA time zone (e.g., America/New_York).")
            return
        result = compute_availability(
            attendee_tz_name=tz_name,
            calendar_id=cal_var.get().strip(),
            days=days_var.get(),
            slot_min=slot_var.get(),
            output=out_var.get(),
            time_format_pref=tf_var.get(),
            now_override=None
        )
        text.delete("1.0", "end")
        text.insert("1.0", result)

    def copy_to_clipboard():
        data = text.get("1.0", "end").strip()
        root.clipboard_clear()
        root.clipboard_append(data)
        messagebox.showinfo("Copied", "Output copied to clipboard.")

    def save_to_file():
        data = text.get("1.0", "end").strip()
        if not data:
            messagebox.showwarning("No Data", "Nothing to save.")
            return
        fpath = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text","*.txt"),("JSON","*.json"),("All files","*.*")])
        if not fpath:
            return
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(data)
        messagebox.showinfo("Saved", f"Saved to {fpath}")

    auth_btn = ttk.Button(btns, text="Authenticate Google", command=do_auth)
    auth_btn.grid(row=0, column=0, padx=4)

    run_btn = ttk.Button(btns, text="Find Availability", command=run_availability)
    run_btn.grid(row=0, column=1, padx=4)

    copy_btn = ttk.Button(btns, text="Copy Output", command=copy_to_clipboard)
    copy_btn.grid(row=0, column=2, padx=4)

    save_btn = ttk.Button(btns, text="Save Output", command=save_to_file)
    save_btn.grid(row=0, column=3, padx=4)

    # Text output area
    text = tk.Text(frm, width=100, height=30, wrap="word")
    text.grid(row=5, column=0, columnspan=4, sticky="nsew", pady=(8,0))
    scroll = ttk.Scrollbar(frm, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.grid(row=5, column=4, sticky="ns")

    # Expand grid
    for c in range(4):
        frm.columnconfigure(c, weight=1)
    frm.rowconfigure(5, weight=1)

    root.mainloop()



def main():
    parser = argparse.ArgumentParser(description="List open time slots translated to attendee's time zone.")
    parser.add_argument("--attendee-tz", help="IANA time zone for attendee (e.g., 'America/New_York').")
    parser.add_argument("--calendar-id", default=DEFAULT_CALENDAR_ID, help="Calendar ID (default Henry@imatest.com).")
    parser.add_argument("--days", type=int, default=7, help="Look-ahead window in days (default 7).")
    parser.add_argument("--slot-min", type=int, default=0, help="If >0, emit discrete slots of this many minutes.")
    parser.add_argument("--output", choices=["text", "json"], default="text", help="Output format (default text).")
    parser.add_argument("--time-format", choices=["auto", "12", "24"], default="auto", help="Time format preference (default auto).")
    parser.add_argument("--now", default=None, help="Override current time (RFC3339) for testing.")
    parser.add_argument("--gui", action="store_true", help="Launch Tkinter GUI.")
    args = parser.parse_args()

    # Launch GUI if requested or if no attendee TZ was provided
    if args.gui or not args.attendee_tz:
        launch_gui()
        return

    # CLI path
    result = compute_availability(
        attendee_tz_name=args.attendee_tz,
        calendar_id=args.calendar_id,
        days=args.days,
        slot_min=args.slot_min,
        output=args.output,
        time_format_pref=args.time_format,
        now_override=args.now
    )
    print(result)


if __name__ == "__main__":
    main()

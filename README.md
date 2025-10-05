# Free slots
compute open slots on your google calendar

## Quick start

Install dependencies
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

Put your Google OAuth desktop client as credentials.json in the same folder as the script.
(First run will open a browser; a token.json will be saved for future runs.)


Examples
```
# Default: text output, auto 12/24h, continuous windows (≥45 min)
python free_slots.py --attendee-tz "America/New_York"

# Force 24-hour or 12-hour regardless of region
python free_slots.py --attendee-tz "Europe/London" --time-format 24
python free_slots.py --attendee-tz "America/Los_Angeles" --time-format 12

# Discrete, bookable slots (≥45 min). If you pass less than 45, it uses 45 anyway.
python free_slots.py --attendee-tz "Europe/Berlin" --slot-min 30

# JSON output instead of text
python free_slots.py --attendee-tz "America/New_York" --output json
```

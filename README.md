# Free slots
compute open slots on your google calendar

## Quick start

Install dependencies
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

## Google Calendar API Setup

To access your Google Calendar, you need to create OAuth 2.0 credentials:

1. **Go to Google Cloud Console**: Visit [console.cloud.google.com](https://console.cloud.google.com)

2. **Create or select a project**:
   - Click the project dropdown at the top
   - Either select an existing project or click "New Project"
   - Give it a name like "Free Slots Calendar"

3. **Enable the Calendar API**:
   - In the left sidebar, go to "APIs & Services" > "Library"
   - Search for "Google Calendar API"
   - Click on it and press "Enable"

4. **Create OAuth credentials**:
   - Go to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - If prompted, configure the OAuth consent screen first:
     - Choose "External" user type
     - Fill in required fields (app name, user support email, developer email)
     - Add your email to test users
   - For application type, select **"Desktop application"**
   - Give it a name like "Free Slots Desktop"
   - Click "Create"

5. **Download credentials**:
   - Click the download icon next to your newly created OAuth client
   - Save the file as `credentials.json` in the same folder as `free_slots.py`

6. **First run authentication**:
   - Run the script for the first time
   - A browser window will open asking you to sign in to Google
   - Grant permission to access your calendar
   - A `token.json` file will be created automatically for future runs

The script will use your primary calendar by default, or you can specify any calendar ID you have access to. Settings are automatically saved to config.json and used as defaults for subsequent runs.

Examples
```
# Default: text output, auto 12/24h, continuous windows (≥45 min), uses primary calendar
python free_slots.py --attendee-tz "America/New_York"

# Specify a different calendar
python free_slots.py --attendee-tz "America/New_York" --calendar-id "team@company.com"

# Force 24-hour or 12-hour regardless of region
python free_slots.py --attendee-tz "Europe/London" --time-format 24
python free_slots.py --attendee-tz "America/Los_Angeles" --time-format 12

# Discrete, bookable slots (≥45 min). If you pass less than 45, it uses 45 anyway.
python free_slots.py --attendee-tz "Europe/Berlin" --slot-min 30

# JSON output instead of text
python free_slots.py --attendee-tz "America/New_York" --output json

# Launch GUI for interactive use (remembers your settings)
python free_slots.py --gui
```

## Configuration

Settings are automatically saved to `config.json` and persist between runs. You can manually edit this file or let the script create it based on your usage.

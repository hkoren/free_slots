# Free Slots - AI Coding Instructions

## Project Overview
This is a **single-file Python application** (`free_slots.py`) that finds available time slots on a Google Calendar, designed specifically for scheduling meetings with timezone conversion. The core logic revolves around **interval mathematics** and **timezone-aware datetime operations**.

## Architecture & Key Components

### Core Data Structure
- **`Interval` dataclass**: All time calculations use tz-aware `datetime` objects
- **Mountain Time bias**: Owner works in `America/Denver` with specific daily schedules
- **Timezone conversion**: All output converted to attendee's timezone for scheduling
- **Configuration persistence**: Settings stored in `config.json` and used as defaults

### Business Logic Layers
1. **Google Calendar API**: Authentication via `credentials.json` → `token.json` flow
2. **Configuration management**: `config.json` stores calendar ID and user preferences
3. **Schedule constraints**: Hardcoded MT business hours (8:30-17:00, Wed starts 9:30)
4. **Buffer management**: 15-min pre/post buffers around existing events
5. **Interval arithmetic**: Merge overlapping busy times, subtract from available windows
6. **Output formatting**: Text (with locale-aware 12/24h) or JSON

### Critical Functions
- `compute_availability()`: Main business logic, used by both CLI and GUI
- `clamp_to_day_window()`: Enforces MT business hours and excludes weekends  
- `subtract_intervals()`: Core algorithm for finding free time between busy blocks
- `discretize_slots()`: Converts continuous windows to bookable time slots (≥45 min)
- `load_config()`/`save_config()`: Manages persistent settings in `config.json`

## Development Workflows

### Environment Setup
```bash
# Install dependencies (no requirements.txt - manual install)
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

# Project uses Python 3.9+ (requires zoneinfo module)
python --version  # Ensure ≥3.9
```

### Quick Testing
```bash
# Basic functionality test
python free_slots.py --attendee-tz "America/New_York" --days 3

# Test discrete slots and JSON output
python free_slots.py --attendee-tz "Europe/London" --slot-min 60 --output json

# Launch GUI for interactive testing
python free_slots.py --gui
```

### Authentication Setup
1. Place Google OAuth desktop client credentials as `credentials.json`
2. First run opens browser for authorization, saves `token.json`
3. Use `--calendar-id` to test with different calendars
4. Settings automatically saved to `config.json` for persistence

### Time Testing
```bash
# Override current time for reproducible testing
python free_slots.py --attendee-tz "America/New_York" --now "2025-10-06T10:00:00-06:00"
```

## Project-Specific Conventions

### Timezone Handling
- **All internal calculations in Mountain Time**: Business logic assumes `America/Denver`
- **Locale detection heuristic**: `uses_24h_by_timezone()` determines 12/24h format
- **Attendee conversion**: Final output always in attendee's timezone
- **Date boundary logic**: Work windows calculated per-day in MT, then converted

### Time Window Rules
- **Minimum duration**: 45 minutes enforced regardless of `--slot-min` parameter
- **Buffer zones**: 15 minutes before/after existing events (non-configurable)
- **Wednesday exception**: Later start time (9:30 vs 8:30) hardcoded
- **Weekend exclusion**: Sat/Sun return zero-duration intervals

### Code Organization
- **Single-file architecture**: All logic in `free_slots.py` (no modules/packages)
- **Dual interface**: CLI args and Tkinter GUI use same `compute_availability()` core
- **Error handling**: Returns error strings rather than raising exceptions
- **Google API**: Paginated event fetching with RFC3339 datetime formatting

## External Dependencies
- **Google Calendar API**: Requires `google-api-python-client`, `google-auth-*` packages
- **Python 3.9+**: Uses `zoneinfo` module (not `pytz`)
- **Tkinter**: For GUI mode (usually included with Python)

## Integration Points
- **Google OAuth flow**: `credentials.json` → browser → `token.json` persistence
- **Calendar events**: Fetches via Google Calendar API v3, handles all-day events
- **Timezone data**: Relies on system IANA timezone database
- **Output formats**: Text for humans, JSON for API integration

## Key Files
- `free_slots.py`: Single application file containing all logic
- `config.json`: User preferences (auto-generated, gitignored)
- `credentials.json`: Google OAuth client secrets (gitignored, user-provided)
- `token.json`: OAuth access tokens (gitignored, auto-generated)

When modifying this code, preserve the Mountain Time business logic and 45-minute minimum duration rules, as these reflect real scheduling constraints.
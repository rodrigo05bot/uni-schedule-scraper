#!/usr/bin/env python3
"""
Uni Schedule Scraper - Fetches schedule from webstudent.mu-varna.bg
using the official API (no Playwright needed).
"""

import os
import requests
from datetime import datetime, timedelta
from icalendar import Calendar, Event, Alarm
import pytz

# Configuration
TOKEN_URL = "https://tokenendpoint-service.mu-varna.bg/token"
SCHEDULE_URL = "https://webstudent-service.mu-varna.bg/api/study-process/student/schedule"

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Origin": "https://webstudent.mu-varna.bg",
    "Referer": "https://webstudent.mu-varna.bg/",
    "Accept": "application/json, text/plain, */*",
}

# Reminder minutes before event (can be set via env)
REMINDER_MINUTES = int(os.environ.get("REMINDER_MINUTES", "15"))


def login(username: str, password: str) -> str:
    """
    Login to the portal and return the Bearer token.
    """
    payload = {
        "grant_type": "password",
        "username": username,
        "password": password,
        "client_id": "webstudent"
    }
    
    headers = HEADERS.copy()
    headers["Content-Type"] = "application/x-www-form-urlencoded"
    
    response = requests.post(TOKEN_URL, data=payload, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Login failed: {response.status_code} - {response.text}")
    
    data = response.json()
    
    if "access_token" not in data:
        raise Exception(f"No access_token in response: {data}")
    
    print(f"✓ Login successful")
    print(f"  User: {data.get('userName', 'Unknown')}")
    print(f"  Token expires in: {data.get('expires_in', 'Unknown')} seconds")
    
    return data["access_token"]


def fetch_schedule(token: str, start_date: str = None, end_date: str = None) -> list:
    """
    Fetch the schedule using the Bearer token.
    
    Args:
        token: Bearer token from login
        start_date: Start date in YYYY-MM-DD format (default: today)
        end_date: End date in YYYY-MM-DD format (default: 30 days from now)
    
    Returns:
        List of schedule events
    """
    # Default date range: today to 30 days from now
    if not start_date:
        start_date = datetime.now().strftime("%Y-%m-%d")
    if not end_date:
        end_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
    
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    params = {
        "start": start_date,
        "end": end_date
    }
    
    print(f"Fetching schedule from {start_date} to {end_date}...")
    
    response = requests.get(SCHEDULE_URL, headers=headers, params=params)
    
    if response.status_code != 200:
        raise Exception(f"Schedule fetch failed: {response.status_code} - {response.text}")
    
    data = response.json()
    
    # Extract calendar events
    events = []
    if "calendarEvents" in data:
        events = data["calendarEvents"].get("studentScheduleEventItems", [])
    
    print(f"✓ Found {len(events)} events")
    
    return events


def generate_icalendar(events: list) -> str:
    """
    Generate an iCalendar file from events.
    """
    cal = Calendar()
    cal.add('prodid', '-//Uni Schedule Scraper//muv.mihoff.de//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'MU Varna Schedule')
    cal.add('x-wr-timezone', 'Europe/Sofia')
    
    tz = pytz.timezone('Europe/Sofia')
    
    for event_data in events:
        try:
            event = Event()
            
            # Extract fields
            event_id = event_data.get("calendarEventId", "")
            title_bg = event_data.get("fullLessonName", "Untitled")
            title_en = event_data.get("fullLessonNameEN", title_bg)
            start_str = event_data.get("start")
            end_str = event_data.get("end")
            
            # Room and building
            room = event_data.get("roomNumberEN", event_data.get("roomNumber", ""))
            building = event_data.get("buildingEN", event_data.get("building", ""))
            
            # Floor
            floor = event_data.get("floor", "")
            
            # Teacher
            teacher = event_data.get("teacherNameEN", event_data.get("teacherName", ""))
            
            # Lesson type
            lesson_type = event_data.get("lessonTypeEN", event_data.get("lessonType", ""))
            
            # Group
            group = event_data.get("groupNames", "")
            
            # Parse datetime strings
            if start_str:
                start_dt = parse_datetime(start_str)
                if start_dt:
                    event.add('dtstart', start_dt)
            
            if end_str:
                end_dt = parse_datetime(end_str)
                if end_dt:
                    event.add('dtend', end_dt)
            
            # Set summary (title)
            event.add('summary', title_en)
            
            # Generate unique ID
            event.add('uid', f"{event_id}@muv.mihoff.de")
            
            # Description in requested format
            desc_lines = []
            if lesson_type:
                desc_lines.append(f"Activity: {lesson_type}")
            if building:
                desc_lines.append(f"Building: {building}")
            if room:
                desc_lines.append(f"Classroom: {room}")
            if floor:
                desc_lines.append(f"Floor: {floor}")
            if teacher:
                desc_lines.append(f"Lecturer: {teacher}")
            
            # Add UniID at the end for reference
            desc_lines.append(f"UniID: {event_id}")
            
            event.add('description', "\n".join(desc_lines))
            
            # Location: Room, Building
            if room and building:
                event.add('location', f"{room}, {building}")
            elif room or building:
                event.add('location', room or building)
            
            # Add reminder alarm (15 minutes before)
            if REMINDER_MINUTES > 0:
                alarm = Alarm()
                alarm.add('action', 'DISPLAY')
                alarm.add('description', f'Reminder: {title_en}')
                alarm.add('trigger', timedelta(minutes=-REMINDER_MINUTES))
                event.add_component(alarm)
            
            cal.add_component(event)
            print(f"✓ Added event: {title_en} ({start_str})")
            
        except Exception as e:
            print(f"⚠ Error processing event: {e}")
            continue
    
    return cal.to_ical().decode('utf-8')


def parse_datetime(dt_str: str):
    """
    Parse datetime string in ISO format.
    """
    if not dt_str:
        return None
    
    # Try ISO format with timezone
    for fmt in [
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    ]:
        try:
            dt = datetime.strptime(dt_str.replace("+00:00", "Z").replace("+02:00", "Z"), fmt.replace("Z", ""))
            return pytz.utc.localize(dt)
        except ValueError:
            continue
    
    # Try fromisoformat
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except:
        pass
    
    return None


def main():
    """
    Main entry point.
    """
    # Get credentials from environment
    username = os.environ.get("WEBSTUDENT_USER")
    password = os.environ.get("WEBSTUDENT_PASS")
    
    if not username or not password:
        raise Exception("WEBSTUDENT_USER and WEBSTUDENT_PASS environment variables required")
    
    print(f"Starting schedule scraper for user: {username}")
    print(f"Reminder: {REMINDER_MINUTES} minutes before each event")
    print("=" * 50)
    
    # Login
    token = login(username, password)
    
    # Fetch schedule (next 60 days to cover full semester)
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    
    events = fetch_schedule(token, start_date, end_date)
    
    # Generate iCalendar
    print("Generating iCalendar...")
    ical_content = generate_icalendar(events)
    
    # Write to file
    output_file = "schedule.ics"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(ical_content)
    
    print("=" * 50)
    print(f"✓ Schedule saved to {output_file}")
    print(f"  Total events: {len(events)}")
    print(f"  Reminder: {REMINDER_MINUTES} min before each class")


if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
Uni Schedule Scraper - Fetches schedule from webstudent.mu-varna.bg
using the official API with groupIntegrationId parameter.

BREAKTHROUGH: The API accepts a groupIntegrationId parameter!
This allows fetching schedules for ALL 24 groups individually.

DYNAMIC DATE RANGE:
    The scraper automatically calculates the date range:
    - 2 weeks backward from current week
    - 2 weeks forward from current week
    - Always fetches complete weeks (Sunday to Saturday)
    - API format: start/end at 22:00 UTC = 00:00 Bulgaria time (UTC+2)

Usage:
    WEBSTUDENT_USER=<user> WEBSTUDENT_PASS=<pass> python scraper.py
"""

import os
import json
import requests
from datetime import datetime, timedelta
from icalendar import Calendar, Event, Alarm
import pytz

# Configuration
TOKEN_URL = "https://tokenendpoint-service.mu-varna.bg/token"
SCHEDULE_URL = "https://webstudent-service.mu-varna.bg/api/study-process/student/schedule"

# All groups (1-24)
ALL_GROUPS = list(range(1, 25))

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


def fetch_schedule_for_group(token: str, start_date: str, end_date: str, group_id: int) -> list:
    """
    Fetch schedule for a specific group using groupIntegrationId parameter.
    
    This is the BREAKTHROUGH: The API accepts groupIntegrationId to filter by group!
    """
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    # Use fixed time format: 22:00:00.000Z (matches API expectations)
    # 22:00 UTC = 00:00 Bulgaria time (UTC+2)
    start_iso = f"{start_date}T22:00:00.000Z"
    end_iso = f"{end_date}T22:00:00.000Z"
    
    params = {
        "start": start_iso,
        "end": end_iso,
        "groupIntegrationId": group_id  # THE KEY PARAMETER!
    }
    
    print(f"  Fetching group {group_id}...", end=" ")
    
    response = requests.get(SCHEDULE_URL, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"✗ Failed: {response.status_code}")
        return []
    
    data = response.json()
    
    events = []
    if "calendarEvents" in data:
        events = data["calendarEvents"].get("studentScheduleEventItems", [])
    
    print(f"✓ {len(events)} events")
    
    return events


def parse_datetime(dt_str: str):
    """
    Parse datetime string in ISO format.
    """
    if not dt_str:
        return None
    
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
    
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except:
        pass
    
    return None


def generate_json_data(events: list) -> dict:
    """
    Generate JSON data with events and extracted groups.
    Returns dict with 'events' and 'groups' keys.
    """
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    processed_events = []
    groups_found = set()
    
    for event_data in events:
        try:
            event_id = event_data.get("calendarEventId", "")
            title_bg = event_data.get("fullLessonName", "Untitled")
            title_en = event_data.get("fullLessonNameEN", title_bg)
            start_str = event_data.get("start")
            end_str = event_data.get("end")
            
            room = event_data.get("roomNumberEN", event_data.get("roomNumber", ""))
            building = event_data.get("buildingEN", event_data.get("building", ""))
            floor = event_data.get("floor", "")
            teacher = event_data.get("teacherNameEN", event_data.get("teacherName", ""))
            lesson_type = event_data.get("lessonTypeEN", event_data.get("lessonType", ""))
            
            group = event_data.get("groupNames", "")
            if group:
                for g in group.split(','):
                    g = g.strip()
                    if g:
                        groups_found.add(g)
            
            start_dt = parse_datetime(start_str)
            end_dt = parse_datetime(end_str)
            
            if not start_dt or not end_dt:
                continue
            
            def format_time(dt):
                return dt.astimezone(pytz.timezone('Europe/Sofia')).strftime('%H:%M')
            
            processed_events.append({
                "id": event_id,
                "title": title_en,
                "titleBg": title_bg,
                "date": start_dt.astimezone(pytz.timezone('Europe/Sofia')).strftime('%Y-%m-%d'),
                "day": day_names[start_dt.astimezone(pytz.timezone('Europe/Sofia')).weekday()],
                "time": f"{format_time(start_dt)}-{format_time(end_dt)}",
                "start": start_str,
                "end": end_str,
                "type": lesson_type,
                "room": room,
                "building": building,
                "floor": floor,
                "lecturer": teacher,
                "group": group,
                "groups": [g.strip() for g in group.split(',') if g.strip()] if group else []
            })
            
        except Exception as e:
            print(f"⚠ Error processing event for JSON: {e}")
            continue
    
    processed_events.sort(key=lambda e: (e['date'], e['time']))
    # Sort groups numerically if possible, then alphabetically for non-numeric
    def group_sort_key(x):
        try:
            return (0, int(x))
        except ValueError:
            return (1, x)
    sorted_groups = sorted(list(groups_found), key=group_sort_key)
    
    return {
        "events": processed_events,
        "groups": sorted_groups,
        "lastUpdate": datetime.now().isoformat(),
        "totalEvents": len(processed_events),
        "totalGroups": len(sorted_groups)
    }


def generate_icalendar(events: list, calendar_name: str = 'MU Varna Schedule') -> str:
    """
    Generate an iCalendar file from events.
    
    Args:
        events: List of event dictionaries
        calendar_name: Name for the calendar (used in x-wr-calname)
    """
    cal = Calendar()
    cal.add('prodid', '-//Uni Schedule Scraper//muv.mihoff.de//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', calendar_name)
    cal.add('x-wr-timezone', 'Europe/Sofia')
    
    seen_ids = set()
    
    for event_data in events:
        try:
            event_id = event_data.get("calendarEventId", "")
            
            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            
            event = Event()
            
            title_bg = event_data.get("fullLessonName", "Untitled")
            title_en = event_data.get("fullLessonNameEN", title_bg)
            start_str = event_data.get("start")
            end_str = event_data.get("end")
            
            room = event_data.get("roomNumberEN", event_data.get("roomNumber", ""))
            building = event_data.get("buildingEN", event_data.get("building", ""))
            floor = event_data.get("floor", "")
            teacher = event_data.get("teacherNameEN", event_data.get("teacherName", ""))
            lesson_type = event_data.get("lessonTypeEN", event_data.get("lessonType", ""))
            group = event_data.get("groupNames", "")
            
            if start_str:
                start_dt = parse_datetime(start_str)
                if start_dt:
                    event.add('dtstart', start_dt)
            
            if end_str:
                end_dt = parse_datetime(end_str)
                if end_dt:
                    event.add('dtend', end_dt)
            
            event.add('summary', title_en)
            event.add('uid', f"{event_id}@muv.mihoff.de")
            
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
            if group:
                desc_lines.append(f"Group: {group}")
            desc_lines.append(f"UniID: {event_id}")
            
            event.add('description', "\n".join(desc_lines))
            
            if room and building:
                event.add('location', f"{room}, {building}")
            elif room or building:
                event.add('location', room or building)
            
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
    print(f"Fetching ALL {len(ALL_GROUPS)} groups using groupIntegrationId parameter")
    print(f"Reminder: {REMINDER_MINUTES} minutes before each event")
    print("=" * 50)
    
    # Login
    token = login(username, password)
    
    # Calculate date range: 2 weeks back + 2 weeks forward
    # Week starts on Sunday (weekday 6 in Python), ends on Saturday (weekday 5)
    # API expects: start = Sunday 22:00 UTC, end = Saturday 22:00 UTC
    today = datetime.now()
    
    # Find start of current week (Sunday = weekday 6, but Python's weekday() gives 6 for Sunday)
    # Python weekday: Monday=0, Tuesday=1, ..., Saturday=5, Sunday=6
    days_since_sunday = (today.weekday() + 1) % 7  # Convert to: Sunday=0, Monday=1, ...
    current_week_sunday = today - timedelta(days=days_since_sunday)
    
    # 2 weeks back: Go back 2 weeks from current week's Sunday
    start_sunday = current_week_sunday - timedelta(weeks=2)
    
    # 2 weeks forward: From current week, go forward 2 weeks to end of that week (Saturday)
    # End date is the Saturday of the week that is 2 weeks ahead
    end_saturday = current_week_sunday + timedelta(weeks=3) - timedelta(days=1)  # Week 3 Sunday - 1 day = Week 2 Saturday
    
    # Format as date strings
    start_date = start_sunday.strftime("%Y-%m-%d")
    end_date = end_saturday.strftime("%Y-%m-%d")
    
    print(f"\n📊 Dynamic date range: 2 weeks back + 2 weeks forward")
    print(f"  Today: {today.strftime('%Y-%m-%d')} ({today.strftime('%A')})")
    print(f"  Start: {start_date} (Sunday, 2 weeks back)")
    print(f"  End: {end_date} (Saturday, 2 weeks forward)")
    print(f"  Total weeks: ~4 weeks coverage")
    
    print(f"\nFetching schedules for all {len(ALL_GROUPS)} groups...")
    print(f"Date range: {start_date} to {end_date}")
    print()
    
    # Fetch all groups
    all_events = []
    events_by_group = {}
    
    for group_id in ALL_GROUPS:
        events = fetch_schedule_for_group(token, start_date, end_date, group_id)
        all_events.extend(events)
        events_by_group[group_id] = len(events)
    
    print(f"\nProcessing events...")
    
    # Remove duplicates
    seen_ids = set()
    unique_events = []
    for event in all_events:
        event_id = event.get("calendarEventId", "")
        if event_id and event_id not in seen_ids:
            seen_ids.add(event_id)
            unique_events.append(event)
    
    print(f"  Total events fetched: {len(all_events)}")
    print(f"  Unique events (after dedup): {len(unique_events)}")
    
    # Generate iCalendar (main schedule - all events)
    print("\nGenerating iCalendar files...")
    ical_content = generate_icalendar(unique_events, "MU Varna Schedule (All Groups)")
    
    # Write main ICS file
    output_file = "schedule.ics"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(ical_content)
    print(f"  ✓ schedule.ics - {len(unique_events)} events (all groups)")
    
    # Filter events for Group 10 (handle whitespace in groupNames)
    group10_events = [e for e in unique_events 
                      if '10' in [g.strip() for g in e.get('groupNames', '').split(',')]]
    
    # Generate Group 10 schedule (all event types)
    if group10_events:
        ical_group10 = generate_icalendar(group10_events, "MU Varna Schedule - Group 10")
        with open("schedule_group10.ics", "w", encoding="utf-8") as f:
            f.write(ical_group10)
        print(f"  ✓ schedule_group10.ics - {len(group10_events)} events (Group 10)")
    
    # Filter exercises for Group 10 (note: API uses "Excercise" with typo)
    exercises_group10 = [e for e in group10_events 
                         if e.get('lessonTypeEN', e.get('lessonType', '')) == 'Excercise']
    
    if exercises_group10:
        ical_exercises = generate_icalendar(exercises_group10, "MU Varna Exercises - Group 10")
        with open("schedule_exercises_group10.ics", "w", encoding="utf-8") as f:
            f.write(ical_exercises)
        print(f"  ✓ schedule_exercises_group10.ics - {len(exercises_group10)} exercises (Group 10)")
    
    # Filter lectures for Group 10
    lectures_group10 = [e for e in group10_events 
                        if e.get('lessonTypeEN', e.get('lessonType', '')) == 'Lecture']
    
    if lectures_group10:
        ical_lectures = generate_icalendar(lectures_group10, "MU Varna Lectures - Group 10")
        with open("schedule_lectures_group10.ics", "w", encoding="utf-8") as f:
            f.write(ical_lectures)
        print(f"  ✓ schedule_lectures_group10.ics - {len(lectures_group10)} lectures (Group 10)")
    
    # Generate JSON data
    print("\nGenerating JSON data...")
    json_data = generate_json_data(unique_events)
    
    # Write schedule.json
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Write groups.json
    groups_data = {
        "groups": json_data["groups"],
        "lastUpdate": json_data["lastUpdate"],
        "eventsByGroup": events_by_group,
        "totalGroups": len(ALL_GROUPS),
        "fetchedGroups": len([g for g in events_by_group.values() if g > 0])
    }
    with open("groups.json", "w", encoding="utf-8") as f:
        json.dump(groups_data, f, indent=2, ensure_ascii=False)
    
    print("=" * 50)
    print("✓ Files generated:")
    print(f"  - schedule.ics ({len(unique_events)} events, all groups)")
    print(f"  - schedule_group10.ics ({len(group10_events)} events, Group 10)")
    print(f"  - schedule_exercises_group10.ics ({len(exercises_group10)} exercises, Group 10)")
    print(f"  - schedule_lectures_group10.ics ({len(lectures_group10)} lectures, Group 10)")
    print(f"  - schedule.json (full event data)")
    print(f"  - groups.json (group metadata)")
    print(f"  Total unique events: {len(unique_events)}")
    print(f"  Total groups: {json_data['totalGroups']}")
    print(f"  Groups with events: {groups_data['fetchedGroups']}/{groups_data['totalGroups']}")
    
    if json_data['groups']:
        print(f"  Groups found: {', '.join(json_data['groups'][:10])}{'...' if len(json_data['groups']) > 10 else ''}")
    print(f"  Reminder: {REMINDER_MINUTES} min before each class")


if __name__ == "__main__":
    main()
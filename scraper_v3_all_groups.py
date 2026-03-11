#!/usr/bin/env python3
"""
Uni Schedule Scraper v3 - Fetches ALL groups using groupIntegrationId parameter.

BREAKTHROUGH: The API accepts a groupIntegrationId parameter!
This allows fetching schedules for ALL 24 groups individually.

Usage:
    WEBSTUDENT_USER=mh11024691 WEBSTUDENT_PASS='x2,bqseW' python scraper_v3_all_groups.py
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
ALL_GROUPS = list(range(1, 25))  # Groups 1-24

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Origin": "https://webstudent.mu-varna.bg",
    "Referer": "https://webstudent.mu-varna.bg/",
    "Accept": "application/json, text/plain, */*",
}

# Reminder minutes before event
REMINDER_MINUTES = int(os.environ.get("REMINDER_MINUTES", "15"))


def login(username: str, password: str) -> str:
    """Login and return Bearer token."""
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
    
    return data["access_token"]


def fetch_schedule_for_group(token: str, start_date: str, end_date: str, group_id: int) -> list:
    """
    Fetch schedule for a specific group using groupIntegrationId parameter.
    
    API Endpoint: 
    https://webstudent-service.mu-varna.bg/api/study-process/student/schedule?start=...&end=...&groupIntegrationId=X
    """
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    # Convert dates to ISO format with timezone
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Format as ISO strings with timezone (UTC)
    start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    params = {
        "start": start_iso,
        "end": end_iso,
        "groupIntegrationId": group_id
    }
    
    print(f"  Fetching group {group_id}...", end=" ")
    
    response = requests.get(SCHEDULE_URL, headers=headers, params=params)
    
    if response.status_code != 200:
        print(f"✗ Failed: {response.status_code}")
        return []
    
    data = response.json()
    
    # Extract events
    events = []
    if "calendarEvents" in data:
        events = data["calendarEvents"].get("studentScheduleEventItems", [])
    
    print(f"✓ {len(events)} events")
    
    return events


def parse_datetime(dt_str: str):
    """Parse datetime string in ISO format."""
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


def generate_json_data(events: list, group_id: int = None) -> dict:
    """Generate JSON data with events."""
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
            
            # Room, building, floor
            room = event_data.get("roomNumberEN", event_data.get("roomNumber", ""))
            building = event_data.get("buildingEN", event_data.get("building", ""))
            floor = event_data.get("floor", "")
            
            # Teacher
            teacher = event_data.get("teacherNameEN", event_data.get("teacherName", ""))
            
            # Lesson type
            lesson_type = event_data.get("lessonTypeEN", event_data.get("lessonType", ""))
            
            # Group from event
            group = event_data.get("groupNames", "")
            if group:
                for g in group.split(','):
                    g = g.strip()
                    if g:
                        groups_found.add(g)
            
            # Tag with group_id if provided
            if group_id and not group:
                group = str(group_id)
            
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
                "groups": [g.strip() for g in group.split(',') if g.strip()] if group else [],
                "fetchedForGroup": group_id
            })
            
        except Exception as e:
            print(f"⚠ Error processing event: {e}")
            continue
    
    processed_events.sort(key=lambda e: (e['date'], e['time']))
    sorted_groups = sorted(list(groups_found), key=lambda x: int(x) if x.isdigit() else x)
    
    return {
        "events": processed_events,
        "groups": sorted_groups,
        "lastUpdate": datetime.now().isoformat(),
        "totalEvents": len(processed_events),
        "totalGroups": len(sorted_groups)
    }


def generate_icalendar(events: list) -> str:
    """Generate iCalendar file from events."""
    cal = Calendar()
    cal.add('prodid', '-//Uni Schedule Scraper v3//muv.mihoff.de//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'MU Varna Schedule (All Groups)')
    cal.add('x-wr-timezone', 'Europe/Sofia')
    
    # Track unique events by ID
    seen_ids = set()
    
    for event_data in events:
        try:
            event_id = event_data.get("calendarEventId", "")
            
            # Skip duplicates (same event can appear in multiple groups)
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
            
        except Exception as e:
            print(f"⚠ Error processing event: {e}")
            continue
    
    return cal.to_ical().decode('utf-8')


def main():
    """Main entry point."""
    # Get credentials from environment or use defaults
    username = os.environ.get("WEBSTUDENT_USER", "mh11024691")
    password = os.environ.get("WEBSTUDENT_PASS", "x2,bqseW")
    
    if not username or not password:
        raise Exception("WEBSTUDENT_USER and WEBSTUDENT_PASS environment variables required")
    
    print(f"=" * 60)
    print(f"Uni Schedule Scraper v3 - All Groups")
    print(f"=" * 60)
    print(f"User: {username}")
    print(f"Groups: 1-{len(ALL_GROUPS)}")
    print(f"Reminder: {REMINDER_MINUTES} min before each event")
    print(f"=" * 60)
    
    # Login
    print("\n[1] Logging in...")
    token = login(username, password)
    
    # Date range: now to 60 days
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    
    print(f"\n[2] Fetching schedules for all {len(ALL_GROUPS)} groups...")
    print(f"    Date range: {start_date} to {end_date}")
    print()
    
    # Fetch all groups
    all_events = []
    events_by_group = {}
    
    for group_id in ALL_GROUPS:
        events = fetch_schedule_for_group(token, start_date, end_date, group_id)
        
        # Tag events with their fetched group
        for event in events:
            event['_fetchedForGroup'] = group_id
        
        all_events.extend(events)
        events_by_group[group_id] = len(events)
    
    print(f"\n[3] Processing events...")
    
    # Remove duplicates (same event can appear in multiple groups)
    seen_ids = set()
    unique_events = []
    for event in all_events:
        event_id = event.get("calendarEventId", "")
        if event_id and event_id not in seen_ids:
            seen_ids.add(event_id)
            unique_events.append(event)
    
    print(f"  Total events fetched: {len(all_events)}")
    print(f"  Unique events (after dedup): {len(unique_events)}")
    
    # Generate JSON
    print(f"\n[4] Generating output files...")
    json_data = generate_json_data(unique_events)
    
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ schedule.json ({len(unique_events)} events)")
    
    # Generate iCalendar
    ical_content = generate_icalendar(unique_events)
    with open("schedule.ics", "w", encoding="utf-8") as f:
        f.write(ical_content)
    print(f"  ✓ schedule.ics")
    
    # Generate groups.json with stats
    groups_data = {
        "groups": json_data["groups"],
        "lastUpdate": json_data["lastUpdate"],
        "eventsByGroup": events_by_group,
        "totalGroups": len(ALL_GROUPS),
        "fetchedGroups": len([g for g in events_by_group.values() if g > 0])
    }
    with open("groups.json", "w", encoding="utf-8") as f:
        json.dump(groups_data, f, indent=2, ensure_ascii=False)
    print(f"  ✓ groups.json")
    
    # Summary
    print(f"\n" + "=" * 60)
    print(f"SUMMARY")
    print(f"=" * 60)
    print(f"  Total groups: {len(ALL_GROUPS)}")
    print(f"  Groups with events: {groups_data['fetchedGroups']}")
    print(f"  Total events: {len(unique_events)}")
    print(f"  Unique groups found: {len(json_data['groups'])}")
    if json_data['groups']:
        print(f"  Groups: {', '.join(json_data['groups'][:15])}{'...' if len(json_data['groups']) > 15 else ''}")
    
    # Events per group
    print(f"\n  Events per group:")
    empty_groups = []
    for group_id in sorted(events_by_group.keys()):
        count = events_by_group[group_id]
        if count == 0:
            empty_groups.append(group_id)
        print(f"    Group {group_id:2d}: {count:3d} events")
    
    if empty_groups:
        print(f"\n  ⚠ Groups with 0 events: {empty_groups}")
    
    print(f"\n✓ Done!")


if __name__ == "__main__":
    main()
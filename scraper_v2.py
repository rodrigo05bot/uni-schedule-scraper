#!/usr/bin/env python3
"""
Uni Schedule Scraper v2 - Enhanced version with group filtering support.

This version attempts to fetch schedules for ALL groups, not just the
logged-in user's groups.

CHANGES FROM v1:
- Added groupId parameter support for the API
- Added fallback to fetch all groups if available
- Enhanced logging to show which groups are being fetched
- Better error handling for group-specific requests
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

# Alternative endpoints to try (for group-specific schedules)
ALTERNATIVE_ENDPOINTS = [
    # Try these for group-specific schedules
    "https://webstudent-service.mu-varna.bg/api/study-process/groups/{group_id}/schedule",
    "https://webstudent-service.mu-varna.bg/api/schedule/group/{group_id}",
    "https://webstudent-service.mu-varna.bg/api/study-process/groups/schedule",
]

# Headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Origin": "https://webstudent.mu-varna.bg",
    "Referer": "https://webstudent.mu-varna.bg/",
    "Accept": "application/json, text/plain, */*",
}

# Reminder minutes before event (can be set via env)
REMINDER_MINUTES = int(os.environ.get("REMINDER_MINUTES", "15"))


def login(username: str, password: str) -> dict:
    """
    Login to the portal and return the Bearer token and user info.
    
    Returns dict with:
        - access_token: Bearer token
        - user_name: Username from login response
        - (potential) group_assignment: If available in response
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
    
    return data


def fetch_schedule_with_group(token: str, start_date: str, end_date: str, group_id: str = None) -> list:
    """
    Fetch the schedule using the Bearer token, optionally filtered by group.
    
    Args:
        token: Bearer token from login
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        group_id: Optional group ID to filter by
    
    Returns:
        List of schedule events
    """
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    # Base params
    params = {
        "start": start_date,
        "end": end_date
    }
    
    # Try adding group parameter if specified
    if group_id:
        params["groupId"] = group_id
    
    print(f"Fetching schedule from {start_date} to {end_date}" + 
          (f" for group {group_id}" if group_id else ""))
    
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


def try_all_groups_endpoint(token: str, start_date: str, end_date: str) -> list:
    """
    Try alternative endpoints that might return all groups' schedules.
    
    Returns:
        List of events if successful, empty list otherwise
    """
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    params = {
        "start": start_date,
        "end": end_date
    }
    
    for endpoint in ALTERNATIVE_ENDPOINTS:
        url = endpoint.format(group_id="all") if "{group_id}" in endpoint else endpoint
        print(f"  Trying: {url}")
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "calendarEvents" in data:
                    events = data["calendarEvents"].get("studentScheduleEventItems", [])
                    print(f"  ✓ SUCCESS: Found {len(events)} events")
                    return events
        except Exception as e:
            print(f"  ✗ Failed: {e}")
    
    return []


def fetch_student_info(token: str) -> dict:
    """
    Try to fetch student info which might contain group assignment.
    
    Returns:
        Student info dict or empty dict if not available
    """
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {token}"
    
    # Try various endpoints that might return student info
    info_endpoints = [
        "https://webstudent-service.mu-varna.bg/api/study-process/student/info",
        "https://webstudent-service.mu-varna.bg/api/study-process/student/profile",
        "https://webstudent-service.mu-varna.bg/api/user/info",
    ]
    
    for endpoint in info_endpoints:
        try:
            response = requests.get(endpoint, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                print(f"  Found student info at: {endpoint}")
                return data
        except Exception as e:
            pass
    
    return {}


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
            # Extract all fields
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
            
            # Group (extract and track)
            group = event_data.get("groupNames", "")
            if group:
                # Group can be comma-separated, split and add each
                for g in group.split(','):
                    g = g.strip()
                    if g:
                        groups_found.add(g)
            
            # Parse datetime
            start_dt = parse_datetime(start_str)
            end_dt = parse_datetime(end_str)
            
            if not start_dt or not end_dt:
                continue
            
            # Format times
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
    
    # Sort events by date and time
    processed_events.sort(key=lambda e: (e['date'], e['time']))
    
    # Sort groups numerically
    sorted_groups = sorted(list(groups_found), key=lambda x: int(x) if x.isdigit() else x)
    
    return {
        "events": processed_events,
        "groups": sorted_groups,
        "lastUpdate": datetime.now().isoformat(),
        "totalEvents": len(processed_events),
        "totalGroups": len(sorted_groups)
    }


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
            
            # Group (NEW: extract and save group info)
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
            
            # Description in requested format (NOW WITH GROUP)
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


def analyze_group_coverage(events: list) -> dict:
    """
    Analyze which groups have events and identify gaps.
    
    Returns:
        Dict with group coverage info
    """
    # Collect all groups from events
    groups_with_events = set()
    lectures = []
    exercises = []
    
    for event in events:
        group_names = event.get("groupNames", "")
        groups = [g.strip() for g in group_names.split(',') if g.strip()]
        groups_with_events.update(groups)
        
        if event.get("lessonTypeEN", event.get("lessonType", "")) == "Lecture":
            lectures.append(event)
        else:
            exercises.append(event)
    
    # Count events per group
    group_event_counts = {}
    for group in groups_with_events:
        count = sum(1 for e in events if group in [g.strip() for g in e.get("groupNames", "").split(',')])
        group_event_counts[group] = count
    
    # Identify expected groups (1-24 for medical students)
    expected_groups = set(str(i) for i in range(1, 25))
    missing_groups = expected_groups - groups_with_events
    
    return {
        "groups_found": sorted(list(groups_with_events), key=lambda x: int(x) if x.isdigit() else x),
        "groups_with_exercises": [],
        "missing_groups": sorted(list(missing_groups), key=lambda x: int(x) if x.isdigit() else x),
        "event_counts_per_group": group_event_counts,
        "total_lectures": len(lectures),
        "total_exercises": len(exercises),
        "lectures_cover_all_groups": len(set(str(i) for i in range(1, 25)) & groups_with_events) == 24
    }


def main():
    """
    Main entry point.
    """
    # Get credentials from environment
    username = os.environ.get("WEBSTUDENT_USER")
    password = os.environ.get("WEBSTUDENT_PASS")
    
    if not username or not password:
        raise Exception("WEBSTUDENT_USER and WEBSTUDENT_PASS environment variables required")
    
    print(f"Starting schedule scraper v2 for user: {username}")
    print(f"Reminder: {REMINDER_MINUTES} minutes before each event")
    print("=" * 50)
    
    # Login
    login_data = login(username, password)
    token = login_data["access_token"]
    
    # Fetch schedule (next 60 days to cover full semester)
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=60)).strftime("%Y-%m-%d")
    
    # First, try the standard schedule endpoint
    print("\n[Step 1] Fetching standard schedule...")
    events = fetch_schedule_with_group(token, start_date, end_date)
    
    # Analyze group coverage
    print("\n[Step 2] Analyzing group coverage...")
    coverage = analyze_group_coverage(events)
    
    print(f"  Groups found: {len(coverage['groups_found'])}")
    print(f"  Missing groups: {coverage['missing_groups'] or 'None'}")
    print(f"  Total lectures: {coverage['total_lectures']}")
    print(f"  Total exercises: {coverage['total_exercises']}")
    
    if coverage['missing_groups']:
        print(f"\n⚠ WARNING: Some groups have no events: {coverage['missing_groups']}")
        print("  This might indicate the API only returns events for the logged-in user's groups.")
    
    # Try to fetch student info (might contain group assignment)
    print("\n[Step 3] Fetching student info...")
    student_info = fetch_student_info(token)
    if student_info:
        print(f"  Student info available: {list(student_info.keys())[:5]}...")
    else:
        print("  No additional student info endpoint available.")
    
    # Try alternative endpoints for all groups
    if coverage['missing_groups']:
        print("\n[Step 4] Trying alternative endpoints for all groups...")
        alt_events = try_all_groups_endpoint(token, start_date, end_date)
        if alt_events:
            events = alt_events
            coverage = analyze_group_coverage(events)
            print(f"  Updated groups: {len(coverage['groups_found'])}")
    
    # Generate iCalendar
    print("\n[Step 5] Generating iCalendar...")
    ical_content = generate_icalendar(events)
    
    # Write ICS file
    output_file = "schedule.ics"
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(ical_content)
    
    # Generate JSON data (events + groups)
    print("\n[Step 6] Generating JSON data...")
    json_data = generate_json_data(events)
    
    # Write schedule.json
    with open("schedule.json", "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    
    # Write groups.json (simple list for easy API access)
    with open("groups.json", "w", encoding="utf-8") as f:
        json.dump({
            "groups": json_data["groups"],
            "lastUpdate": json_data["lastUpdate"]
        }, f, indent=2, ensure_ascii=False)
    
    # Write coverage analysis
    with open("group_coverage.json", "w", encoding="utf-8") as f:
        json.dump(coverage, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 50)
    print(f"✓ Schedule saved to {output_file}")
    print(f"✓ JSON data saved to schedule.json")
    print(f"✓ Groups saved to groups.json")
    print(f"✓ Coverage analysis saved to group_coverage.json")
    print(f"  Total events: {len(events)}")
    print(f"  Total groups: {json_data['totalGroups']}")
    if json_data['groups']:
        print(f"  Groups found: {', '.join(json_data['groups'][:10])}{'...' if len(json_data['groups']) > 10 else ''}")
    print(f"  Reminder: {REMINDER_MINUTES} min before each class")
    
    # Final warning if groups are missing
    if coverage['missing_groups']:
        print(f"\n⚠ FINAL WARNING: {len(coverage['missing_groups'])} groups have no events!")
        print("  This indicates the API only returns events for specific groups.")
        print("  Consider using multiple accounts or finding a public schedule API.")


if __name__ == "__main__":
    main()
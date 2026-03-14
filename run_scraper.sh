#!/bin/bash
#
# Wrapper script for uni-schedule-scraper
# - Ensures log file exists
# - Runs scraper with proper environment
# - Health check on output files
# - Notifications on failure
#
# Usage: ./run_scraper.sh [--no-notify]
#

set -e

SCRIPT_DIR="/root/.openclaw/workspace/uni-schedule-scraper"
SCRAPER_SCRIPT="$SCRIPT_DIR/scraper.py"
ENV_FILE="$SCRIPT_DIR/.env"
LOG_FILE="$SCRIPT_DIR/scraper.log"
PYTHON="/usr/bin/python3"

# Minimum age in seconds for health check (5 minutes = 300 seconds)
MAX_FILE_AGE_SECONDS=300

# Notification function
send_notification() {
    local message="$1"
    local priority="${2:-high}"
    
    # Log the notification
    log_message "NOTIFICATION: $message"
    
    # Try to send via OpenClaw gateway if available
    if command -v curl &> /dev/null; then
        # Check if notification script exists
        local notify_script="/root/.openclaw/workspace/notify.sh"
        if [ -x "$notify_script" ]; then
            "$notify_script" "$message" 2>/dev/null || true
        fi
    fi
}

# Log function with timestamp
log_message() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S %Z')
    echo "[$timestamp] $1" >> "$LOG_FILE"
}

# Health check: verify ICS files were updated recently
health_check() {
    local now=$(date +%s)
    local files=("schedule.ics" "schedule_group10.ics" "schedule_exercises_group10.ics" "schedule_lectures_group10.ics" "schedule.json" "groups.json")
    local failed=0
    
    for file in "${files[@]}"; do
        local filepath="$SCRIPT_DIR/$file"
        if [ ! -f "$filepath" ]; then
            log_message "❌ Health check FAILED: $file does not exist"
            failed=1
            continue
        fi
        
        local file_mtime=$(stat -c %Y "$filepath" 2>/dev/null || echo "0")
        local age=$((now - file_mtime))
        
        if [ $age -gt $MAX_FILE_AGE_SECONDS ]; then
            local age_minutes=$((age / 60))
            log_message "⚠️ Health check WARNING: $file is ${age_minutes} minutes old"
        else
            log_message "✓ Health check OK: $file updated $(stat -c %y "$filepath" | cut -d. -f1)"
        fi
    done
    
    return $failed
}

# Ensure log file exists
ensure_log_file() {
    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE"
        chmod 644 "$LOG_FILE"
        log_message "Log file created"
    fi
}

# Main execution
main() {
    ensure_log_file
    
    log_message "=========================================="
    log_message "Starting hourly scraper run"
    log_message "Working directory: $SCRIPT_DIR"
    log_message "Python: $PYTHON"
    
    # Check if .env exists
    if [ ! -f "$ENV_FILE" ]; then
        log_message "❌ FATAL: .env file not found at $ENV_FILE"
        send_notification "URGENT: Scraper failed - .env file missing!" "critical"
        exit 1
    fi
    
    # Check if scraper script exists
    if [ ! -f "$SCRAPER_SCRIPT" ]; then
        log_message "❌ FATAL: scraper.py not found at $SCRAPER_SCRIPT"
        send_notification "URGENT: Scraper failed - scraper.py missing!" "critical"
        exit 1
    fi
    
    # Check if python exists
    if [ ! -x "$PYTHON" ]; then
        log_message "❌ FATAL: Python not found at $PYTHON"
        send_notification "URGENT: Scraper failed - Python not found!" "critical"
        exit 1
    fi
    
    # Change to script directory
    cd "$SCRIPT_DIR"
    
    # Run the scraper with environment
    log_message "Running scraper..."
    
    if set -a && source "$ENV_FILE" && set +a && "$PYTHON" "$SCRAPER_SCRIPT" >> "$LOG_FILE" 2>&1; then
        log_message "✓ Scraper completed successfully"
        
        # Health check
        if health_check; then
            log_message "✓ All health checks passed"
            exit 0
        else
            log_message "⚠️ Some health checks failed, but scraper ran"
            send_notification "Scraper ran but some output files may be stale" "warning"
            exit 0
        fi
    else
        local exit_code=$?
        log_message "❌ Scraper FAILED with exit code $exit_code"
        
        # Show last 20 lines of log for debugging
        log_message "Last 20 lines of output:"
        tail -20 "$LOG_FILE" | while IFS= read -r line; do
            log_message "  $line"
        done
        
        send_notification "URGENT: Scraper failed (exit code $exit_code). Check $LOG_FILE" "critical"
        exit $exit_code
    fi
}

# Run main with all arguments
main "$@"
#!/usr/bin/env bash
# Server-side deploy: backup -> pull -> restart -> health check -> rollback.
set -euo pipefail

TARGET_COMMIT="${1:?usage: deploy_remote.sh <commit> [app_dir] [service] [branch]}"
APP_DIR="${2:-/home/loktionov/ttn_bot}"
SERVICE="${3:-ttn_bot.service}"
BRANCH="${4:-main}"

log() {
    printf '[deploy] %s\n' "$*"
}

fail() {
    printf '[deploy] ERROR: %s\n' "$*" >&2
    exit 1
}

cd "$APP_DIR" || fail "cannot cd to $APP_DIR"
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || fail "$APP_DIR is not a git repository"

if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    git status --short
    fail "tracked files are modified in $APP_DIR"
fi

if [ -x "$APP_DIR/venv/bin/python3" ]; then
    PYTHON="$APP_DIR/venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
else
    fail "python3 not found"
fi

PREV_COMMIT="$(git rev-parse HEAD)"
log "current commit: $PREV_COMMIT"

# 1. Backup and verify before changing code.
log "creating backup"
if ! BACKUP_OUTPUT="$("$PYTHON" backup.py 2>&1)"; then
    printf '%s\n' "$BACKUP_OUTPUT"
    fail "backup failed; deploy aborted"
fi
printf '%s\n' "$BACKUP_OUTPUT"
BACKUP_DIR="$(printf '%s\n' "$BACKUP_OUTPUT" | grep -o 'backup/[0-9][0-9-]*' | tail -n 1 || true)"
log "backup ready: ${BACKUP_DIR:-unknown}"

# 2. Pull only fast-forward changes.
log "fetching origin/$BRANCH"
git fetch origin "$BRANCH" || fail "git fetch failed"
git pull --ff-only origin "$BRANCH" || fail "git pull --ff-only failed"

NEW_COMMIT="$(git rev-parse HEAD)"
case "$NEW_COMMIT" in
    "$TARGET_COMMIT"*) ;;
    *) fail "expected commit $TARGET_COMMIT, got $NEW_COMMIT" ;;
esac
log "new commit: $NEW_COMMIT"

service_pid() {
    systemctl show -p MainPID --value "$SERVICE" 2>/dev/null || true
}

restart_service() {
    local old_pid new_pid attempt
    old_pid="$(service_pid)"

    # Prefer a non-interactive sudo. If it is unavailable, SIGTERM the main
    # process: the unit has Restart=always and systemd starts it again.
    if sudo -n systemctl restart "$SERVICE" >/dev/null 2>&1; then
        log "restarted with systemctl"
    else
        if ! [ "$old_pid" -gt 1 ] 2>/dev/null; then
            log "sudo is unavailable and MainPID is empty"
            return 1
        fi
        log "sudo is unavailable, sending SIGTERM to PID $old_pid"
        kill "$old_pid" 2>/dev/null || true
    fi

    for attempt in $(seq 1 30); do
        if systemctl is-active --quiet "$SERVICE"; then
            new_pid="$(service_pid)"
            if [ "$new_pid" -gt 1 ] 2>/dev/null && [ "$new_pid" != "$old_pid" ]; then
                log "service is active, PID $new_pid"
                return 0
            fi
        fi
        sleep 1
    done

    log "service did not become active with a new PID"
    return 1
}

health_check() {
    local pid started

    systemctl is-active --quiet "$SERVICE" || {
        log "service is not active"
        return 1
    }

    pid="$(service_pid)"
    if ! [ "$pid" -gt 1 ] 2>/dev/null; then
        log "service MainPID is invalid: ${pid:-empty}"
        return 1
    fi

    started=0
    if command -v journalctl >/dev/null 2>&1; then
        if journalctl -u "$SERVICE" --since "3 minutes ago" --no-pager 2>/dev/null \
                | grep -q "Бот запущен"; then
            started=1
        fi
    fi
    if [ "$started" -eq 0 ] && [ -f "$APP_DIR/logs/bot.log" ] \
            && [ -n "$(find "$APP_DIR/logs/bot.log" -mmin -5 2>/dev/null)" ]; then
        if tail -n 300 "$APP_DIR/logs/bot.log" | grep -q "Бот запущен"; then
            started=1
        fi
    fi
    if [ "$started" -eq 0 ]; then
        log "startup message not found in journal or recent bot.log"
        return 1
    fi

    if [ -f "$APP_DIR/orders.db" ] && command -v "$PYTHON" >/dev/null 2>&1; then
        if ! "$PYTHON" - "$APP_DIR/orders.db" <<'PY'
import sqlite3
import sys

conn = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
try:
    result = conn.execute("PRAGMA quick_check").fetchone()[0]
finally:
    conn.close()
if result != "ok":
    raise SystemExit("quick_check failed: %s" % result)
PY
        then
            log "SQLite quick_check failed"
            return 1
        fi
    fi

    log "health check passed (PID $pid)"
    return 0
}

rollback() {
    log "rolling back to $PREV_COMMIT"
    git reset --hard "$PREV_COMMIT" || log "rollback reset failed"
    restart_service || log "service restart after rollback failed"
    health_check || log "health check after rollback failed"
}

if ! restart_service; then
    rollback
    fail "restart failed"
fi

if ! health_check; then
    rollback
    fail "health check failed"
fi

TIMER_STATUS="$(systemctl is-active ttn_backup.timer 2>/dev/null || true)"
log "deploy complete"
printf 'commit=%s\n' "$NEW_COMMIT"
printf 'service=%s\n' "$SERVICE"
printf 'pid=%s\n' "$(service_pid)"
printf 'backup=%s\n' "${BACKUP_DIR:-unknown}"
printf 'backup_timer=%s\n' "${TIMER_STATUS:-unknown}"

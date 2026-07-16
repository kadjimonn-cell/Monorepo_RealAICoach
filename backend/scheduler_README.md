# Scheduler Architecture

## Overview

The RealAICoach scheduler system handles background jobs, automated tasks, and system maintenance.

## File Structure

### `scheduler.py` (4,367 lines)
- **Purpose:** Main scheduler engine using APScheduler
- **Responsibilities:**
  - Job registration and configuration
  - Scheduler lifecycle management
  - Error handling and logging
  - Health monitoring

### `scheduler_jobs.py` (6,759 lines)
- **Purpose:** Background job implementations
- **Contains:** 104 scheduled functions
- **Organization:** See inline comments in file for domain grouping

## Job Naming Convention

- `scheduled_*` - Recurring background jobs (daily, hourly, weekly)
- `check_*` - Health check and monitoring jobs
- `_*` - Internal helper functions (not directly scheduled)

## Common Job Patterns

### 1. **Data Cleanup Jobs**
- Remove expired records
- Archive old data
- Purge temporary files

### 2. **Analytics & Reporting**
- Generate daily/weekly reports
- Update dashboards
- Compile metrics

### 3. **User Engagement**
- Send email campaigns
- Push notifications
- In-app announcements

### 4. **Security & Compliance**
- Auto-audits
- Access reviews
- Compliance checks

### 5. **System Maintenance**
- Cache freshness
- Database optimization
- Health monitoring

## Future Refactoring Plan

When breaking down `scheduler_jobs.py` into modules:

```
/app/backend/scheduler_jobs/
├── __init__.py
├── core.py           # Platform core jobs (bills, videos, etc.)
├── security.py       # Auto-audits, lock cycles
├── engagement.py     # Email campaigns, notifications
├── analytics.py      # Reports, dashboards, metrics
├── maintenance.py    # Cleanup, archival, optimization
├── payments.py       # Payment processing, tax audits
└── README.md         # This file
```

## Adding New Jobs

1. Add function to `scheduler_jobs.py` with `scheduled_*` prefix
2. Register in `scheduler.py` with desired schedule
3. Add logging and error handling
4. Document in appropriate section

## Monitoring

- Heartbeat tracking via `_record_scheduler_heartbeat()`
- Admin dashboard at `/admin/scheduler`
- Logs in `/var/log/supervisor/scheduler*.log`

## Notes

- All jobs should be idempotent (safe to run multiple times)
- Use async/await for database operations
- Always include error handling
- Log job start/completion for observability

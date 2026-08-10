# Backup and Recovery Runbook

## Backup cadence
- Daily database backup at 02:00 UTC.
- Keep 7 daily backups and 4 weekly backups.

## Restore procedure
1. Stop the web container and scheduler.
2. Restore the latest database dump into the target database.
3. Restart the web container and verify the health endpoint.
4. Run the regression test suite.

## Verification checklist
- Health endpoint returns 200.
- Login and core approval routes respond normally.
- Scheduler and worker processes are healthy.

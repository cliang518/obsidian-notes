# V2 Dev Runbook

## Local ports

- backend: `127.0.0.1:8011`
- frontend: `127.0.0.1:3011`

## Start commands

### Backend

```powershell
.\platform_v2\start-v2-backend.ps1
```

### Frontend

```powershell
.\platform_v2\start-v2-frontend.ps1
```

- if `frontend/src` is newer than `frontend/dist`, the script now rebuilds the frontend automatically before serving
- this also works when port `3011` is already listening, so repeated startup can refresh the deployed static bundle

### Frontend (dev / hot reload)

```powershell
.\platform_v2\start-v2-frontend-dev.ps1
```

### Both

```powershell
.\platform_v2\start-v2-stack.ps1
```

### Stop

```powershell
.\platform_v2\stop-v2-stack.ps1
```

### Tray

```powershell
.\platform_v2\dist\YongjiaWeakCurrentV2Tray.exe
```

- tray menu now supports `开启开机启动 / 关闭开机启动 / 查看状态`
- startup item is written to the current user's Windows startup folder as `YongjiaWeakCurrentV2Tray.vbs`
- manual install:

```powershell
.\platform_v2\install-v2-tray-startup.ps1
```

- manual remove:

```powershell
.\platform_v2\remove-v2-tray-startup.ps1
```

### License generator

```powershell
.\platform_v2\build-v2-license-generator-exe.ps1
```

### Backup

```powershell
.\platform_v2\backup-v2-state.ps1
```

### Smoke test

```powershell
py -3.14 .\platform_v2\tools\smoke_v2.py
```

## Release bundle

Generate a portable release package with the current backend source, backend venv, built frontend, tray exe, and license generator:

```powershell
powershell -ExecutionPolicy Bypass -File .\platform_v2\publish-v2-release.ps1
```

The bundle is written to `.\platform_v2\release\YongjiaWeakCurrentV2-<timestamp>.zip`.
Inside the extracted folder, use `.\start-v2-stack.ps1` for local launch or `.\dist\YongjiaWeakCurrentV2Tray.exe` for tray startup.

## User documentation

Read the detailed user guide and initialization guide here:

- `.\platform_v2\docs\system-user-guide.md`
- `.\platform_v2\docs\data-initialization-guide.md`
- `.\platform_v2\docs\first-launch-import-checklist.md`
- `.\platform_v2\docs\screenshot-collection-checklist.md`
- `.\platform_v2\docs\engineering-memory.md`

## Engineering rules

- future core workflow changes must evaluate desktop and mobile together
- homepage remains a task-dispatch overview, not a standalone video landing page
- preview / snapshot / diagnostic actions should stay behind concrete devices and channels
- alert center and work-order center must keep one-click jump back to asset/device context
- after each core change, rerun `npm run build` and `py -3.14 .\platform_v2\tools\smoke_v2.py`

## Current sequencing decision

This is the current development order confirmed during live build-out and testing:

- AI module is now in the `usable + keep testing` stage, not the final `deep hardening` stage
- tray / resident-service stack is also in the `usable + keep testing` stage
- deeper AI refinement, richer model-provider hardening, richer action coverage, tray polish, and final operation-grade hardening are intentionally deferred
- those deferred AI / tray items should be resumed only after the main business modules are finished and the whole platform enters the final integration pass

Current mainline priority:

- continue improving existing modules first
- continue end-to-end testing of current features
- continue front-line information collection / attribution /整理 /归纳 workflows
- keep fixing real usage issues discovered during live testing
- do not pause mainline progress to over-invest in AI polishing or tray polishing yet

## Installer build

Build a professional Windows installer with Inno Setup:

```powershell
powershell -ExecutionPolicy Bypass -File .\platform_v2\installer\build-installer.ps1
```

- the script reuses the latest portable release bundle as installer source
- output is written to `.\platform_v2\installer\output\YongjiaWeakCurrentV2-Setup.exe`
- if `ISCC.exe` is missing, install Inno Setup 6 first and run the build again

## Current behavior

- backend initializes a dedicated V2 database
- backend seeds known fact sources discovered during the audit
- frontend is a new information architecture shell
- default frontend script serves the built `dist` directory for better unattended stability
- V2 is isolated from the legacy production line
- V2 can bridge legacy alert data into its own alert center during the transition stage
- runtime center can be used to observe CPU, memory, service ports, and tracked processes
- annual license mode has been scaffolded for formal deployment
- default policy is `365 days + 3 days grace + re-activate on machine change`
- development keeps `V2_LICENSE_ENFORCED=false` unless explicitly enabled

## Source import quick actions

When backend is running, authenticated users can trigger source imports:

- `POST /api/setup/import-source/tg-cos`
  - refresh camera-switch-port relations from TG audit CSV
- `POST /api/setup/import-source/tg-cos-vlan`
  - backfill switch port VLAN from `telnet-show-bundle.txt` L2 MAC table
- `GET /api/topology/vlan-attribution`
  - inspect current attribution result (`attributed / unattributed / recommendations`)
- `GET /api/topology/vlan-attribution/unattributed`
  - list unattributed links for manual verification
- `GET /api/topology/vlan-attribution/unattributed.csv`
  - export unattributed links as CSV
- `POST /api/topology/vlan-attribution/manual-apply`
  - apply manual VLAN corrections in batch

## Alert center quick actions

- `GET /api/alerts`
  - paged list (`page`, `page_size`) with filter params
- `GET /api/alerts/export.csv`
  - export current filtered alert rows
- `POST /api/alerts/bulk-action`
  - batch operation (`acknowledge`, `resolve`, `delete`) with `ids`
- `POST /api/alerts/cleanup`
  - cleanup historical alerts by `status + keep_days` (supports `dry_run`)

## Legacy alert anti-flap behavior

- `POST /api/setup/import-source/legacy-alerts`
  - now uses dedupe-key coalescing for same-device same-kind legacy events
  - short recovery events (<= 180s) are classified as `network_flap_watch`
  - stale replay rows are ignored by timestamp guard to prevent duplicate growth
- `GET /api/alerts/summary`
  - includes `flap_watch_count` and `strict_unresolved_count` for noisy-link diagnosis
  - now includes `storm_guard` for large-scale outage / host-disconnect diagnosis
- `GET /api/alerts/guard-settings`
  - inspect current alert-storm guard thresholds
- `PUT /api/alerts/guard-settings`
  - persist tuned thresholds to `runtime/alert_guard_settings.json`
- `POST /api/notifications/dispatch-alerts`
  - now consults `storm_guard` before fan-out
  - when large-scale outage protection is active, non-`full_ops` channels suppress per-alert pushes by default
  - use `force_dispatch=true` only when you intentionally want to bypass this protection

## Runtime backup quick actions

- `GET /api/system/backups`
  - list recent V2 backup archives
- `POST /api/system/backup`
  - create a new backup archive immediately
- `POST /api/system/backups/prune`
  - prune backups by keep count (`keep_latest`) with `dry_run` support
- `GET /api/system/backups/{filename}`
  - download a specific backup zip
- `DELETE /api/system/backups/{filename}`
  - delete a specific backup zip

## Control platform maintenance quick actions

- `GET /api/control-platform/registrations/{registration_id}/export`
  - export the selected control-platform registration, activity snapshot, and current audit object counts as JSON
- `DELETE /api/control-platform/registrations/{registration_id}/audit-data`
  - clear imported audit data for the selected track while preserving the registration itself
  - removes control devices / points / scenarios / events / menus plus related sync jobs, snapshots, and source-object mappings

## Notification anti-spam quick actions

- `POST /api/notifications/dispatch-alerts`
  - dispatch recent alert notifications with throttling and optional `dry_run`
  - key params: `lookback_minutes`, `max_alerts`, `dry_run`
- channel-level controls:
  - `alert_cooldown_seconds`: cooldown window for same alert event re-send
  - `suppress_flap_watch`: suppress `network_flap_watch` noise by default

## Temporary dev note

During this stage, `platform_v2/frontend/node_modules` may be linked to the legacy frontend dependency tree to avoid unnecessary network churn while the V2 shell is still being stabilized.

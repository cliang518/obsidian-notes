# V2 Phase 1 Execution Plan

## Goal

Phase 1 establishes a clean operational core for the new platform without trying to replace every old function at once.

## Deliverables

### 1. Unified asset backbone

- platform sources
- asset devices
- asset areas
- network ports
- topology links
- video channels
- credential references

### 2. Read-only ingestion backbone

- TG/COS source adapter
- JVSS source adapter
- Hikvision NVR source adapter
- Hikvision decoder source adapter
- switch/gateway source placeholders

### 3. First operational views

- overview dashboard
- asset center
- topology center
- integration center
- video center shell

## Build order

### Step 1

Stabilize data model and repository layout.

### Step 2

Add source ingestion record tables:

- sync job
- sync snapshot
- source object mapping

### Step 3

Implement first adapters:

- JVSS channels import
- TG/COS terminal import
- Hikvision NVR import

### Step 4

Normalize relations:

- source object -> asset device
- NVR -> channel
- switch -> port
- device -> area

### Step 5

Expose stable V2 APIs:

- `/api/system/health`
- `/api/assets/runtime-counts`
- `/api/assets/platform-sources`
- `/api/assets/devices`
- `/api/assets/channels`
- `/api/assets/links`
- `/api/integrations/sources`

## Non-goals for phase 1

- no final playback center yet
- no full alarm migration yet
- no write-back into third-party platforms
- no full map system yet

## Quality bar

- clean module boundaries
- no legacy table coupling
- no hidden dependency on old runtime paths
- source facts must preserve origin and timestamp


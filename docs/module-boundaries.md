# V2 Module Boundaries

## Core modules

- `asset-center`
  - unified asset registry
  - areas, devices, ports, channels, links
- `integration-center`
  - syncs from TG/COS, JVSS, Hikvision, gateway, switch
- `topology-center`
  - topology graph, relation confidence, fault blast radius
- `video-center`
  - streams, snapshots, playback entry points, decoder outputs
- `alarm-center`
  - layered alarms with dependency suppression
- `work-order-center`
  - tickets, maintenance flow, evidence uploads
- `resource-center`
  - notes, manuals, reports, contracts, attachments

## Design constraints

- no direct write-back into third-party platforms
- no mixing legacy tables with V2 tables
- media routing stays separate from business APIs
- source facts must preserve origin and sync time


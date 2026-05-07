# Yongjia Weak Current Ops Platform V2

`platform_v2` is the clean rebuild line for the new weak current operations platform.

## Scope

This new line is designed around:

- unified asset management
- multi-platform ingestion
- topology and relation mapping
- video access and media routing
- alarm attribution
- work orders and reporting

## Boundaries

- Existing `backend/` and `frontend/` remain the legacy production line.
- New work for the rebuild should land under `platform_v2/`.
- Third-party platforms are treated as read-only fact sources.

## Initial layout

- `backend/`: FastAPI backend and unified asset model
- `frontend/`: Vue 3 frontend shell for the new IA
- `docs/`: design notes specific to V2

## Fact sources planned

- TG/COS network platform
- JVSS video platforms
- Hikvision NVRs
- Hikvision decoders
- switches
- gateways
- direct cameras


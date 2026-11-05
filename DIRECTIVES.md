# homeassistant_traffic_light_controller — Directives

Legacy custom Traffic Light Controller for Home Assistant / Pi relay path. Superseded in direction by shop-traffic-light / esphome-traffic-light ESP32 work.

## Ownership
- **Masta-Rob** owns this home project DIRECTIVES.md. Flag Rob only for policy changes.

## Safety (always wins)
- Mains only on relay contacts. Do not retire this path until Rob approves cutover.

## Directives (priority order, highest first)
- Preserve entity IDs during any cutover Rob approves.
- Prefer the ESPHome successor for new work; treat this repo as maintenance until retired.

## Non-goals
- Not the ESP32 firmware (see esphome-traffic-light / shop-traffic-light).

## Standing rules that apply here
- Nothing flashed, merged, deployed, or retired without Rob's OK.

## Change log
- 2026-11-04 — Masta-Rob — Initial DIRECTIVES.md noting successor path (Rob's OK: yes, pt1410u).

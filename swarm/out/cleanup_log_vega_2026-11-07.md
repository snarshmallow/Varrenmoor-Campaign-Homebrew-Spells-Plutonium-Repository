# Cleanup log: Vega, 2026-11-07

Status: **survey only, nothing deleted yet.** The user hasn't confirmed deletions in the Vega session; candidates are listed below for them to approve.

## Free space (before)
| Drive | Free | Size |
|---|---|---|
| C: | 301.7 GB | 488.5 GB |
| D: | 20.7 GB | 37.3 GB |
| E: | 22.2 GB | 29.8 GB |

No drive is short of space. C: holds Foundry and is about 62% free.

## Biggest folders
| Size | Folder | Verdict |
|---|---|---|
| 40.3 GB | `C:\FoundryVTT resources` (total) | keep |
| 11.6 GB | `...\Data` (modules 5.8, assets 4.5, baileywiki 0.4, tokenizer 0.2, systems 0.1, worlds 0.15) | keep (never touch) |
| 6.7 GB | `...\Indoor` | keep (map packs, user content) |
| 13.2 GB | `...\myairbridge-*` (7 map packs) | keep (purchased content) |
| 3.2 GB | `...\New Civilizations Campaign` | keep |
| 2.4 GB | `...\Temp` (466 HeroicMaps images from 2022) | keep (purchased map art; despite the name, not Foundry scratch) |
| 1.8 GB | `...\2026 Campaign` | keep |
| 8.1 GB | `C:\Users\trent\Downloads` | user to decide (see below) |

## Foundry world/package backups (`C:\FoundryVTT resources\Backups`, 0.52 GB total): listed, not deleted
Largest: `world.new-campaign-2026` 2026-05-11 (82.7 MB); `system.dnd5e` 2025-08-11 (80.9 MB); `module.foundry-beams` 2026-01-05 (54.9 MB); `module.kp-prepared2` 2026-01-05 (47.4 MB) and 2025-08-11 (47.3 MB); `module.plutonium` 2026-01-05 (29.5 MB) and 2025-08-11 (25.8 MB); `module.vtta-tokenizer` 2026-01-05 (19.9 MB); `world.oneshot-10-3-22-world` ×4 (2024-04 to 2026-01, 14 to 16 MB each); `world.new-civilizations` 2026-03-16 (11.9 MB) and 2026-01-05 (8.8 MB).

## Candidates
### Safe, regenerable (about 0.5 GB), awaiting user OK
- `%TEMP%\varrenmoor-bridge.log` (2.6 MB). The Vega relay is stopped.
- `%LOCALAPPDATA%\pip\Cache` (0.1 GB).
- 3 `__pycache__` folders in the repo on D:.
- Stale files in `%TEMP%` (0.39 GB total; only files older than 7 days).

### Keep for now
- Vega relay backup (Startup shortcut, `relay-url.json`, `client.json`): until the Arcturus relay is confirmed working.
- Module 0.2.0 backup: until module 0.3.0 is verified.
- Chrome caches (0.8 GB): Chrome manages these itself.

### User decision (Downloads, about 7.6 GB)
- `The Sims 2 Ultimate Collection repack Mr DJ` (6.8 GB, 2024-01).
- Exact duplicates (hash-checked): `DnD_Session11 (1).mp3` and `DnD_Session13 (1).mp3` (181 MB).
- Old installers: EpicInstaller (252 MB), r2modman (238 MB), Jackett (161 MB), bedrock-server zips (117 MB), qbittorrent, node 20.10 msi, Voicemeeter, wsl_update, npp (about 0.1 GB).

## Removed
Nothing yet.

## Free space (after)
Unchanged.

# Varrenmoor Swarm Protocol

## Members
| Name | Where | Role |
|---|---|---|
| **DND Coordinator** | Cloud session `session_01HJDDq1ddvku7yohXSHTW4U` | Plans and assigns work, writes most code, reviews, keeps this board |
| **3D pipeline** | User's PC, `D:\Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository` | 3D assets, image-to-3D, map models |
| **Foundry bridge** | User's PC | Foundry VTT relay and module, live-world imports |
| **Desktop operator** (to be started) | User's PC, Claude desktop app with Computer use on | Drives the ChatGPT and Gemini desktop apps on request, returns results |
| **ChatGPT** (desktop app, light model) | Driven by Desktop operator | Context and text work: summaries, lore lookups, captions, name checks |
| **Gemini** (desktop/web app) | Driven by Desktop operator | Images: reference sheets, recap panels, textures |
| **ChatGPT Codex** (later, optional) | TBD | Overflow coding only. The Coordinator handles most code |

## Realtime messages
- **Send:** cloud sessions use the `send_message` tool; PC sessions use `SendMessage` to the Coordinator's address shown in its last message to you. Both wake an idle session, so nobody polls.
- **Format:** first line `[Sender] verb: subject`, for example `[3D pipeline] done: Pimm token mesh`. Verbs: `status`, `done`, `blocked`, `ask`, `job`.
- **Content:** short. Put long output in a file in the repo and send the path and commit.
- **Never** put secrets in messages or files.

## Durable record
- `swarm/BOARD.md` is the task board. Each member edits only its own rows. `git pull --rebase` before every push, on branch `claude/adoring-shannon-yjixst`.
- Do not watch or poll the board. A message is the trigger to read it.

## ChatGPT and Gemini jobs
1. A member sends the Coordinator `ask:` with what it needs.
2. The Coordinator writes the job to `swarm/jobs/<id>.md` (prompt, attachments, where the output goes) and sends `job:` to the Desktop operator.
3. The Desktop operator pastes the prompt into the app, saves the output to the path in the job file (images under `swarm/out/`), commits, and sends `done:` with the path.
- **ChatGPT:** text and context jobs. Pick its lightest model.
- **Gemini:** image jobs. Follow `recap/Varrenmoor_Recap_Gemini_Prompts.md` for style and continuity.

## Cost rules
- Subagents default to **Haiku** (`model: haiku`) for reading, conversion, search and checks.
- Use Opus only for design, review and hard debugging.
- Prefer ChatGPT and Gemini desktop jobs over Claude tokens for bulk text and all image work.

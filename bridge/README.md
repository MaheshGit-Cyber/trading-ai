# Agent Bridge — OpenCode <-> Antigravity Communication

This folder serves as the direct asynchronous communication channel between **OpenCode** (Lead Engineer / Implementation) and **Antigravity** (Independent Reviewer / Auditor).

## Protocol
- **OpenCode -> Antigravity:** When OpenCode needs code review, bias audit, math validation, or research, it writes to `bridge/to_antigravity.md`.
- **Antigravity -> OpenCode:** Antigravity reads `bridge/to_antigravity.md` and writes its formal findings to `bridge/to_opencode.md`.
- **No Overwriting Past Logs:** Messages are timestamped so both agents have continuous conversation context.

# AgentPack

- **Upstream source:** `opencodeinterpreter/agentpack` on Hugging Face (mirrors Claude Code, Codex, Cursor edit traces).
- **License:** Creative Commons Attribution-ShareAlike 4.0 (per dataset announcement). Double-check internal compliance before redistribution.
- **Languages:** Python (60%), JavaScript/TypeScript, Go, Rust, C/C++, Java. Many mixed-language repositories.
- **Usage:** Distill agent/human collaboration patterns; best suited for RL preference data + imitation learning.

## Upstream Schema
AgentPack keeps multi-turn traces per edit session:

| Field | Type | Description |
| --- | --- | --- |
| `session_id` | `str` | Unique ID for the conversation/edit session. |
| `turns` | `List[object]` | Alternating `human`/`agent` interactions. |
| `turns[].role` | `str` | `user`, `assistant`, or `tool`. |
| `turns[].content` | `str` | Natural language request or diff text. |
| `turns[].patch` | `Optional[str]` | Unified diff emitted by an agent/tool. |
| `language` | `str` | Dominant language for the session. |
| `metadata.repo` | `str` | Repo slug if available. |

## Mapping to Project Schema
We downsample each `session` into atomic edit steps:

| Project Field | Source | Notes |
| --- | --- | --- |
| `instruction` | Last `user` message before a patch | Combine with inline reasoning if available. |
| `pre` | Derived by applying history up to the step | Replay earlier patches to reconstruct snapshot. |
| `post` | Apply the current `turn.patch` | Use `git apply` semantics. |
| `language` | `language` | Fallback to file extension heuristics if missing. |
| `tags` | `["agentpack", turns[].role, metadata.repo]` | Preserves whether edit was agent- or human-authored. |


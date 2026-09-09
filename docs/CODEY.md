# Codey desktop integration

Codey mode connects the Wi-Fi display to a local macOS Codex installation. It uses a read-only query against the local task index and optional lifecycle hooks. It does not run ChatGPT on the ESP32.

## Setup

Follow the Codey commands in the root README. A compatible installed app is needed to export artwork, or provide your own compatible sprite sheet with `assets --profile codey-tft --sheet PATH`. The current grid is 1536 pixels wide, 192×208 cells, with the rows used by the converter available. Asset format changes fail with an error rather than silently selecting a different asset.

The generated header, sheet, palette, device captures and runtime event files are excluded from Git and source releases. The MIT license applies to this project's original code, not the OpenAI character or branding.

## Useful information

- Task name and project/model, alternating with cumulative token total.
- Count of tasks updated within the last two minutes, labelled recently active.
- Optional hook-observed lifecycle state: working, needs input, finished, failed or idle.
- BOOT tap: next recently active task, with a request to open it in the desktop app.
- BOOT hold for at least 800 ms, then release: restore automatic display rotation.

The recent-task cycle has stable ordering despite token updates. Navigation events carry per-boot IDs, expire after ten seconds, and are deduplicated by the companion. A stale/offline feed does not open a task. Browser selection changes what the pet shows; automatic rotation never opens app tasks.

## Hooks

`./install.sh hooks` adds ten observer definitions for this installation's absolute path to `~/.codex/hooks.json`, preserving unrelated entries. It does not alter hook trust. Review/enable the definitions through the app's Hooks settings. Existing running tasks may retain their previous configuration until the app restarts. If you move this project, remove its previous entries and reinstall at the new path.

Hook input is bounded, and the script stores only a hashed session identifier, event name, status and timestamp. Prompts and tool arguments are discarded. Files are local with restrictive permissions. The observer fails open and returns `{}` so a display failure does not block app work.

Hook statuses are aggregated across observed sessions; they are not guaranteed to describe the selected task. In the absence of fresh hooks, task-index recency is an inference, labelled accordingly. Finished highlights expire, and stale feeds show unavailable.

## Compatibility and privacy

The metadata reader currently expects `~/.codex/state_5.sqlite` and an allowlisted set of columns. It reads task names, project paths (reduced to a basename), model, cumulative tokens and update times. It does not query messages, previews, transcript content, credentials or trust settings. Schema changes fail closed. Cumulative tokens are not remaining quota or cost.

The installed macOS protocol handler is invoked with `codex://threads/<validated UUID>`. This integration is version-sensitive and has no Windows/Linux app-navigation implementation. A successful open command confirms dispatch, not that the app visually switched tasks.

The full metadata feed is available to a loopback browser or a paired client. Device heartbeats receive only compact display text and lifecycle data, not the full task list or raw IDs. Wi-Fi uses token-authenticated HTTP on a trusted LAN. Keep the companion port off the public Internet.

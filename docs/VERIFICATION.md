# Verification

## Software checks

The release workflow runs Node integration tests, Python installer tests, C++ lifecycle/button tests, and builds all three PlatformIO environments from clean source. Tests cover bounded commands, acknowledgements, stale data, authentication/origin restrictions, navigation retry deduplication, profile selection, credential preservation, configuration rollback, ambiguous serial ports and build-only behavior.

Codey's CI build uses generated geometric fixture pixels. Local Codey compilation also uses a locally exported compatible sprite sheet. Neither is a claim that every desktop app version is compatible.

## Physical hardware exercised during development

An ideaspark ESP32-D0WD-V3 revision 3.1 with an integrated 170×320 ST7789 and CH340 USB adapter was identified, backed up, flashed and tested. Development checks included:

- Flash verification and device-rendered framebuffer capture for Pip and Codey.
- Care controls, Wi-Fi heartbeat, network outage recovery, continuing uptime and heap headroom.
- Synthetic lifecycle events through the observer, companion and Wi-Fi to the physical display.
- Live task metadata and selected-task display on the physical device.
- Serial invocation of the same firmware navigation handler used by BOOT, with Wi-Fi acknowledgements and successful macOS open-command dispatch.

The final navigation exercise did not physically press BOOT or visually verify the app's destination page. Native tests cover debounce, short press, hold, one-shot events and timer rollover. Hook installation/trust and actual app emission are separate checks; synthetic event tests do not prove app-emitted hooks.

## Limits

- OLED is compile-tested; no physical SSD1306 was verified in this project.
- macOS installer/builds are exercised locally; Linux is checked by CI. Windows wrapper and tooling are supplied but untested.
- No new flash is performed simply to test installer profile switching. The currently installed device configuration is preserved.
- The companion must run on the computer, and both devices need LAN reachability. Display wiring is specific to each profile.
- API replies use mocked upstream responses in automated tests. A configured key and available API access are required for real AI replies.
- Private raw hardware logs, backups, captured metadata and configured binaries are deliberately absent from releases.

Hardware diagnostics are opt-in, require `--port`, and may reset the board when opening serial. `tools/button_test.py` also opens recently active tasks. Run these only against your own connected setup with the matching companion already running.

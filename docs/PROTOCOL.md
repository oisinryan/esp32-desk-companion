# Companion protocol v1

One companion process serves one pet. Device, care, chat and state routes require `Authorization: Bearer <PET_TOKEN>` in real mode. `GET /api/info` is public; desktop metadata and selection also allow a loopback browser with checked Host (and matching Origin for selection). Body requests require `Content-Type: application/json` and are capped at 4096 bytes. Static files are served from an explicit allowlist; configuration files are never served.

## Device heartbeat

`POST /api/device`, about once per second:

```json
{"energy":80,"fullness":75,"joy":75,"sleeping":false,"mood":"curious","ack":""}
```

Needs are integers 0–100. `sleeping` must be a JSON boolean. Mood must be one of `happy`, `curious`, `love`, `excited`, `sleepy`, `sad`, `thinking`. `ack` is the last applied command's UUID or an empty string at boot.

Response is either `{"command":null}` or:

```json
{"command":{"id":"a-command-uuid","action":"feed","mood":"","text":""}}
```

A chat reply has an empty action plus mood and printable ASCII text (maximum 160 characters). The oldest queued command is returned until acknowledged. Firmware applies each ID once during its current boot and echoes that ID on the next poll. A response must never acknowledge a command before applying it. Queue depth is eight. Commands expire after 30 seconds. The UI considers hardware disconnected after six seconds without a heartbeat.

The network task passes fixed-size command records through a FreeRTOS queue; only the animation loop mutates the pet. The animation loop shares a fixed-size snapshot through a single-item queue. Network status uses an atomic flag. Network calls have timeouts, and both tasks join the task watchdog. The OLED framebuffer is 1024 bytes; the ideaspark TFT target uses a 54,400-byte palette framebuffer.

The hardware is authoritative: the companion does not optimistically update needs after sending a command. It waits for the next reported device state. The browser's decorative case is a visual preview, not a supplied physical enclosure design.

## Browser routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/info` | Demo/API configured flags, no secrets |
| GET | `/api/state` | Device state, connection freshness, bounded chat history, pending count |
| POST | `/api/action` | `{"action":"pet"}`; also feed, play, sleep, wake |
| POST | `/api/chat` | `{"message":"Hello Pip"}`; AI response queues an expression and caption |

In demo mode, care updates a simulated pet and chat produces scripted messages. `/api/device` is rejected to prevent hardware and demo state mixing. Demo always binds to loopback. Authenticated real mode is required for LAN operation.

## Extending display support

`firmware/include/pet.h` holds the hardware-independent lifecycle. `render()` in `firmware/src/main.cpp` is the OLED renderer. Replace the display adapter and board pin map for TFT/e-paper hardware; preserve the lifecycle, fixed-size queues, protocol, and HTTP task. Pin maps must be checked for the actual ESP32 variant. The ideaspark adapter is defined in `firmware/include/ideaspark_display.h`; its fixed PCB wiring was matched to the running radar installation before flashing.


## Desktop metadata and navigation

`GET /api/desktop` returns bounded task metadata, freshness, the selected task, and display text. `POST /api/desktop/select` accepts `{"key":"task-key"}` or `{"key":null}` for automatic selection. A browser-selected key must belong to the current feed.

Codey heartbeats may include `"navigation":{"id":"01234567-00000001","action":"next"}` (or `"auto"`). The ID is a per-boot nonce plus sequence. The device retries until acknowledged or ten seconds elapse; the service retains 64 deduplication results and serializes concurrent events. Navigation is token-authenticated. The response includes compact `desktop` data and a navigation result with the original ID and `ok` boolean. The full task list and raw task IDs are omitted from the device response.

The configured Codey app opener is macOS-specific. Acknowledgement reports whether the open command succeeded, not visual confirmation of task focus.

# desktop-pet-ai · AI Desktop Pet

> **Language:** English | [中文](README.md)

A PyQt5-based AI-driven desktop pet: transparent, always-on-top, draggable and
scalable. All text (self-talk / head-pat reactions / chat replies) is generated
in real time by an OpenAI-compatible API — no quote libraries at all.

## Features

1. **Real-time AI generation**: self-talk, head-pat reactions and chat replies
   all call an OpenAI-compatible `/v1/chat/completions` endpoint; the system
   prompt combines persona + context (time of day, affection tier, weather,
   trigger tag) + recent conversation history.
2. **Built-in free AI (DeepSeekWeb2API)**: the project embeds
   `vendor/DeepSeekWeb2API` (portable Node build, prepared locally, not in
   Git). On first launch a DeepSeek login browser pops up; after you log in
   and close the console window the service starts on `127.0.0.1:3000` and
   later launches stay silent. If the login expires, click "Rebind" in
   settings. If a web2api service is already listening on port 3000, it is
   reused as-is.
3. **Provider presets**: the settings page offers a preset dropdown —
   DeepSeekWeb2API (built-in free) / SiliconFlow / Kimi / Custom. Picking a
   preset fills in base_url and auto-fetches candidate models from the
   platform's `/v1/models` into a model dropdown (still manually editable);
   cloud services only need an API key.
4. **Chat input**: an always-visible input box below the pet (draggable,
   wheel-adjustable font size, remembered position); press Enter to chat.
5. **Head-pat reaction**: a single click plays the head-pat animation once and
   triggers an AI reaction; press-and-hold = drag, which does not trigger.
6. **Contextual self-talk**: same trigger logic as the original — time-of-day
   windows (morning/noon/afternoon/evening/midnight, once per day each),
   weekends, a 45-minute sedentary reminder, a 90-minute no-interaction
   attention seeker, affection-tier changes, weather changes (auto IP
   location + Open-Meteo) and random chatter at a configurable interval.
6. **Chat history**: all messages (including self-talk) are persisted to JSON
   with a configurable cap, surviving restarts; view them via the tray menu's
   "Chat history…". Context length is configurable and only user/assistant
   messages are sent.
7. **Failure fallback**: when a request fails, a fallback text
   ("Hmm… I'm short-circuiting a bit") is shown; it can be turned off.
8. **Thought-cloud notifications**: actions pop a cloud bubble with
   customizable fill/outline colors, text and font size.
9. **Appearance**: import PNG/GIF skins; the head-pat animation (GIF, plays
   once, transparent background) and window always-on-top are switchable
   (default skin `assets/ds拟人.png`, default head-pat animation
   `assets/ds拟人_q.gif`).
10. **Affection system**: petting/interaction raises affection, idleness
    decays it over time; high/mid/low tiers shape the AI's tone and triggers;
    an "affection" badge can be shown, and every parameter (initial, cap,
    gain, decay, thresholds) is configurable.
11. **Period status label**: peak/idle status label stays visible
    (customizable text), confirmed via bubble.
12. **Position/size memory & one-click recall**: position and size are saved on
    exit and restored on the next launch; the tray menu's "Recall to center"
    moves the pet to the center of the current screen without resizing it, so
    it can always be brought back even if it was dragged off-screen.

AI messages never use force notifications: they appear as bubbles/labels, and
chat content is persisted for later reading.

## Requirements

- Windows 10/11
- Python 3.9+
- Dependencies: PyQt5, requests, Pillow (see `requirements.txt`)
- For the built-in free AI, place a DeepSeekWeb2API portable bundle under
  `vendor/DeepSeekWeb2API` (node/, node_modules/, src/, config.json; not
  included in the repo), or use any cloud OpenAI-compatible key

## Install & run

```bash
pip install -r requirements.txt
python main.py
```

First use: right-click the tray icon (or the pet) → Notification settings →
AI tab → pick a preset and enter your API key (model is editable).

> The local DeepSeekWeb2API endpoint defaults to `http://127.0.0.1:8000/v1`;
> use the port from that project's `config.json`.

## Usage

- **Left-drag**: move the pet (auto-saved); **wheel**: zoom.
- **Left-click**: play head-pat animation + AI reaction; rapid clicks restart
  it; dragging does not trigger.
- **Chat input**: press Enter to send; draggable, wheel adjusts font size.
- **Tray**: left-click shows/hides the pet; right-click menu: chat history,
  autostart, notification settings, appearance, test notification, quit.

## Configuration

`config.json` sits in the project root (auto-generated, atomic writes with a
`.bak` backup). Common keys:

- Notification/appearance: `balloon_fill`, `balloon_outline`, `balloon_text`,
  `balance_font_size` (global font size), `pet_image`, `pet_interact_image`,
  `pet_scale`, `pet_pos`, `always_on_top`;
- Affection: `affection_*` (enabled/initial/cap/gain/decay/thresholds/badge);
- Self-talk: `self_talk_enabled`, `self_talk_interval` (random chatter, seconds);
- AI: `ai_preset`, `ai_base_url`, `ai_api_key`, `ai_model`, `ai_persona`,
  `ai_context_n` (context messages), `ai_fallback_enabled`, `ai_fallback_text`;
- History: `chat_history_max` (persistence cap), `chat_input_offset` (input
  box position);
- `auto_start`: launch at login (synced with the registry Run key).

## Development & testing

Offscreen self-check (no GUI needed; covers GIF playback, click/drag split,
affection, triggers, history, input box, weather):

```bash
python tests/offscreen_smoke.py
```

Smoke run: `PET_SMOKE=1 python main.py` (auto-exits, exit 0 = pass).

## Related projects

* [png-q-bounce](https://github.com/toki-2004/png-q-bounce): turn one PNG into
  a bouncy GIF (plays once, transparent background) — usable as the head-pat
  animation skin.

## Security note

`ai_api_key` in `config.json` is stored in plain text — never commit or share it.

# desktop-pet-ai · Free AI Desktop Pet

> **Language:** English | [简体中文](README.md)

A desktop pet that lives on your screen: it talks to itself, reacts to head pats,
and chats with you — every word generated live by AI. **Built-in free AI
(DeepSeekWeb2API)** means one first-time login with a web DeepSeek account, then
zero-cost chatting with no API key at all.

## Highlights

- **Completely free**: a bundled local DeepSeekWeb2API service. Log in to the
  web DeepSeek account once; no paid API key ever needed.
- **AI generates everything in real time**: self-talk, head-pat reactions and
  chat replies come straight from the model — no repetitive quote banks.
  Customize the persona; behavior adapts to time of day, weather, affection
  tier, work status and more.
- **Switch AI providers anytime**: besides the built-in free service, switch to
  the DeepSeek Open Platform / SiliconFlow / Kimi / any OpenAI-compatible
  endpoint; presets auto-fetch the platform's model list.
- **It remembers**: an affection system plus chat-history context means the AI
  knows what you've talked about.

## Features

1. **Free AI chat**: an always-visible input box below the pet; press Enter to chat.
2. **AI self-talk**: triggered by time, weather, idle reminders, attention
   seeking, affection tiers, work status, etc.
3. **Head-pat interaction**: click the pet to play a bouncy animation and get an
   AI reaction.
4. **Affection system**: petting raises affection, idleness decays it; tiers
   shape the AI's tone, with an always-visible badge.
5. **Work-status awareness**: after binding a balance account, work state
   (working / idle / topped up) is derived from balance changes and injected
   into the AI prompt; the AI speaks on state changes.
6. **Balance query**: multi-platform accounts (DeepSeek / Kimi / SiliconFlow),
   with the balance label always visible at the pet's top-left.
7. **Context label group**: affection / period / work-status labels sit side by
   side below the pet.
8. **Weather awareness**: auto geo-location + Open-Meteo weather; it will chat
   about rain.
9. **Chat history**: persisted to JSON; the history dialog opens scrolled to the
   latest message.
10. **Look & layout**: PNG/GIF skins, wheel zoom, position/size memory,
    one-click recall (never get stuck off-screen).
11. **The usual desktop-pet stuff**: auto-start, tray control, always-on-top.

## Screenshots

(To be added: pet appearance / chat example / settings page)

## Getting started

### Option 1: download the release (recommended)

1. Grab the latest `DesktopPet-vX.Y.Z.zip` from
   [Releases](https://github.com/toki-2004/desktop-pet-ai/releases), unzip and
   double-click `DesktopPet.exe`.
2. **On first launch a DeepSeek login browser pops up**: log in with your
   DeepSeek account, then close the console window — the built-in free AI is
   ready (no popup on later launches).
3. Just talk to the pet: type in the input box and press Enter; click it to pat
   its head; right-click the tray icon for more.

### Option 2: run from source

```bash
pip install -r requirements.txt
python main.py
```

(From source you also need the local vendor bundle for the built-in AI, or use a
cloud preset — see "AI settings".)

### Common actions

- **Chat**: press Enter in the input box below the pet.
- **Head pat**: left-click the pet (animation + AI reaction); press-and-drag to
  move (position remembered automatically).
- **Zoom**: hover over the pet and scroll the wheel.
- **Tray**: left-click toggles show/hide; right-click menu: recall to center,
  chat history, auto-start, settings, change skin, quit.
- **AI settings**: right-click → Settings → AI tab: provider presets (built-in
  free / DeepSeek Open Platform / SiliconFlow / Kimi / Custom); picking a preset
  auto-lists its models; base URL / key / model can also be edited manually.
- **Balance**: Settings → Balance tab to add accounts (DeepSeek / Kimi /
  SiliconFlow).

### Login expired?

Click "Rebind" on the settings AI tab — the DeepSeek login browser pops up again.

## Requirements

- Windows 10/11 (the packaged version needs no Python)
- From source: Python 3.9+, dependencies in `requirements.txt`

## Configuration

`config.json` is auto-generated next to the program (atomic writes + `.bak`
backup). Common keys:

- Look/layout: `pet_image`, `pet_interact_image`, `pet_scale`, `pet_pos`,
  `balance_font_size` (global font), `always_on_top`;
- Affection: `affection_*` (enabled/initial/cap/gain/decay/thresholds/badge);
- AI: `ai_preset`, `ai_base_url`, `ai_api_key`, `ai_model`, `ai_persona`,
  `ai_context_n`, `ai_fallback_enabled`, `ai_web2api_max_messages`;
- Balance/work status: `accounts`, `poll_interval_sec`, `show_balance`,
  `work_label_enabled`, `work_state_hold_sec`;
- Others: `self_talk_enabled`, `self_talk_interval`, `chat_history_max`,
  `auto_start`.

## Development & testing

```bash
python tests/offscreen_smoke.py   # offscreen self-check (90 checks)
PET_SMOKE=1 python main.py        # smoke run, exit 0 = pass
```

## Related projects

* [desktop-pet](https://github.com/toki-2004/desktop-pet) (archived): the
  original project this one evolved from.
* [png-q-bounce](https://github.com/toki-2004/png-q-bounce): turn one PNG into a
  bouncy GIF (plays once, transparent background) — usable as a head-pat skin.

## Security note

`ai_api_key` and balance account keys in `config.json` are stored in plain text —
never commit or share them.

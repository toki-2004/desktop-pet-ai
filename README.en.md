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
- **It can see**: drop an image onto the pet, paste a screenshot with Ctrl+V
  (Win+Shift+S works straight away), or use right-click → "Send image…" and it
  looks at the picture and says something. The built-in free AI uses DeepSeek
  web image recognition, so it stays free.
- **It knows what you're doing**: current open apps plus apps currently playing
  audio (background music counts) are injected into the AI context, so it can
  tell coding, gaming or video-watching apart and keep the chat on topic.

## Features

1. **Free AI chat**: an always-visible input box below the pet; press Enter to chat.
2. **AI self-talk**: triggered by time, weather, idle reminders, attention
   seeking, affection tiers, work status, etc.
3. **Head-pat interaction**: click the pet to play a bouncy animation and get an
   AI reaction.
4. **Affection system**: petting raises affection, idleness decays it; tiers
   shape the AI's tone, with an always-visible badge.
5. **Image chat**: drop an image / paste a screenshot / right-click "Send image…";
   the AI looks at it and answers, and the exchange is saved to history.
6. **Chat-history web page (LAN)**: open one URL from your phone or tablet on the
   same WiFi to read the history and talk to the pet — exactly like typing in the
   pet's input box. The header shows the current affection and has a **head-pat
   button** (same path as clicking the pet: animation + AI reaction + affection);
   the log refreshes every 2 seconds, so replies show up without reloading. The
   **图片** button sends a photo/gallery image to the pet (same as dragging an
   image onto the desktop pet; big photos are downscaled on the phone first), and
   sent images are rendered inline in the log (tap for the full picture).
   The URL carries an access token; right-click the pet to copy it.
7. **Work-status awareness**: after binding a balance account, work state
   (working / idle / topped up) is derived from balance changes and injected
   into the AI prompt; the AI speaks on state changes.
8. **Balance query**: multi-platform accounts (DeepSeek / Kimi / SiliconFlow),
   with the balance label always visible at the pet's top-left.
9. **Context label group**: affection / period / work-status labels sit side by
   side below the pet.
10. **Weather awareness**: auto geo-location + Open-Meteo weather; it will chat
   about rain.
11. **Chat history**: persisted to JSON; the history dialog opens scrolled to the
   latest message.
12. **Look & layout**: PNG/GIF skins, wheel zoom, position/size memory,
    one-click recall (never get stuck off-screen).
13. **The usual desktop-pet stuff**: auto-start, tray control, always-on-top.
14. **App awareness**: each conversation includes the currently open app
    windows (foreground first) plus apps producing audio (background
    music/video counts), so the AI can tell what you're doing.
15. **Sleep**: say "午安" (nap) or "晚安" (good night) and the pet answers, then
    goes to sleep — 2 hours for a nap, 8 hours for the night; it wakes when that
    timer ends or when the clock hits 14:30 / 08:30 (whichever comes first).
    While asleep, talking to it / patting it / sending a photo only gets
    "呼……呼……（桌宠似乎睡得正香）" (not saved to history), self-talk stops, and
    affection neither rises nor decays; its first line after waking sounds like
    someone who just got up.

## Screenshots

<p align="center">
  <img src="assets/screenshots/appearance.png" alt="Pet appearance with side-by-side labels" width="320"/>
  <img src="assets/screenshots/chat.png" alt="AI chat with the pet" width="320"/>
  <br/>
  <img src="assets/screenshots/ai_settings.png" alt="AI settings page" width="520"/>
</p>

Left to right: the pet with its affection / period / work-status labels side by
side, an AI chat with the pet, and the AI settings page (provider presets with
an auto-fetched model list).

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

### Phone app (pack the chat page into an APK)

The chat page can live on your phone, so you can talk to the pet while away:

1. Right-click the desktop pet → **"Copy chat page address"** (the URL carries the token).
2. Run `tools\apk\build_apk.cmd` (double-click; it reads the clipboard by default) — or
   `.\build_apk.ps1 -Url "http://…/?k=…" -Label "Address 1"`.
3. `desktop-pet-chat.apk` appears in the current folder. Install it (Android 7+) and one
   button gives you the history, chatting, photos and head pats.

Requirements (JDK 17 / Gradle 8.x / Android SDK 34), all parameters and the usual traps
(cleartext http, self-signed certificates, WebView photo picker) are in
[tools/apk/README.en.md](tools/apk/README.en.md).

Note: only the **builder and project template** live in this repository (no address and no
token); releases never ship an apk — keep your generated apk local.

### Common actions

- **Chat**: press Enter in the input box below the pet.
- **Images**: drag a PNG/JPG/WEBP/GIF onto the pet, or take a screenshot
  (Win+Shift+S) and press Ctrl+V in the input box, or right-click the pet →
  "Send image…". It comments on the picture, and later text questions stay in
  the same conversation.
- **Phone / tablet**: right-click the pet → "Copy chat page address" and open it
  on a device on the same WiFi. The page refreshes every 2 seconds (replies appear
  as soon as the pet answers) and follows the newest message by default (sending
  your own message always jumps to the latest); while you scroll back through old
  messages it stays put and only shows a "有新消息 ↓" hint until you tap it or
  scroll to the bottom. Its header shows the affection and offers a
  "摸头" (head-pat) button identical to clicking the pet, and its input box sends
  messages exactly like the pet's own input box. Next to it a "图片" button sends
  a photo/gallery image, exactly like dropping an image on the desktop pet
  (large photos are downscaled on the phone before upload); sent images show up in
  the log itself (tap to open the original). The `?k=…` in the URL is the
  access token (generated on first run, stored in `config.json`); set
  `webchat_enabled` to `false` to turn the page off.
- **Put it to sleep**: just say "晚安" (good night) or "午安" (nap) — it answers, then
  sleeps. While asleep any interaction only gets "呼……呼……". To wake it early, set
  `sleep_until` to `0` in `config.json` and restart (or wait for the wake time).
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

On startup the pet checks whether it can actually reach the chat UI (the bundled
service self-checks and reports it on `/health` as `loggedIn`), so an expired
session is surfaced right away instead of showing up as a mysteriously failed
chat; a failed chat also tells you it is a login problem.

Click "Rebind" on the settings AI tab: the old browser login profile is renamed
to a backup (`vendor/DeepSeekWeb2API/data/user-data.bak-<timestamp>`, newest 3
kept) before a fresh DeepSeek login browser opens, so you can re-login or switch
accounts.

Rebinding never touches the conversations in your DeepSeek account (they live on
the server) nor the local `chat_history.json` — it only swaps the local browser
profile, and it backs that up instead of deleting it.

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
- Chat page: `webchat_enabled`, `webchat_port` (default 8848), `webchat_bind`
  (default 0.0.0.0; use 127.0.0.1 for this machine only), `webchat_token`;
- Balance/work status: `accounts`, `poll_interval_sec`, `show_balance`,
  `work_label_enabled`, `work_state_hold_sec`;
- Others: `self_talk_enabled`, `self_talk_interval`, `chat_history_max`,
  `auto_start`.

## Development & testing

```bash
python tests/offscreen_smoke.py   # offscreen self-check (209 checks)
PET_SMOKE=1 python main.py        # smoke run, exit 0 = pass
tools\apk\build_apk.cmd           # pack the chat page into a phone APK (see tools/apk/README.md)
```

## Related projects

* [desktop-pet](https://github.com/toki-2004/desktop-pet) (archived): the
  original project this one evolved from.
* [png-q-bounce](https://github.com/toki-2004/png-q-bounce): turn one PNG into a
  bouncy GIF (plays once, transparent background) — usable as a head-pat skin.

## Security note

`ai_api_key` and balance account keys in `config.json` are stored in plain text —
never commit or share them.

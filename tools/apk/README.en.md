# Chat-page APK builder

Turns the desktop pet's chat web page into a phone app: the **address (host:port) is baked in
at build time, the access key is typed inside the app** (once, then it is remembered) — so no
typing the URL ever again, and one app can serve many chat histories: change the key, no rebuild.

English | [中文](README.md)

## Four steps

1. Right-click the desktop pet → **"Copy chat page address"** (the URL carries the access
   key `?k=…`). Only the address is used; the key is never written into the apk — the script
   just echoes it masked so you know what to type.
2. In this folder, run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build_apk.ps1
   ```

   The script reads the URL **straight from the clipboard** (or asks you to paste it).
   You can also pass it explicitly:

   ```powershell
   .\build_apk.ps1 -Url "http://192.168.1.5:8848/?k=abcd1234" -Label "Address 1"
   ```

3. A few seconds later `desktop-pet-chat.apk` appears in the current folder:

   ```powershell
   adb install -r .\desktop-pet-chat.apk
   ```

   …or copy the file to the phone and tap it. Android 7+ required.

4. On first launch: type the key (`webchat_token` in `config.json`, i.e. the `?k=` part of the
   chat page URL) into the key box, then tap the address button. It is remembered from then on.

## Parameters

| Parameter | Meaning | Default |
|-----------|---------|---------|
| `-Url` | chat page URL to build from (a `?k=` key is allowed but never written into the apk) | clipboard, then prompt |
| `-Label` | text of the single button | `Open chat` |
| `-OutFile` | where to write the apk | `desktop-pet-chat.apk` in the current folder |
| `-GradleHome` | Gradle 8.x install dir | `GRADLE_HOME`, else `gradle` from PATH |
| `-AndroidSdk` | Android SDK dir | `ANDROID_SDK_ROOT` / `ANDROID_HOME` |

## Requirements

- **JDK 17** (`java -version`)
- **Gradle 8.x** (e.g. unzip to `D:\gradle-8.7`, then `setx GRADLE_HOME D:\gradle-8.7`)
- **Android SDK** with `platforms;android-34` and `build-tools;34.0.0`
- First build downloads the Android Gradle Plugin (Aliyun mirrors are preconfigured)

## Notes

- The app is **one address + one button** (plus the key box): the address is baked in at build
  time, the key is typed in the app, and tapping the button opens `address + ?k=key` inside a
  WebView; the back button returns to that screen.
- **The key is never compiled into the apk** — it only lives in the app's private settings on
  the phone. So rotating the key (e.g. switching to another chat history, or `webchat_token`
  changing) needs no rebuild; changing the **address** (LAN IP moved, another tunnel) does.
- An empty key still opens the page; the page itself then says the token is wrong.
- Cleartext http needs `usesCleartextTraffic` (already in the template); self-signed https
  (e.g. your own tunnel) is allowed for that baked-in address so the WebView does not go blank.
- The page's photo button needs `WebChromeClient.onShowFileChooser`, otherwise tapping it
  does nothing inside a WebView (implemented in the template).
- `template/` contains no personal address and is safe to keep in version control; keep the
  generated apk out of the repository.

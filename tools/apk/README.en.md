# Chat-page APK builder

Turns the desktop pet's chat web page into a phone app: one button, then you can read the
history and talk to the pet (text, photos, head pats) without typing the URL every time.

English | [中文](README.md)

## Three steps

1. Right-click the desktop pet → **"Copy chat page address"** (the URL carries the access
   token `?k=…`).
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

## Parameters

| Parameter | Meaning | Default |
|-----------|---------|---------|
| `-Url` | chat page URL (with its `?k=` token) | clipboard, then prompt |
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

- The app has exactly one button: it opens the URL you baked in, inside a WebView; the back
  button returns to that button screen.
- The URL (including its token) is **compiled into the apk**. Changing the address, the
  token (`webchat_token` in `config.json`) or the LAN IP means rebuilding.
- Cleartext http needs `usesCleartextTraffic` (already in the template); self-signed https
  (e.g. your own tunnel) is allowed for that baked-in address so the WebView does not go blank.
- The page's photo button needs `WebChromeClient.onShowFileChooser`, otherwise tapping it
  does nothing inside a WebView (implemented in the template).
- `template/` contains no personal address and is safe to keep in version control; keep the
  generated apk out of the repository.

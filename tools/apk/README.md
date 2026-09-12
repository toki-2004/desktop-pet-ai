# 聊天网页 APK 打包工具

把桌宠的聊天记录网页打包成一个手机 App：装好后点一下按钮就能看聊天记录、和桌宠说话
（发文字、发图、摸头都在），不用每次输网址。

[English](README.en.md) | 中文

## 用起来（三步）

1. 右键桌面上的桌宠 →「**复制聊天记录网页地址**」（地址里带着访问口令 `?k=…`）。
2. 在本目录打开 PowerShell，运行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\build_apk.ps1
   ```

   脚本会**直接读剪贴板**里的地址（没有的话会提示你粘贴）。想自己指定也行：

   ```powershell
   .\build_apk.ps1 -Url "http://192.168.1.5:8848/?k=abcd1234" -Label "地址1"
   ```

3. 几十秒后当前目录会出现 `desktop-pet-chat.apk`。装到手机：

   ```powershell
   adb install -r .\desktop-pet-chat.apk
   ```

   或者把 apk 拷到手机（微信/QQ/USB 都行）点安装。要求 Android 7 以上。

## 参数

| 参数 | 说明 | 默认 |
|------|------|------|
| `-Url` | 聊天网页地址（带 `?k=` 口令） | 读剪贴板，读不到就提示粘贴 |
| `-Label` | App 里那个按钮的文字 | `Open chat` |
| `-OutFile` | 输出的 apk 路径 | 当前目录 `desktop-pet-chat.apk` |
| `-GradleHome` | Gradle 安装目录（8.x） | 环境变量 `GRADLE_HOME`，或 PATH 里的 `gradle` |
| `-AndroidSdk` | Android SDK 目录（含 platforms;android-34、build-tools;34.0.0） | 环境变量 `ANDROID_SDK_ROOT` / `ANDROID_HOME` |

## 环境要求

- **JDK 17**（`java -version` 能看到 17）
- **Gradle 8.x**：例如解压到 `D:\gradle-8.7`，然后 `setx GRADLE_HOME D:\gradle-8.7`
- **Android SDK**：需要 `platforms;android-34` 与 `build-tools;34.0.0`
  （只装了 cmdline-tools 的话：`sdkmanager "platforms;android-34" "build-tools;34.0.0"`）
- 首次构建要从 Maven 拉 AGP 依赖（脚本里用的是阿里云镜像，国内更快）

## 说明

- 生成出来的 App 就是**一个按钮**：点开在应用内打开你填的那个网址，返回键回到按钮页。
- 地址（含口令）是**打包时写死**在 apk 里的。换了地址 / 换了口令（`config.json` 的
  `webchat_token`）/ 局域网 IP 变了，都要重新打包。
- 明文 http 需要在清单里允许（模板已加 `usesCleartextTraffic`）；自签名 https（例如自建隧道）
  在 WebView 里会 SSL 报错，模板已对**这个预置地址**放行，不会白屏。
- 手机页面里的「图片」按钮要能拉起相册/相机，需要 `WebChromeClient.onShowFileChooser`
  （模板已实现，否则 WebView 里点了没反应）。
- `template/` 里不含任何个人地址，可以安全地跟进版本库；生成的 apk 请勿入库。

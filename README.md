# desktop-pet — 桌宠核心

基于 PyQt5 的桌面宠物核心：透明置顶、可拖动，支持思考云线通知、DeepSeek 开放平台
余额实时显示、高峰/空闲时段提醒、外观自定义。

## 功能

1. **思考云线通知**：触发动作时在桌宠上方弹出云线气泡，文字居中显示；
   默认白底深蓝描边，颜色与文本均可自定义（取色器含吸管与十六进制颜色码输入）。
2. **多平台余额实时显示**：轮询已绑定账号的平台余额（内置 DeepSeek、
   Kimi/Moonshot、SiliconFlow 硅基流动，适配器架构可扩展）；余额增加时绿色
   浮动文字动画，减少时红色浮动文字动画；右键菜单可开关余额常态显示；
   账号按"平台 + API Key"管理，支持绑定多个账号并跳转各平台官网。
3. **高峰/空闲时段切换通知**：高峰时段（北京时间周一至周五 9:00-12:00、
   14:00-18:00）与空闲时段切换时弹出通知，持续显示直到用户确认。
4. **外观自定义**：可导入 PNG/GIF 更改桌宠外观；默认图片
   `assets/deepseek拟人.png`。
5. **滚轮缩放**：鼠标悬停桌宠时滚动滚轮可放大/缩小图片或动图（比例自动记忆）。
6. **左键交互**：**按住**桌宠立即循环播放"摸头"动图，松开恢复；
   单击不再触发；若设置的是图片，按住期间显示该图片；默认素材 `assets/ds摸头.gif`，
   可在设置中更换。
7. **摸头语录**：**长按**桌宠（默认按住 0.6 秒）随机弹出摸头语录；按住期间可按
   设置的间隔持续换语录；摸头语录与自言自语是两个独立语录库，互不干扰。
8. **自言自语**：挂机时按随机间隔从可自定义文本库中弹出云线通知，
   像桌宠在"自言自语"；文本库、开关、间隔均可在设置中调整。
9. **语录库 JSON 化**：摸头与自言自语语录均改为独立的 JSON 文件存储
   （`pet_head_quotes.json` / `self_talk_quotes.json`），首次运行自动生成预置默认
   语录库；旧版 `self_talk.txt` 会自动迁移为 JSON（原文件保留）。
10. **窗口置顶开关**：设置中可统一控制"显示在最上层"，通知、桌宠、余额文本、
    浮动字四种窗口同步切换，不会出现"通知置顶但余额文本不置顶"的情况。
11. **余额显示美化**：余额常驻文本移至图片右上方，白底黑字，字号可调。
12. **设置热生效**：修改任何设置（账号、外观、通知、自言自语、置顶、刷新频率等）后立即生效，
   无需重启。
13. **基础交互**：左键拖动桌宠，位置自动记忆；右键呼出菜单。
14. **开机自启**：右键菜单可开关"开机自启"（写入当前用户 Run 键，无需管理员，
    开机后用 pythonw 静默启动）。

## 效果展示

| 默认外观 | 自言自语通知 |
| --- | --- |
| ![默认外观](assets/screenshots/default_appearance.png) | ![自言自语](assets/screenshots/self_talk.png) |

| 通知与绿色浮动动画 | 摸头交互 |
| --- | --- |
| ![通知测试](assets/screenshots/notification_test.png) | ![摸头](assets/screenshots/pet_interact.png) |

## 下载

最新版本可在 [Releases](https://github.com/toki-2004/desktop-pet/releases) 页面下载。

## 环境要求

- Windows 10/11
- Python 3.9+（本机 Python 3.13 已验证）
- 依赖：PyQt5、requests（见 `requirements.txt`）

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

## 使用说明

- **左键拖动**：移动桌宠位置（自动保存）。
- **滚轮缩放**：光标在桌宠上时滚动滚轮，放大（向上）/缩小（向下）。
- **左键按住**：立即播放交互动图（摸头），循环直到松开；单击不触发。
- **左键长按**（默认 0.6 秒）：额外弹出摸头语录；按住期间按设置间隔持续换语录。
- **右键菜单**：
  - 余额常态显示：开关余额文本的常驻显示；
  - 开机自启：开关随系统启动；
  - 绑定/管理账号：添加或删除 DeepSeek 账号；
  - 通知设置：自定义通知文本、高峰/空闲文本、云线填充色与描边色；
  - 更换外观：导入 PNG/GIF、窗口置顶开关、摸头语录库编辑；
  - 发送测试通知：验证云线与浮动动画；
  - 退出。

## 配置说明

配置文件为项目根目录的 `config.json`（自动生成，已加入 `.gitignore`）：

- `balloon_fill` / `balloon_outline`：云线填充色与描边色（十六进制）；
- `balloon_text`：默认通知文本；
- `peak_balloon_text` / `idle_balloon_text`：高峰/空闲开始提示文本；
- `pet_image`：桌宠图片路径（PNG/GIF）；
- `pet_scale`：缩放比例（滚轮调整，自动保存）；
- `pet_interact_image`：左键交互图片/动图路径（PNG/GIF）；
- `pet_pos`：桌宠位置；
- `show_balance`：余额常态显示开关；
- `balance_font_size`：余额字号（9-24）；
- `poll_interval_sec`：余额轮询间隔（秒，默认 3，可在设置面板调整，最低 1）；
- `always_on_top`：窗口置顶开关（通知/桌宠/余额文本/浮动字同步）；
- `self_talk_enabled` / `self_talk_texts` / `self_talk_interval` / `self_talk_file`：
  自言自语开关、默认文本、间隔（秒）、语录库 JSON 文件路径；
- `pet_head_enabled` / `pet_head_texts` / `pet_head_interval` / `pet_head_long_press_ms` /
  `pet_head_file`：摸头语录开关、默认文本、按住期间换语录间隔（秒）、长按判定（毫秒）、
  语录库 JSON 文件路径；
- `auto_start`：开机自启开关（与注册表 Run 键同步）；
- `accounts`：账号名 → `{"platform": "平台ID", "api_key": "..."}`；
  旧格式（直接存 Key 字符串）会自动迁移为 DeepSeek 账号。

## DeepSeek 账号绑定

1. 右键菜单 → 绑定/管理账号 → 添加账号；
2. 选择平台（DeepSeek / Kimi / 硅基流动），点击"在浏览器打开平台官网"获取 API Key；
3. 填写账号名称与 API Key，保存后即开始轮询余额。

当前支持的余额接口：

- DeepSeek：`GET https://api.deepseek.com/user/balance`（已验证）；
- Kimi (Moonshot)：`GET https://api.moonshot.cn/v1/users/me/balance`（按官方文档实现）；
- SiliconFlow 硅基流动：`GET https://api.siliconflow.cn/v1/user/info`（按官方文档实现）。

其他平台可在 `platforms.py` 中按同一接口（`fetch(api_key) -> (余额, 币种)`）扩展。

## 高峰时段定义

高峰时段为北京时间周一至周五 9:00-12:00、14:00-18:00；其余时间均为空闲时段。
时段切换时弹出通知并持续显示，直到点击"知道了"或气泡确认。

## 打包（可选）

面向用户分发时可用 PyInstaller 打包：

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --name DesktopPet --add-data "assets;assets" main.py
```

打包说明：`config.json` 不打包（含 API Key），首次运行会在 exe 同目录自动生成；
自带素材与两个默认语录库（`assets/*_quotes.json`）从打包目录解出，可自定义。

## 安全提示

`config.json` 中保存的 DeepSeek API Key 为明文，请勿将该文件提交到任何仓库或
外传；建议为桌宠单独创建 Key，并在平台侧设置限额。

# desktop-pet-ai · AI 桌宠

> **语言：** 中文 | [English](README.en.md)

基于 PyQt5 的 AI 驱动桌宠：透明置顶、可拖动、可缩放，所有文本
（自言自语 / 摸头反应 / 聊天回复）由 OpenAI 兼容 API 实时生成，不依赖任何语录库。

## 功能

1. **AI 实时生成**：自言自语、摸头反应、聊天回复全部调用 OpenAI 兼容的
   `/v1/chat/completions` 接口实时生成；system prompt 由人设 + 当前情境
   （时段 / 好感档位 / 天气 / 触发标签）+ 最近对话历史组成。
2. **内置免费 AI（DeepSeekWeb2API）**：项目内置 `vendor/DeepSeekWeb2API`
   （便携 Node 版本，需本地准备，不入 Git）。第一次启动会弹出 DeepSeek
   登录浏览器，登录并关闭控制台窗口后服务自动在 `127.0.0.1:3000` 拉起，
   之后启动不再弹窗；登录失效时在设置页点"重新绑定"即可。若 3000 端口已有
   web2api 服务（如手动启动的），会直接复用。
3. **厂商预设**：设置页提供预设下拉——DeepSeekWeb2API（内置免费）/ 硅基流动 /
   Kimi / 自定义；选预设自动填 base_url，并自动从该平台的 `/v1/models`
   拉取候选模型到模型下拉框（可手动输入），云端服务只需填 API Key。
4. **聊天输入框**：桌宠下方常驻可输入文本框（可拖动、滚轮调字号、位置记忆），
   回车即与 AI 对话。
5. **摸头反应**：单击桌宠播放一次摸头动画并触发 AI 反应；长按 = 拖动，不触发。
6. **自言自语（情境触发）**：沿袭原版触发逻辑——时段窗口（早/午/下午/晚/深夜，
   每段每天一次）、周末、久坐 45 分钟提醒、90 分钟未互动求关注、好感档位切换、
   天气变化（自动定位 + Open-Meteo 实时天气）、随机闲聊（间隔可设）。
6. **聊天记录**：全部消息（含自言自语）按 JSON 落盘（条数上限可设），跨重启记忆；
   右键菜单"聊天记录…"可查看。上下文条数可设，只取 user/assistant 消息。
7. **失败兜底**：AI 请求失败显示兜底文本（"唔……我现在有点短路了"），
   可在设置关闭。
8. **云线通知**：动作触发时弹出云线气泡，填充色/描边色/文本/字号可自定义。
9. **外观**：导入 PNG/GIF 更换皮肤（默认 `assets/ds拟人.png`，摸头动画默认
   `assets/ds拟人_q.gif`，只播一遍、保留透明背景）；窗口置顶可在设置切换。
10. **好感度系统**：摸头/互动增加好感，闲置按时间衰减；高/中/低档位影响 AI
    语气与触发；可显示"好感"小标签，全部参数（初始值/上限/增量/衰减/阈值）可设。
11. **时段状态标签**：高峰/空闲时段标签常驻显示（自定义文本），气泡确认。
12. **位置/大小记忆与一键召回**：退出时自动记住桌宠位置与大小，下次启动原样
    恢复；托盘菜单"一键召回"把桌宠移到当前屏幕正中间（不改变大小），防止
    桌宠掉到屏幕外无法操作。

AI 消息一律不用强通知：以气泡/标签呈现，聊天内容落盘供事后查看。

## 环境要求

- Windows 10/11
- Python 3.9+
- 依赖：PyQt5、requests、Pillow（见 `requirements.txt`）
- 内置免费 AI 需在 `vendor/DeepSeekWeb2API` 放入 DeepSeekWeb2API 便携包
  （node/、node_modules/、src/、config.json；仓库不含，见上方说明），
  或改用任意云端 OpenAI 兼容 Key

## 安装与运行

```bash
pip install -r requirements.txt
python main.py
```

首次使用：右键托盘/桌宠 → 通知设置 → AI 页 → 选预设、填 API Key（模型可改）。

> DeepSeekWeb2API 本机服务地址默认 `http://127.0.0.1:8000/v1`，
> 端口以该项目 `config.json` 为准。

## 使用说明

- **左键拖动**：移动桌宠（自动保存）；**滚轮**：缩放。
- **左键单击**：播放摸头动画 + AI 反应；连点从头重放；拖动不触发。
- **聊天输入框**：回车发送；可拖动，滚轮调字号。
- **托盘**：左键显示/隐藏桌宠；右键菜单：聊天记录、开机自启、通知设置、
  更换外观、发送测试通知、退出。

## 配置说明

配置文件为项目根目录 `config.json`（自动生成，原子写入并保留 `.bak` 备份）。
常用项：

- 通知/外观：`balloon_fill`、`balloon_outline`、`balloon_text`、
  `balance_font_size`（全局字号）、`pet_image`、`pet_interact_image`、
  `pet_scale`、`pet_pos`、`always_on_top`；
- 好感：`affection_*`（启用/初始值/上限/增量/衰减/阈值/标签开关等）；
- 自言自语：`self_talk_enabled`、`self_talk_interval`（随机闲聊间隔秒数）；
- AI：`ai_preset`、`ai_base_url`、`ai_api_key`、`ai_model`、`ai_persona`、
  `ai_context_n`（上下文条数）、`ai_fallback_enabled`、`ai_fallback_text`；
- 历史：`chat_history_max`（落盘条数上限）、`chat_input_offset`（输入框位置）；
- `auto_start`：开机自启（与注册表 Run 键同步）。

## 开发与测试

离屏自检（无需 GUI，覆盖动图播放/拖动单击区分/好感/触发器/历史/输入框/天气）：

```bash
python tests/offscreen_smoke.py
```

冒烟：`PET_SMOKE=1 python main.py`（自动退出，exit=0 即通过）。

## 相关项目

* [png-q-bounce](https://github.com/toki-2004/png-q-bounce)：把一张 PNG 一次性做成
  Q 弹 GIF（只播一遍、保留透明背景），可直接用作摸头动画皮肤。

## 安全提示

`config.json` 中保存的 `ai_api_key` 为明文，请勿提交到仓库或外传。

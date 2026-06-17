# A5-景区导览AI数字人

## 项目概述

第十五届"中国软件杯"A5 赛题作品。基于 Open-LLM-VTuber 二次开发，整合 DeepSeek LLM + Dify RAG 知识库 + FunASR 语音识别 + Edge-TTS 语音合成 + Live2D 数字人，实现游客与景区数字人导游的语音/文本自然对话。**纯 CPU 运行，零 GPU 依赖。**

核心使用流程：用户语音/文字提问 → FunASR/Web Speech 转文字 → Dify RAG 检索景区知识 → DeepSeek LLM 生成回答 → Edge-TTS 播报 → Live2D 口型同步。

---

## 技术栈

| 模块 | 选型 | 版本 / 关键参数 |
|------|------|----------------|
| 核心框架 | Open-LLM-VTuber (Fork) | tag v0.5.5+, 二次开发 |
| 后端框架 | FastAPI + Uvicorn | Python ≥3.10, FastAPI ≥0.110 |
| LLM | DeepSeek API | `deepseek-chat`, api.deepseek.com/v1 |
| RAG 知识库 | Dify 社区版 | Docker 部署, ≥0.10.0 |
| 语音识别 ASR | FunASR | `paraformer-zh`, device: cpu |
| 语音合成 TTS | Edge-TTS | `zh-CN-XiaoxiaoNeural`, ≥6.0 |
| 数字人 | Live2D Cubism SDK | WebGL, 音量驱动口型同步 |
| 管理后台 | Streamlit | ≥1.35, 多页面结构 |
| 数据库 | SQLite | Python 内置, 文件在 `data/` |
| 代码质量 | Ruff | line-length=120, target-version=py310 |
| 配置管理 | pydantic-settings | ≥2.0, `.env` 加载 |
| 容器化 | Docker Compose | 仅 Dify 部署用 |

---

## 目录结构

```
a5-digital-human/
├── main.py                        # FastAPI / Open-LLM-VTuber 入口
├── conf.yaml                      # LLM / TTS / ASR / Live2D 核心配置
├── .env                           # 敏感配置（不入 Git）
├── .env.example                   # 配置模板（入 Git）
├── pyproject.toml                 # Ruff 配置 + 项目元数据
├── requirements.txt               # Python 依赖清单
├── README.md                      # 项目说明 + 快速启动
│
├── backend/                       # 后端业务逻辑扩展
│   ├── config.py                  # Settings 类（pydantic-settings）
│   └── services/
│       ├── dify_client.py         # Dify 对话 API 封装
│       ├── tts_service.py         # Edge-TTS + pyttsx3 降级
│       ├── asr_service.py         # FunASR + Web Speech 降级
│       └── chatbot.py             # 对话编排（LLM + RAG + 上下文）
│
├── admin/                         # Streamlit 管理后台
│   ├── app.py                     # 多页面入口
│   ├── pages/
│   │   ├── knowledge.py           # 知识库管理：上传文档 + 列表
│   │   ├── stats.py               # 数据大屏：统计 + Top10 + 趋势
│   │   └── settings.py            # 系统设置：模型 + TTS 音色
│   └── utils/
│       └── dify_admin.py          # 后台 Dify API 封装
│
├── frontend/static/               # 前端资源（景区化改造）
│   ├── live2d/                    # Live2D 模型文件
│   └── themes/                    # 主题配色 JSON
│
├── knowledge/                     # 景区知识库原始文档（杭州西湖）
│   ├── scenic_intro.md            # 景点介绍
│   ├── ticket_info.md             # 票务信息
│   ├── dining_guide.md            # 餐饮推荐
│   ├── route_map.md               # 路线指引
│   └── faq.md                     # 常见问题 FAQ（30-50 对）
│
├── tests/                         # 测试目录
│   ├── conftest.py
│   ├── test_chat_chain.py         # 核心链路测试（≥5 用例）
│   ├── test_dify_rag.py           # RAG 检索测试
│   └── test_tts_asr.py            # 语音闭环测试
│
├── docs/                          # 文档
│   ├── architecture.md            # 架构说明 + ASCII 图
│   ├── deployment.md              # 部署手册
│   └── api-reference.md           # API 文档
│
├── scripts/                       # 运维 / 测试脚本
│   ├── setup.sh                   # 一键环境搭建
│   ├── test_accuracy.py           # 准确率测试（100 题）
│   └── download_models.py         # ASR / Live2D 模型预下载
│
└── data/                          # 运行时数据（不入 Git）
    └── conversations.db           # 对话记录 SQLite
```

---

## 核心命令

```bash
# 安装依赖
pip install -r requirements.txt

# 启动数字人服务（主窗口）
python main.py                      # → http://localhost:8000

# 启动管理后台（新终端）
streamlit run admin/app.py          # → http://localhost:8501

# 部署 Dify 知识库
cd dify/docker && docker compose up -d   # → http://localhost

# 代码质量检查（提交前必须执行）
ruff check . && ruff format .

# 运行测试
pytest tests/ -v

# 准确率测试
python scripts/test_accuracy.py     # 目标 ≥ 90%

# 预下载 ASR / Live2D 模型
python scripts/download_models.py

# 推送到 GitHub（每次编码后必须执行）
git add -A && git commit -m "type(scope): description" && git push
```

---

## 编码约定

| 规则 | 内容 |
|------|------|
| **缩进** | Python: 4 空格 / YAML: 2 空格 |
| **引号** | Python: 双引号 `"`（Ruff 强制）|
| **命名 - 文件** | 小写 + 下划线, 如 `dify_client.py` |
| **命名 - 类** | 大驼峰, 如 `DifyClient` |
| **命名 - 函数 / 方法** | 小写 + 下划线, 如 `get_scenic_info()` |
| **命名 - 常量 / 环境变量** | 大写 + 下划线, 如 `MAX_RETRIES = 3` |
| **类型注解** | 所有函数必须有完整类型签名（def func(x: int) -> str:）|
| **import 顺序** | 标准库 → 第三方 → 本地模块（Ruff-I 规则自动检查）|
| **文档** | 中文注释；函数需英文标题 docstring（一行描述）|
| **文件上限** | ≤ 500 行，超出则拆分模块 |
| **函数上限** | ≤ 50 行，超出则拆分 |
| **嵌套上限** | ≤ 4 层，超出则用提前返回 |

---

## 架构原则

1. **先理解再编码** — 读清楚现有代码的结构和约定再动手；不确定 API 行为时，先查文档或写小测试验证
2. **简单优先** — 能用标准库解决的不用第三方；能在一个文件解决的不要拆模块；不引入未要求的抽象层
3. **精准修改** — 只改必须改的文件；修 bug 时不顺手优化无关代码；不加没要求的功能
4. **目标驱动** — 每个任务明确验收标准；跑通验证再收工，不自认为"应该好了"
5. **降级优先** — 每个外部依赖（DeepSeek / Dify / Edge-TTS / FunASR）都配降级方案；主链路失败不中断服务，自动切降级
6. **日志驱动** — 关键路径写 `logger.info()`；异常链保留完整 `traceback.format_exc()`；不自己吞掉 `exception`

---

## 质量门禁

| 要求 | 阈值 | 验证方式 |
|------|------|---------|
| 问答准确率 | ≥ 90% | `python scripts/test_accuracy.py`（100 题标准测试集）|
| 端到端延迟 | < 5 秒 | 从语音输入结束到 TTS 播报开始，计时 10 次取平均 |
| Ruff 检查 | 零 Error | `ruff check .` |
| 演示视频 | ≤ 7 分钟 | H.264, 1920×1080, ≥30fps |
| 核心对话测试 | ≥ 5 用例 | `pytest tests/test_chat_chain.py -v` |
| 文件编码 | UTF-8 without BOM | `file *.py` 检查 |
| 调试语句残留 | 零残留 | 全局搜 `print(` `console.log(` |
| **代码推送** | **每次编码后必推** | `git add -A && git commit && git push` |

---

## 安全规则

- 所有 API Key（DeepSeek、Dify）从 `.env` 读取，代码中不出现明文密钥
- `.env` 必须在 `.gitignore` 中，commit 前执行 `git check-ignore .env` 确认
- 用户输入在前端渲染时使用 `textContent` 或框架转义函数，不拼接 `innerHTML`
- CORS 生产环境限制具体域名，不开放 `["*"]`
- 调试语句（`print(` / `console.log(`）提交前全部删除
- SQL 查询全部使用参数化传参，禁止字符串拼接

---

## 功能边界

### 做的功能（F1–F10）

| 编号 | 功能 | 优先级 |
|------|------|--------|
| F1 | 语音问答对话：语音→ASR→LLM+RAG→TTS→口型同步 | P0 |
| F2 | 文本问答对话：文字输入→LLM+RAG→文字+TTS 展示 | P0 |
| F3 | 景区知识库 RAG：Dify 管理景区资料，准确率 ≥ 90% | P0 |
| F4 | 多轮对话记忆：连续 3 轮以上不丢失上下文 | P1 |
| F5 | 知识库管理后台：Streamlit 上传文档→Dify API 更新 | P0 |
| F6 | 对话数据统计：总问答数、热门 Top10、日活跃趋势 | P0 |
| F7 | 情感分析：对话情感分类（积极/中性/消极） | P1 |
| F8 | 数字人配置管理：切换 Live2D 模型 + TTS 音色 | P1 |
| F9 | Live2D 口型同步：TTS 播报时随音量驱动口型 | P0 |
| F10 | 景区视觉主题：配色 #2d6a4f / #fefae0 / #d4a373 | P1 |

### 排除项（严格不做）

- ❌ 3D 数字人（魔珐 / MetaHuman / MuseTalk 等），渲染层只用 Live2D
- ❌ GPU 推理（Wav2Lip / SadTalker / LivePortrait），所有模型 CPU 运行
- ❌ 移动端原生 App，仅 Web 响应式适配手机浏览器
- ❌ 支付系统、用户注册登录体系（赛题不要求）
- ❌ 前端框架（Vue / React），沿用 Open-LLM-VTuber 自带 HTML/CSS/JS
- ❌ 实时视频流处理或摄像头功能
- ❌ 商业授权的 TTS/ASR 服务，只使用免费开源方案

---

## 配置管理

`.env` 文件结构（`.env.example` 入 Git，`.env` 不入 Git）：

```bash
# ===== LLM 配置 =====
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-key-here
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# ===== Dify 配置 =====
DIFY_API_URL=http://localhost/v1
DIFY_API_KEY=app-your-key-here
DIFY_KNOWLEDGE_BASE_ID=kb-your-id-here

# ===== 语音配置 =====
TTS_PROVIDER=edge-tts
TTS_VOICE=zh-CN-XiaoxiaoNeural
ASR_PROVIDER=funasr

# ===== 数据库 =====
DATABASE_URL=sqlite:///./data/conversations.db

# ===== 管理后台 =====
ADMIN_PASSWORD=admin123

# ===== 运行环境 =====
ENV=development
LOG_LEVEL=INFO

# ===== Live2D =====
LIVE2D_MODEL_PATH=frontend/static/live2d/default
```

`.gitignore` 必须包含：`.env`, `*.db`, `data/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.pyc`

---

## 降级方案

| 主方案 | 降级到 | 切换条件 |
|--------|--------|---------|
| Edge-TTS | pyttsx3（离线 TTS） | 网络异常或 API 403 |
| FunASR | Web Speech API（浏览器内置） | 模型加载失败或超时 > 10s |
| DeepSeek API | 通义千问 API | API 连续 3 次 5xx |
| Live2D | 静态 PNG + CSS 口型动画 | SDK 加载失败 |
| Dify RAG | 直连 DeepSeek API（无检索） | Dify 服务不可用 |

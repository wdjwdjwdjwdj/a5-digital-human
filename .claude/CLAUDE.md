# A5-景区导览AI数字人

## 项目概述

第十五届"中国软件杯"A5 赛题作品。基于 Open-LLM-VTuber 二次开发，整合 DeepSeek LLM + Dify RAG 知识库 + FunASR 语音识别 + Edge-TTS 语音合成 + Three.js VRM 3D 数字人，实现游客与景区数字人导游的语音/文本自然对话。**纯 CPU 运行，零 GPU 依赖。**

核心使用流程：用户语音/文字提问 → FunASR/Web Speech 转文字 → Dify RAG 检索景区知识 → DeepSeek LLM 生成回答 → Edge-TTS 播报 → VRM 3D 数字人口型同步。

---

## 技术栈

| 模块 | 选型 | 版本 / 关键参数 |
|------|------|----------------|
| 核心框架 | FastAPI + Uvicorn | Python ≥3.10, FastAPI ≥0.110 |
| LLM | DeepSeek API | `deepseek-chat`, api.deepseek.com/v1 |
| RAG 知识库 | Dify 社区版 | Docker 部署, ≥0.10.0 |
| 语音识别 ASR | FunASR | `paraformer-zh`, device: cpu |
| 语音合成 TTS | Edge-TTS | `zh-CN-XiaoxiaoNeural`, ≥6.0 |
| 数字人 | Three.js + @pixiv/three-vrm | WebGL, VRM 1.0 BlendShape 口型同步 |
| 管理后台 | Streamlit | ≥1.35, 多页面结构 |
| 数据库 | SQLite | Python 内置, 文件在 `data/` |
| 代码质量 | Ruff | line-length=120, target-version=py310 |
| 配置管理 | pydantic-settings | ≥2.0, `.env` 加载 |
| 容器化 | Docker Compose | 仅 Dify 部署用（可选，可用 local_rag 替代）|
| ASR 离线引擎 | FunASR | `paraformer-zh`, device: cpu, ⚠️ 需 `asyncio.to_thread` 避免事件循环阻塞 |
| 离线 TTS 降级 | pyttsx3 | 不含 SAPI5 驱动时可能失败 |

---

## 目录结构

```
a5-digital-human/
├── main.py                        # FastAPI 入口
├── conf.yaml                      # LLM / TTS / ASR / VRM 核心配置
├── .env                           # 敏感配置（不入 Git）
├── .env.example                   # 配置模板（入 Git）
├── pyproject.toml                 # Ruff 配置 + 项目元数据
├── requirements.txt               # Python 依赖清单
├── README.md                      # 项目说明 + 快速启动
│
├── backend/                       # 后端业务逻辑扩展
│   ├── config.py                  # Settings 类（pydantic-settings）
│   ├── http_client.py             # 全局 httpx 客户端（复用连接池）
│   ├── routes/
│   │   ├── chat.py                # 核心对话路由（/message, /voice, /stream, /stream-tts）
│   │   ├── health.py              # 健康检查
│   │   ├── scenic.py              # 景区信息 CRUD API（11 端点）
│   │   └── vrm.py                 # VRM 模型管理（从 live2d.py 迁移）
│   ├── repository/
│   │   ├── chat_repo.py           # SQLite 对话持久化（WAL 模式）
│   │   └── scenic_repo.py         # 景区数据仓储（5 表 CRUD + 种子数据）
│   └── services/
│       ├── dify_client.py         # Dify 对话 API 封装
│       ├── tts_service.py         # Edge-TTS + Kokoro + pyttsx3 三级降级
│       ├── asr_service.py         # FunASR + Web Speech 降级
│       ├── chatbot.py             # 对话编排（LLM + RAG + 上下文，三级降级）
│       └── local_rag.py           # 本地 RAG 降级（可选，Dify 不可用时用）
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
│   ├── vrm/                       # VRM 3D 模型文件 (.vrm)
│   └── themes/                    # 主题配色 JSON
│
├── knowledge/                     # 景区知识库原始文档（无锡灵山胜境）
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
│   ├── test_scenic_repo.py        # 景区仓储 CRUD 测试
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
│   └── download_models.py         # ASR / VRM 模型预下载
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

# 预下载 ASR / VRM 3D 模型
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
| **前端 ES Module** | 使用 `<script type="importmap">` 加载 Three.js / VRM CDN，不用打包工具 |
| **3D 渲染** | VRM 模型放在 `frontend/static/vrm/`，通过 URL 路径引用 |

---

## 架构原则

1. **先理解再编码** — 读清楚现有代码的结构和约定再动手；不确定 API 行为时，先查文档或写小测试验证
2. **简单优先** — 能用标准库解决的不用第三方；能在一个文件解决的不要拆模块；不引入未要求的抽象层
3. **增量修改（重）** — 基于现有代码做增量补全，不覆盖已有实现。已有文件只做字段级修改（Edit），不做整体 Write 覆盖
4. **精准修改** — 只改必须改的文件；修 bug 时不顺手优化无关代码；不加没要求的功能
5. **目标驱动** — 每个任务明确验收标准；跑通验证再收工，不自认为"应该好了"
6. **降级优先** — 每个外部依赖（DeepSeek / Dify / Edge-TTS / FunASR / Three.js VRM）都配降级方案；主链路失败不中断服务，自动切降级
7. **日志驱动** — 关键路径写 `logger.info()`；异常链保留完整 `traceback.format_exc()`；不自己吞掉 `exception`
8. **3D 降级渲染** — VRM 模型加载失败自动切静态头像（CSS 动画口型），不阻塞对话流程
9. **配置统一管理** — 所有运行时配置从 `.env` 通过 pydantic-settings 加载，`conf.yaml` 仅做配置参考文档
10. **Token 节省优先** — 每次 LLM API 调用都应考虑 Token 消耗（见下方 Token 节省策略）

---

## Token 节省策略

| 机制 | 实现位置 | 效果 |
|------|---------|------|
| **历史压缩** | `chatbot.py _auto_compress()` | 6 轮后自动将旧对话压缩为 system 级摘要（≤300 Token），保留最近 4 轮原始消息。单轮省 60-80% 历史 Token |
| **高频问答缓存** | `chatbot.py _check_cache()` | LRU 缓存最近 20 条问答。精确命中时零 API 调用。适用："你好"、"门票"等重复高频 |
| **自适应 max_tokens** | `chatbot.py chat()` | 短查询（≤10 字）用 256 tokens，长查询用 1024 tokens。短问题省 75% output tokens |
| **超预算熔断** | `chatbot.py chat()` | 单会话 Token 超 8192 后自动清空历史重新开始，防止无限膨胀 |
| **精简 System Prompt** | `chat.py _SCENIC_CONTEXT` | 从 128 字压缩至 78 字，每轮省 ~50 input tokens |
| **Token 统计监控** | `GET /token-stats` | 实时查看总消耗、缓存命中率、已压缩会话数 |

> 预计可节省 40-60% API Token 消耗（高频场景更显著）。

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
| VRM 模型加载 | 模型可加载 | 打开首页，3D 数字人渲染正常，控制台无 Three.js 错误 |
| 配置一致性 | conf.yaml 与 .env 值一致 | `diff <(grep -v '^#' conf.yaml) <(grep -v '^#' .env)` 无冲突 |
| 默认密码检查 | 不残留 admin123 | `grep "admin123" backend/config.py` 零匹配 |
| 路径遍历防护 | 所有文件路径路由有安全检查 | `backend/routes/*.py` 中不含 `..` 拼接 |
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
| F8 | 数字人配置管理：切换 VRM 3D 模型 + TTS 音色 | P1 |
| F9 | VRM 口型同步：TTS 播报时通过 BlendShape 驱动口型 | P0 |
| F10 | 景区视觉主题：配色 #2d6a4f / #fefae0 / #d4a373 | P1 |

### 排除项（严格不做）

- ❌ 2D Live2D 渲染（已迁移至 3D VRM 方案，前端用 Three.js + @pixiv/three-vrm）
- ❌ GPU 推理（Wav2Lip / SadTalker / LivePortrait），所有模型 CPU 运行
- ❌ 移动端原生 App，仅 Web 响应式适配手机浏览器
- ❌ 支付系统、用户注册登录体系（赛题不要求）
- ❌ 前端框架（Vue / React），沿用原生 HTML/CSS/JS + ESM importmap
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

# ===== 降级 LLM 配置（必须配置，否则 DeepSeek 故障时降级断链） =====
FALLBACK_LLM_PROVIDER=qwen
FALLBACK_LLM_API_KEY=your-key-here
FALLBACK_LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

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

# ===== 管理后台（⚠️ 必须修改默认值，不允许 admin123） =====
ADMIN_PASSWORD=your-strong-password-here

# ===== 运行环境 =====
ENV=development
LOG_LEVEL=INFO

# ===== 3D VRM 数字人 =====
VRM_MODEL_URL=frontend/static/vrm/AliciaSolid.vrm
```

`.gitignore` 必须包含：`.env`, `*.db`, `data/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `*.pyc`

---

## 降级方案

| 主方案 | 降级到 | 切换条件 |
|--------|--------|---------|
| Edge-TTS | pyttsx3（离线 TTS） | 网络异常或 API 403 |
| FunASR | Web Speech API（浏览器内置） | 模型加载失败或超时 > 10s |
| DeepSeek API | 通义千问 API | API 连续 2 次 5xx（滑动窗口切换）|
| Three.js VRM | 静态 PNG + CSS 口型动画 | VRM 模型加载失败 |
| Dify RAG | 本地 langchain+faiss 检索 → 直连 DeepSeek（无检索） | Dify 服务不可用 |

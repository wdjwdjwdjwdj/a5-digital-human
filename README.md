# A5-景区导览AI数字人

第十五届"中国软件杯"A5 赛题作品。基于 Open-LLM-VTuber 二次开发，整合 DeepSeek LLM + Dify RAG 知识库 + FunASR 语音识别 + Edge-TTS 语音合成 + Three.js VRM 3D 数字人，实现游客与景区数字人导游的语音/文本自然对话。

**纯 CPU 运行，零 GPU 依赖。**

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key

# 启动数字人服务
python main.py

# 启动管理后台
streamlit run admin/app.py
```

## 技术栈

- LLM: DeepSeek API
- RAG: Dify 社区版
- ASR: FunASR (paraformer-zh)
- TTS: Edge-TTS
- 数字人: Three.js + @pixiv/three-vrm (3D VRM)
- 后端: FastAPI
- 管理后台: Streamlit

## 目录结构

见 [.claude/CLAUDE.md](.claude/CLAUDE.md)。

## 质量门禁

- 问答准确率 ≥ 90%
- 端到端延迟 < 5 秒
- Ruff 检查零 Error

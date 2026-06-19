from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从 .env 文件加载。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ===== LLM =====
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # ===== 降级 LLM（DeepSeek 连续故障时自动切换）=====
    fallback_llm_provider: str = "qwen"  # 预留字段，当前由 fallback_llm_model 决定模型名
    fallback_llm_model: str = "qwen-turbo"
    fallback_llm_api_key: str = ""
    fallback_llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # ===== Dify =====
    dify_api_url: str = "http://localhost/v1"
    dify_api_key: str = ""
    dify_knowledge_base_id: str = ""

    # ===== 语音 =====
    tts_provider: str = "edge-tts"
    tts_voice: str = "zh-CN-XiaoxiaoNeural"
    asr_provider: str = "funasr"

    # ===== 数据库 =====
    database_url: str = "sqlite:///./data/conversations.db"

    # ===== 管理后台 =====
    admin_password: str = ""  # ⚠️ 生产环境必须修改

    # ===== 运行环境 =====
    env: str = "development"
    log_level: str = "INFO"
    cors_origin: str = "*"
    api_base_url: str = "http://localhost:8000"

    # ===== VRM 3D =====
    vrm_model_url: str = "frontend/static/vrm/AliciaSolid.vrm"


settings = Settings()

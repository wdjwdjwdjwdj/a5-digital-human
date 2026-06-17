from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，从 .env 文件加载。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ===== LLM =====
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

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
    admin_password: str = "admin123"

    # ===== 运行环境 =====
    env: str = "development"
    log_level: str = "INFO"

    # ===== Live2D =====
    live2d_model_path: str = "frontend/static/live2d/default"


settings = Settings()

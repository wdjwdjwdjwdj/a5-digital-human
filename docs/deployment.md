# 部署手册

## 环境要求

- Python ≥ 3.10
- pip
- Docker & Docker Compose（仅 Dify 部署需要）

## 快速部署

### 1. 克隆项目
```bash
git clone <repo-url>
cd a5-digital-human
```

### 2. 安装依赖
```bash
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env，填入 DeepSeek API Key 和 Dify API Key
```

### 4. 启动 Dify（可选）
```bash
cd dify/docker && docker compose up -d
```

### 5. 启动服务
```bash
python main.py              # → http://localhost:8000
streamlit run admin/app.py  # → http://localhost:8501
```

## 测试

```bash
pytest tests/ -v
python scripts/test_accuracy.py
ruff check .
```

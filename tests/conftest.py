"""测试配置。"""

import sys
from pathlib import Path
from unittest.mock import MagicMock

# 将项目根目录加入 sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── 预加载 python_multipart mock（FastAPI /voice 路由需要，但测试环境可能未安装）────
if "python_multipart" not in sys.modules:
    _mock = MagicMock()
    _mock.__version__ = "99.0.0"
    # multipart 子模块也需要 mock（新版 fastapi 可能检查 multipart.multipart）
    _mock.multipart = MagicMock()
    _mock.multipart.parse_options_header = MagicMock()
    sys.modules["python_multipart"] = _mock
    sys.modules["multipart"] = _mock
    sys.modules["multipart.multipart"] = _mock.multipart

# ── 预加载 cachetools mock（chatbot.py 依赖，测试环境可能未安装）────
if "cachetools" not in sys.modules:
    from unittest.mock import MagicMock as _MM

    class _MockTTLCache(dict):
        """OrderedDict 降级实现，模拟 cachetools.TTLCache 基本接口。"""

        def __init__(self, maxsize: int = 1024, ttl: int = 1800, **kwargs):  # noqa: ARG002
            super().__init__()
            self.maxsize = maxsize
            self.ttl = ttl

        def popitem(self) -> tuple:
            return super().popitem() if self else ("", "")

    _cm = _MM()
    _cm.TTLCache = _MockTTLCache
    sys.modules["cachetools"] = _cm

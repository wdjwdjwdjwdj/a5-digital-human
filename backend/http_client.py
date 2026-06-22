"""全局 HTTP 客户端（复用连接池，跳过 SSL 验证）。"""

from httpx import AsyncClient, Limits, Timeout

_client: AsyncClient | None = None


def get_http_client() -> AsyncClient:
    """获取全局 HTTP 客户端（单例，复用连接池）。

    Returns:
        配置好的 AsyncClient 实例
    """
    global _client
    if _client is None:
        _client = AsyncClient(
            verify=False,
            timeout=Timeout(30.0),
            limits=Limits(max_keepalive_connections=20, max_connections=100),
        )
    return _client

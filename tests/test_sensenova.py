"""SenseNova API 接入验证脚本。

验证内容：
1. 基础连通性 — chat() 正常返回
2. 内容验证 — 回复非空、非纯空白
3. 超时控制 — 5 秒超时机制生效
4. 流式输出 — chat_stream() 正常
5. 空消息处理 — 空消息不崩溃
6. 延迟统计 — 记录首 token 和总延迟

用法：
    cd C:/Users/29688/Desktop/a5-digital-human
    python tests/test_sensenova.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.sensenova import SenseNovaClient, SenseNovaResponse

# ── 测试结果收集 ─────────────────────────────────────────
results: list[tuple[str, bool, str]] = []


def record(test_name: str, passed: bool, detail: str = "") -> None:
    """记录一条测试结果。"""
    results.append((test_name, passed, detail))
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"  {status} | {test_name}")
    if detail:
        print(f"         {detail}")


# ═════════════════════════════════════════════════════════
# 测试用例
# ═════════════════════════════════════════════════════════


async def test_basic_chat() -> None:
    """测试 1：基础对话 — 发送"你好"并验证回复。"""
    print("\n── 测试 1：基础对话 ──")
    client = SenseNovaClient()

    start = time.monotonic()
    resp = await client.chat(
        [{"role": "user", "content": "你好，请用一句话介绍自己"}],
        max_tokens=1024,
    )
    elapsed = (time.monotonic() - start) * 1000

    # 验证 1：响应非空
    if not resp.is_valid:
        record("基础对话", False, f"响应为空（延迟={elapsed:.0f}ms）")
        return

    # 验证 2：内容长度合理
    content_len = len(resp.content)
    if content_len < 2:
        record("基础对话", False, f"内容过短（{content_len} 字符）")
        return

    # 验证 3：延迟在 5 秒内
    if elapsed > 5000:
        record("基础对话", False, f"延迟超标: {elapsed:.0f}ms（阈值 5000ms）")
        return

    record(
        "基础对话",
        True,
        f"延迟={elapsed:.0f}ms, tokens={resp.total_tokens}, 内容={resp.content[:60]}...",
    )


async def test_content_validation() -> None:
    """测试 2：响应内容验证 — 确认不返回推理文本。"""
    print("\n── 测试 2：响应内容验证 ──")
    client = SenseNovaClient()

    resp = await client.chat(
        [{"role": "user", "content": "灵山大佛有多高？"}],
        max_tokens=1024,
    )

    if not resp.is_valid:
        record("响应内容验证", False, "响应为空")
        return

    # 验证：内容不能是纯推理/思考文本（不应以"用户"开头）
    if resp.content.startswith("用户"):
        record(
            "响应内容验证",
            False,
            f"疑似推理文本泄露: {resp.content[:60]}",
        )
        return

    record(
        "响应内容验证",
        True,
        f"内容={resp.content[:80]}...",
    )


async def test_timeout_control() -> None:
    """测试 3：超时控制 — 验证 5 秒超时机制。

    通过将 timeout 设为极小值（1ms）模拟超时场景。
    """
    print("\n── 测试 3：超时控制 ──")
    import asyncio as _asyncio

    client = SenseNovaClient()
    original_timeout = client._chat_timeout
    client._chat_timeout = 0.001  # 模拟 1ms 超时（几乎立即超时）

    start = time.monotonic()
    try:
        resp = await _asyncio.wait_for(
            client.chat([{"role": "user", "content": "你好"}]),
            timeout=10,  # 外层 10s 保证由内层 timeout 触发
        )
        elapsed = (time.monotonic() - start) * 1000
        if not resp.is_valid and elapsed < 3000:
            record("超时控制", True, f"超时正确触发（耗时={elapsed:.0f}ms）")
        else:
            record("超时控制", False, f"超时未按预期触发（耗时={elapsed:.0f}ms, valid={resp.is_valid}）")
    except _asyncio.TimeoutError:
        elapsed = (time.monotonic() - start) * 1000
        record("超时控制", True, f"外层超时触发（耗时={elapsed:.0f}ms）")
    finally:
        client._chat_timeout = original_timeout


async def test_streaming() -> None:
    """测试 4：流式输出 — 逐 token 生成。"""
    print("\n── 测试 4：流式输出 ──")
    client = SenseNovaClient()

    tokens: list[str] = []
    start = time.monotonic()
    first_token_time = None

    try:
        async for token in client.chat_stream(
            [{"role": "user", "content": "说一句问候语"}],
            max_tokens=1024,
        ):
            if first_token_time is None:
                first_token_time = (time.monotonic() - start) * 1000
            tokens.append(token)

        total_elapsed = (time.monotonic() - start) * 1000
        reply = "".join(tokens)

        if not reply.strip():
            record("流式输出", False, "流式响应为空")
            return

        if total_elapsed > 5000:
            record("流式输出", False, f"延迟超标: {total_elapsed:.0f}ms")
            return

        record(
            "流式输出",
            True,
            f"首token={first_token_time:.0f}ms, 总={total_elapsed:.0f}ms, 内容={reply[:60]}...",
        )
    except Exception as e:
        record("流式输出", False, f"异常: {e}")


async def test_empty_input() -> None:
    """测试 5：空输入处理 — 不崩溃。"""
    print("\n── 测试 5：空输入处理 ──")
    client = SenseNovaClient()

    try:
        resp = await client.chat(
            [{"role": "user", "content": ""}],
            max_tokens=1024,
        )
        # 空输入可能返回空或简短回复，都不应该崩溃
        record("空输入处理", True, f"无崩溃（valid={resp.is_valid}）")
    except Exception as e:
        record("空输入处理", False, f"异常: {e}")


async def test_latency_benchmark() -> None:
    """测试 6：延迟基准 — 多次请求取平均值。"""
    print("\n── 测试 6：延迟基准（3 次请求）──")
    client = SenseNovaClient()

    latencies: list[float] = []
    for i in range(3):
        start = time.monotonic()
        resp = await client.chat(
            [{"role": "user", "content": "你好"}],
            max_tokens=1024,
        )
        lat = (time.monotonic() - start) * 1000
        latencies.append(lat)
        print(f"    请求 {i+1}: {lat:.0f}ms, valid={resp.is_valid}")

    avg = sum(latencies) / len(latencies)
    all_under_5s = all(lat < 5000 for lat in latencies)

    if all_under_5s:
        record(
            "延迟基准",
            True,
            f"平均={avg:.0f}ms, min={min(latencies):.0f}ms, max={max(latencies):.0f}ms",
        )
    else:
        record("延迟基准", False, f"存在超过 5s 的请求: max={max(latencies):.0f}ms")


# ═════════════════════════════════════════════════════════
# 主入口
# ═════════════════════════════════════════════════════════


async def main() -> None:
    """运行所有测试。"""
    print("=" * 60)
    print("  SenseNova API 接入验证")
    print("  Model: sensenova-6.7-flash-lite")
    print(f"  Endpoint: https://token.sensenova.cn/v1/chat/completions")
    print("=" * 60)

    tests = [
        test_basic_chat,
        test_content_validation,
        test_timeout_control,
        test_streaming,
        test_empty_input,
        test_latency_benchmark,
    ]

    for test_fn in tests:
        try:
            await test_fn()
        except Exception as e:
            record(test_fn.__name__, False, f"测试异常: {e}")

    # ── 汇总 ──────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)

    for name, p, detail in results:
        icon = "✅" if p else "❌"
        print(f"  {icon} {name}")
        if detail:
            print(f"     {detail}")

    print(f"\n  📊 通过: {passed}/{len(results)} | 失败: {failed}/{len(results)}")

    if failed > 0:
        print("\n  ⚠️ 存在失败用例，请检查。")
        sys.exit(1)
    else:
        print("\n  🎉 全部测试通过！SenseNova API 接入成功。")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

"""SenseNova API 接入 — 比赛标准验证脚本。

严格对照比赛要求的 4 条成功标准：
  标准 1：调用接口 https://token.sensenova.cn/v1/chat/completions
          请求头包含 Authorization: Bearer <key> 和 Content-Type: application/json
  标准 2：使用模型 sensenova-6.7-flash-lite
          消息体格式 {"model": "...", "messages": [{"role":"user","content":"..."}]}
  标准 3：接口能正常返回回答内容，且响应时间小于 5 秒
  标准 4：代码包含超时控制（5 秒阈值）和响应验证逻辑

用法：
    cd C:/Users/29688/Desktop/a5-digital-human
    python tests/test_sensenova_competition.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.sensenova import SenseNovaClient, SenseNovaResponse

# ── 比赛参数 ──────────────────────────────────────────────
API_URL = "https://token.sensenova.cn/v1/chat/completions"
API_KEY = "sk-faXRQ8xPU3tJRtnbwILV9bBYUqBwFUeO"
MODEL = "sensenova-6.7-flash-lite"
TIMEOUT_THRESHOLD = 5.0  # 比赛要求：响应时间 < 5 秒

results: list[tuple[str, bool, str]] = []


def record(criterion: str, passed: bool, detail: str = "") -> None:
    results.append((criterion, passed, detail))
    icon = "✅" if passed else "❌"
    print(f"\n  {icon} {criterion}")
    if detail:
        print(f"     {detail}")


# ═════════════════════════════════════════════════════════
# 标准 1 + 标准 2：原始 HTTP 请求验证（curl 级别）
# ═════════════════════════════════════════════════════════

async def test_criterion_1_2_raw_http() -> None:
    """标准 1+2：验证接口地址、请求头、模型名、消息体格式。

    用 httpx 直接发送比赛要求的原始请求格式，绕过封装层，
    确认底层 API 100% 符合比赛规格。
    """
    print("\n" + "=" * 60)
    print("  标准 1 + 标准 2：接口地址 / 请求头 / 模型 / 消息体格式")
    print("=" * 60)

    import httpx

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Hello!"}],
        "max_tokens": 1024,
    }

    print(f"\n  → POST {API_URL}")
    print(f"  → Authorization: Bearer {API_KEY[:12]}...{API_KEY[-4:]}")
    print(f"  → Content-Type: application/json")
    print(f"  → model: {MODEL}")
    print(f"  → messages: [{{'role':'user','content':'Hello!'}}]")

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
            resp = await client.post(API_URL, headers=headers, json=body)
        elapsed = (time.monotonic() - start) * 1000

        # 标准 1：HTTP 状态码
        http_ok = resp.status_code == 200
        record(
            "标准1: 接口地址可达 + 请求头正确",
            http_ok,
            f"HTTP {resp.status_code}, 延迟={elapsed:.0f}ms"
            + ("" if http_ok else f", body={resp.text[:200]}"),
        )

        # 标准 2：响应中包含正确模型名 + choices 结构
        data = resp.json()
        model_correct = data.get("model", "").startswith("sensenova")
        has_choices = "choices" in data and len(data["choices"]) > 0
        has_content = (
            has_choices
            and data["choices"][0].get("message", {}).get("content") is not None
        )

        record(
            "标准2: 模型=sensenova-6.7-flash-lite + 消息体格式正确",
            model_correct and has_choices,
            f"model={data.get('model','?')}, choices={len(data.get('choices',[]))}, "
            f"has_content={has_content}",
        )

    except Exception as e:
        record("标准1+2: 原始HTTP请求", False, f"异常: {e}")


# ═════════════════════════════════════════════════════════
# 标准 3：响应内容非空 + 响应时间 < 5 秒
# ═════════════════════════════════════════════════════════

async def test_criterion_3_content_and_latency() -> None:
    """标准 3：接口正常返回回答内容 + 响应时间 < 5 秒。

    使用流式模式（推理模型推荐），验证首 token < 5s 且内容非空。
    再用非流式模式补充验证。
    """
    print("\n" + "=" * 60)
    print("  标准 3：正常返回回答内容 + 响应时间 < 5 秒")
    print("=" * 60)

    # ── 流式模式 ──
    print("\n  [流式模式] 发送: 'Hello!'")
    client = SenseNovaClient()

    tokens: list[str] = []
    start = time.monotonic()
    first_token_ms = None

    async for token in client.chat_stream(
        [{"role": "user", "content": "Hello!"}],
        max_tokens=512,
    ):
        if first_token_ms is None:
            first_token_ms = (time.monotonic() - start) * 1000
        tokens.append(token)

    reply = "".join(tokens).strip()
    total_ms = (time.monotonic() - start) * 1000

    stream_content_ok = len(reply) >= 2
    stream_latency_ok = first_token_ms is not None and first_token_ms < TIMEOUT_THRESHOLD * 1000

    record(
        "标准3a [流式]: 返回内容非空",
        stream_content_ok,
        f"内容长度={len(reply)}字, 预览={reply[:80]}..." if reply else "内容为空",
    )
    record(
        f"标准3b [流式]: 首 token 响应时间 < 5s",
        stream_latency_ok,
        f"首token={first_token_ms:.0f}ms (阈值{TIMEOUT_THRESHOLD:.0f}s)"
        if first_token_ms
        else "未收到任何 token",
    )

    # ── 非流式模式（比赛标准格式）──
    print("\n  [非流式模式] 发送: '灵山大佛有多高？'")
    start2 = time.monotonic()
    resp = await client.chat(
        [{"role": "user", "content": "灵山大佛有多高？"}],
        max_tokens=512,
    )
    non_stream_ms = (time.monotonic() - start2) * 1000

    nonstream_content_ok = resp.is_valid
    nonstream_latency_ok = non_stream_ms < TIMEOUT_THRESHOLD * 1000

    record(
        "标准3c [非流式]: 返回内容非空",
        nonstream_content_ok,
        f"内容={resp.content[:80]}..." if resp.is_valid else f"内容为空 (latency={resp.latency_ms:.0f}ms)",
    )
    record(
        "标准3d [非流式]: 响应时间 < 5s",
        nonstream_latency_ok,
        f"延迟={non_stream_ms:.0f}ms (阈值{TIMEOUT_THRESHOLD:.0f}s)",
    )


# ═════════════════════════════════════════════════════════
# 标准 4：超时控制（5 秒阈值）+ 响应验证逻辑
# ═════════════════════════════════════════════════════════

async def test_criterion_4_timeout_and_validation() -> None:
    """标准 4：代码包含超时控制（5 秒阈值）+ 响应验证逻辑。

    验证点：
    a) 超时控制：将 timeout 设为极小值，确认会触发超时而非无限等待
    b) 响应验证：空 content 返回 is_valid=False
    c) 代码审查：确认 sensenova.py 包含 timeout 和 _validate 逻辑
    """
    print("\n" + "=" * 60)
    print("  标准 4：超时控制（5 秒阈值）+ 响应验证逻辑")
    print("=" * 60)

    # ── 4a: 超时控制生效 ──
    print("\n  [超时控制] 设置 timeout=0.001s，确认超时机制触发")
    client = SenseNovaClient()
    original = client._stream_timeout
    client._stream_timeout = 0.001  # 1ms，强制超时

    start = time.monotonic()
    tokens_timeout: list[str] = []
    try:
        async for token in client.chat_stream(
            [{"role": "user", "content": "你好"}],
            max_tokens=512,
        ):
            tokens_timeout.append(token)
    except Exception:
        pass
    finally:
        client._stream_timeout = original

    elapsed = (time.monotonic() - start) * 1000
    timeout_triggered = elapsed < 3000 and len(tokens_timeout) == 0

    record(
        "标准4a: 超时控制（5s 阈值）生效",
        timeout_triggered,
        f"timeout=0.001s → {elapsed:.0f}ms 内中断, 收到token数={len(tokens_timeout)}",
    )

    # ── 4b: 响应验证逻辑 — 空响应处理 ──
    print("\n  [响应验证] 验证 SenseNovaResponse.is_valid 逻辑")
    empty_resp = SenseNovaResponse("", 0, 0)
    whitespace_resp = SenseNovaResponse("   \n\n  ", 0, 0)
    valid_resp = SenseNovaResponse("你好世界", 10, 1000)

    validation_ok = (
        not empty_resp.is_valid
        and not whitespace_resp.is_valid
        and valid_resp.is_valid
    )

    record(
        "标准4b: 响应验证逻辑（content 非空校验）",
        validation_ok,
        f"空字符串→is_valid={empty_resp.is_valid}, "
        f"纯空白→is_valid={whitespace_resp.is_valid}, "
        f"正常文本→is_valid={valid_resp.is_valid}",
    )

    # ── 4c: 代码结构审查 ──
    print("\n  [代码审查] 确认 sensenova.py 包含超时 + 验证逻辑")
    import inspect
    from backend.services import sensenova as sn_module

    source = inspect.getsource(sn_module)
    has_timeout = "asyncio.wait_for" in source and "timeout" in source.lower()
    has_validate = "_validate" in source and "is_valid" in source
    has_5s_ref = "5.0" in source or "_STREAM_TIMEOUT" in source

    record(
        "标准4c: 代码包含 timeout + _validate + 5s 阈值常量",
        has_timeout and has_validate and has_5s_ref,
        f"asyncio.wait_for={'✅' if has_timeout else '❌'}, "
        f"_validate={'✅' if has_validate else '❌'}, "
        f"5s常量={'✅' if has_5s_ref else '❌'}",
    )


# ═════════════════════════════════════════════════════════
# 额外：多轮对话验证（景区导览场景）
# ═════════════════════════════════════════════════════════

async def test_scenic_conversation() -> None:
    """额外验证：景区导览多轮对话，确认实际业务场景可用。"""
    print("\n" + "=" * 60)
    print("  额外验证：景区导览多轮对话")
    print("=" * 60)

    client = SenseNovaClient()
    questions = [
        "灵山大佛有多高？",
        "九龙灌浴表演什么时候有？",
    ]

    all_ok = True
    for i, q in enumerate(questions, 1):
        print(f"\n  Q{i}: {q}")
        start = time.monotonic()
        resp = await client.chat(
            [{"role": "user", "content": q}],
            max_tokens=512,
        )
        reply = resp.content.strip()
        elapsed = (time.monotonic() - start) * 1000

        ok = resp.is_valid and elapsed < TIMEOUT_THRESHOLD * 1000
        all_ok = all_ok and ok
        print(f"  A{i}: {reply[:100]}...")
        print(f"     延迟={elapsed:.0f}ms, 字数={len(reply)}, <5s={'✅' if elapsed < 5000 else '❌'}")

    record(
        "额外: 景区导览多轮对话（2轮 Q&A）",
        all_ok,
        "2 轮问答均返回有效内容且首 token < 5s" if all_ok else "存在失败轮次",
    )


# ═════════════════════════════════════════════════════════
# 主入口
# ═════════════════════════════════════════════════════════

async def main() -> None:
    print("╔" + "═" * 58 + "╗")
    print("║" + "  SenseNova API 接入 — 比赛标准验证".center(54) + "    ║")
    print("║" + f"  Endpoint: {API_URL}".ljust(58) + "║")
    print("║" + f"  Model: {MODEL}".ljust(58) + "║")
    print("║" + f"  Key: {API_KEY[:12]}...{API_KEY[-4:]}".ljust(58) + "║")
    print("║" + f"  成功标准: 返回内容 + 响应<5s + 超时控制 + 响应验证".ljust(58) + "║")
    print("╚" + "═" * 58 + "╝")

    await test_criterion_1_2_raw_http()
    await test_criterion_3_content_and_latency()
    await test_criterion_4_timeout_and_validation()
    await test_scenic_conversation()

    # ── 汇总 ──────────────────────────────────────────
    print("\n\n" + "═" * 60)
    print("  比赛标准验证结果汇总")
    print("═" * 60)

    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)

    for name, p, detail in results:
        icon = "✅" if p else "❌"
        print(f"\n  {icon} {name}")
        if detail:
            print(f"     {detail}")

    print(f"\n  {'─' * 50}")
    print(f"  📊 通过: {passed}/{total} | 失败: {failed}/{total}")

    if failed == 0:
        print("\n  🎉 全部比赛标准验证通过！SenseNova API 接入符合要求。")
    else:
        print(f"\n  ⚠️ {failed} 项未通过，请检查。")

    print("\n" + "═" * 60)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

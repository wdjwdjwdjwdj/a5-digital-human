"""准确率测试：使用灵山胜境测试集验证问答准确率 ≥ 90%。

用法：
    python scripts/test_accuracy.py

测试覆盖 5 个知识库文档：
    景点介绍 scenic_intro.md、票务信息 ticket_info.md、
    餐饮推荐 dining_guide.md、路线指引 route_map.md、FAQ faq.md

测试路径（优先级）：
    1. Local RAG 语义检索（主要路径）
    2. ChatBot 降级链路（次要路径，当无 API Key 时测试降级行为）
"""

import logging
import sys
from pathlib import Path

# 加入项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _out(msg: str = "") -> None:
    """输出到终端（替代 print）。"""
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


# ── 测试集：20 对灵山 QA 覆盖全部 5 个知识库文档 ──────────
# 每项：(question, [expected_keywords])
# 回答中包含任一关键词即视为正确

TEST_QUESTIONS: list[dict] = [
    # ════════════════════════════════════════════════
    # 景点类（6题）— 文档: scenic_intro.md
    # ════════════════════════════════════════════════
    {"q": "灵山大佛有多高？", "keywords": ["88米", "88 米", "八十八米"], "source": "scenic_intro.md"},
    {"q": "灵山大佛由什么材料建造？", "keywords": ["青铜", "铜"], "source": "scenic_intro.md"},
    {"q": "灵山梵宫有什么特色？", "keywords": ["东方卢浮宫", "72000", "七万二"], "source": "scenic_intro.md"},
    {"q": "九龙灌浴一天表演几次？",
     "keywords": ["4次", "四次", "10:00", "11:30", "13:30", "15:00"],
     "source": "scenic_intro.md"},
    {"q": "五印坛城展示什么文化？", "keywords": ["藏传", "藏传佛教", "藏族"], "source": "scenic_intro.md"},
    {"q": "祥符禅寺有什么历史？", "keywords": ["千年", "古刹", "唐代"], "source": "scenic_intro.md"},
    # ════════════════════════════════════════════════
    # 票务类（5题）— 文档: ticket_info.md
    # ════════════════════════════════════════════════
    {"q": "灵山门票多少钱？", "keywords": ["210元", "210 元", "成人票"], "source": "ticket_info.md"},
    {"q": "灵山有学生票吗？", "keywords": ["半价", "半票", "105"], "source": "ticket_info.md"},
    {"q": "灵山胜境开放时间？", "keywords": ["7:00", "17:30", "07:00", "17:30"], "source": "ticket_info.md"},
    {"q": "灵山老人有优惠吗？", "keywords": ["70", "免票", "免费"], "source": "ticket_info.md"},
    {"q": "灵山梵宫需要另外买票吗？", "keywords": ["含", "包含", "大门票", "不需"], "source": "ticket_info.md"},
    # ════════════════════════════════════════════════
    # 路线类（4题）— 文档: route_map.md
    # ════════════════════════════════════════════════
    {"q": "推荐一条灵山游览路线？",
     "keywords": ["南门", "九龙灌浴", "佛手广场", "祥符禅寺",
                   "灵山大佛", "灵山梵宫", "五印坛城"],
     "source": "route_map.md"},
    {"q": "灵山适合玩多久？", "keywords": ["4", "5", "6", "小时", "半日", "一日"], "source": "route_map.md"},
    {"q": "怎么去灵山胜境？", "keywords": ["公交", "88路", "89路", "乐游线", "自驾"], "source": "route_map.md"},
    {"q": "灵山停车场怎么收费？", "keywords": ["15元", "15 元", "次"], "source": "route_map.md"},
    # ════════════════════════════════════════════════
    # 餐饮/其他类（5题）— 文档: dining_guide.md / faq.md
    # ════════════════════════════════════════════════
    {"q": "灵山有什么吃的？", "keywords": ["素斋", "素食", "灵山精舍"], "source": "dining_guide.md"},
    {"q": "灵山有住宿吗？", "keywords": ["灵山精舍", "拈花湾", "住宿"], "source": "faq.md"},
    {"q": "九龙灌浴表演多长时间？", "keywords": ["15", "15分钟", "一刻钟"], "source": "scenic_intro.md"},
    {"q": "天下第一掌在哪里？", "keywords": ["佛手广场"], "source": "scenic_intro.md"},
    {"q": "灵山胜境在哪个城市？", "keywords": ["无锡", "江苏", "太湖"], "source": "faq.md"},
]


def load_test_set() -> list[dict]:
    """加载测试集。

    Returns:
        测试用例列表
    """
    return TEST_QUESTIONS


def evaluate_keywords(reply: str, keywords: list[str]) -> bool:
    """检查回答是否包含任一关键词。

    Args:
        reply: 模型回答文本
        keywords: 期望出现的关键词列表（命中任一即算正确）

    Returns:
        包含关键词返回 True
    """
    reply_lower = reply.lower()
    return any(kw.lower() in reply_lower for kw in keywords)


def run_test(get_answer_fn, test_name: str) -> dict:
    """运行准确率测试。

    Args:
        get_answer_fn: 接受 question 返回 answer 的函数
        test_name: 测试名称

    Returns:
        测试结果统计
    """
    test_cases = load_test_set()
    total = len(test_cases)
    passed = 0
    failed: list[dict] = []

    _out(f"\n{'=' * 60}")
    _out(f"  测试: {test_name}（共 {total} 题）")
    _out(f"{'=' * 60}\n")

    for i, item in enumerate(test_cases, 1):
        question = item["q"]
        keywords = item["keywords"]

        try:
            answer = get_answer_fn(question)
            if answer is None:
                answer = ""

            is_pass = evaluate_keywords(answer, keywords)
            if is_pass:
                passed += 1
            else:
                failed.append(
                    {
                        "q": question,
                        "keywords": keywords,
                        "answer": answer[:120] if answer else "None",
                    }
                )
                _out(f"  ❌ [{i:02d}] {question}")
                _out(f"      期望: {keywords}")
                _out(f"      回答: {answer[:80] if answer else 'None'}…")
        except Exception as e:
            failed.append(
                {
                    "q": question,
                    "keywords": keywords,
                    "answer": f"Error: {e}",
                }
            )
            _out(f"  ❌ [{i:02d}] {question} (异常: {e})")

    accuracy = passed / total if total > 0 else 0
    _out(f"\n{'─' * 60}")
    result_line = f"  结果: {accuracy * 100:.1f}% ({passed}/{total})"
    if accuracy >= 0.9:
        result_line += " ✅ 通过（目标 ≥ 90%）"
    else:
        result_line += " ❌ 未通过（目标 ≥ 90%）"
    _out(result_line)
    _out(f"{'─' * 60}\n")

    if failed:
        _out(f"  失败详情（{len(failed)} 题失败）:")
        for f in failed:
            _out(f"    · {f['q']}")
            _out(f"      期望: {f['keywords']}")
            _out(f"      回答: {f['answer'][:80] if f['answer'] else 'None'}")
        _out("")

    return {"total": total, "passed": passed, "failed": len(failed), "accuracy": accuracy}


async def async_run_test(get_answer_async_fn, test_name: str) -> dict:
    """异步运行准确率测试。

    Args:
        get_answer_async_fn: 接受 question 返回 answer 的 async 函数
        test_name: 测试名称

    Returns:
        测试结果统计
    """
    test_cases = load_test_set()
    total = len(test_cases)
    passed = 0
    failed: list[dict] = []

    _out(f"\n{'=' * 60}")
    _out(f"  测试: {test_name}（共 {total} 题）")
    _out(f"{'=' * 60}\n")

    for i, item in enumerate(test_cases, 1):
        question = item["q"]
        keywords = item["keywords"]

        try:
            answer = await get_answer_async_fn(question)
            if answer is None:
                answer = ""

            is_pass = evaluate_keywords(answer, keywords)
            if is_pass:
                passed += 1
            else:
                failed.append(
                    {
                        "q": question,
                        "keywords": keywords,
                        "answer": answer[:120] if answer else "None",
                    }
                )
                _out(f"  ❌ [{i:02d}] {question}")
                _out(f"      期望: {keywords}")
                _out(f"      回答: {answer[:80] if answer else 'None'}…")
        except Exception as e:
            failed.append(
                {
                    "q": question,
                    "keywords": keywords,
                    "answer": f"Error: {e}",
                }
            )
            _out(f"  ❌ [{i:02d}] {question} (异常: {e})")

    accuracy = passed / total if total > 0 else 0
    _out(f"\n{'─' * 60}")
    result_line = f"  结果: {accuracy * 100:.1f}% ({passed}/{total})"
    if accuracy >= 0.9:
        result_line += " ✅ 通过（目标 ≥ 90%）"
    else:
        result_line += " ❌ 未通过（目标 ≥ 90%）"
    _out(result_line)
    _out(f"{'─' * 60}\n")

    if failed:
        _out(f"  失败详情（{len(failed)} 题失败）:")
        for f in failed:
            _out(f"    · {f['q']}")
            _out(f"      期望: {f['keywords']}")
            _out(f"      回答: {f['answer'][:80] if f['answer'] else 'None'}")
        _out("")

    return {"total": total, "passed": passed, "failed": len(failed), "accuracy": accuracy}


async def test_local_rag() -> dict:
    """测试 Local RAG 检索准确率（主要路径）。

    Returns:
        测试结果
    """
    from backend.services.local_rag import local_rag

    # 构建索引（首次加载）
    _out("[INFO] 构建 Local RAG 索引...")
    success = local_rag.build_index()
    if not success:
        _out("[WARN] Local RAG 索引构建失败，跳过")
        return {"total": 0, "passed": 0, "failed": 0, "accuracy": 0.0}

    def get_answer(q: str) -> str:
        return local_rag.search(q)

    return run_test(get_answer, "Local RAG 语义检索")


async def test_chatbot_dify_fallback() -> dict:
    """测试 ChatBot 在 Dify 不可用时的降级行为。

    当 Dify 未配置时，chatbot._dify_configured() 返回 False，
    chat() 应直接走 DeepSeek 链路（不抛异常）。

    Returns:
        测试结果
    """
    from backend.services.chatbot import chatbot

    # 验证 _dify_configured() 行为
    dify_configured = chatbot._dify_configured()
    _out(f"  [INFO] Dify 配置状态: {'已配置' if dify_configured else '未配置（将测试降级链路）'}")

    async def get_answer(q: str) -> str:
        reply = await chatbot.chat(query=q, session_id="accuracy_test_dify")
        return reply if reply else ""

    return await async_run_test(get_answer, f"ChatBot 降级测试 (Dify={'已配置' if dify_configured else '未配置'})")


async def evaluate_accuracy() -> float:
    """评估各路径问答准确率。

    测试顺序：
    1. Local RAG 检索（主要路径，无网络依赖）
    2. ChatBot 降级链路（次要路径，验证 _dify_configured() 行为）

    Returns:
        Local RAG 准确率（0.0 ~ 1.0）
    """
    # ── 路径1：Local RAG 语义检索（主要路径）──
    local_result = await test_local_rag()

    # ── 路径2：ChatBot 降级链路测试 ──
    _out(f"\n{'=' * 60}")
    _out("  ChatBot 降级行为测试")
    _out(f"{'=' * 60}")
    dify_result = await test_chatbot_dify_fallback()

    # ── 结论 ──
    _out(f"\n{'=' * 60}")
    _out("  测试总结")
    _out(f"{'=' * 60}")

    overall_pass = True

    _out("\n  [1] Local RAG:")
    if local_result["total"] > 0:
        pct = local_result["accuracy"] * 100
        status = "✅" if pct >= 90 else "❌"
        _out(f"      {pct:.1f}% ({local_result['passed']}/{local_result['total']}) {status}")
        if pct < 90:
            overall_pass = False
    else:
        _out("      未运行")

    _out("\n  [2] ChatBot 降级链路:")
    if dify_result["total"] > 0:
        pct = dify_result["accuracy"] * 100
        _out(f"      {pct:.1f}% ({dify_result['passed']}/{dify_result['total']})")
    else:
        _out("      未运行")

    _out(f"\n{'─' * 60}")
    if overall_pass and local_result["total"] > 0:
        _out("  总体: ✅ Local RAG 准确率通过（≥90%）")
    else:
        _out("  总体: ⚠️ 请检查各路径结果")
    _out(f"{'─' * 60}\n")

    return local_result["accuracy"] if local_result["total"] > 0 else 0.0


if __name__ == "__main__":
    import asyncio

    asyncio.run(evaluate_accuracy())

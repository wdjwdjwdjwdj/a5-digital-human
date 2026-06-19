"""准确率测试：使用西湖景区测试集验证问答准确率 ≥ 90%。

用法：
    python scripts/test_accuracy.py

测试覆盖 5 个知识库文档：
    景点介绍 scenic_intro.md、票务信息 ticket_info.md、
    餐饮推荐 dining_guide.md、路线指引 route_map.md、FAQ faq.md

测试路径（优先级）：
    1. Local RAG 语义检索（主要路径）
    2. Dify RAG / DeepSeek / 通义千问 LLM（次要路径，当无 API Key 时测试降级行为）
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


# ── 测试集：50 题覆盖全部 5 个知识库文档 ──────────────
# 每项：(question, [expected_keywords])
# 回答中包含任一关键词即视为正确

TEST_QUESTIONS: list[dict] = [
    # ════════════════════════════════════════════════
    # 景点类（12题）— 文档: scenic_intro.md
    # ════════════════════════════════════════════════
    {"q": "西湖十景包括哪些？", "keywords": ["断桥残雪", "苏堤春晓", "雷峰夕照"], "source": "scenic_intro.md"},
    {"q": "断桥残雪为什么叫断桥？", "keywords": ["雪", "桥面", "似断非断"], "source": "scenic_intro.md"},
    {"q": "苏堤是谁建的？", "keywords": ["苏轼", "苏东坡"], "source": "scenic_intro.md"},
    {"q": "雷峰塔跟什么民间传说有关？", "keywords": ["白蛇传", "白素贞", "法海"], "source": "scenic_intro.md"},
    {"q": "三潭印月有几个石塔？", "keywords": ["三座", "三个", "3座"], "source": "scenic_intro.md"},
    {"q": "花港观鱼在西湖哪个位置？", "keywords": ["苏堤", "南段"], "source": "scenic_intro.md"},
    {"q": "曲院风荷与什么有关？", "keywords": ["荷花", "酿酒", "宫廷"], "source": "scenic_intro.md"},
    {"q": "南屏晚钟是哪里发出的钟声？", "keywords": ["净慈寺", "南屏山"], "source": "scenic_intro.md"},
    {"q": "西湖哪一年列入世界遗产？", "keywords": ["2011", "2011年"], "source": "scenic_intro.md"},
    {"q": "孤山有什么景点？", "keywords": ["西泠印社", "平湖秋月", "楼外楼"], "source": "scenic_intro.md"},
    {"q": "白堤是谁修建的？", "keywords": ["白居易"], "source": "scenic_intro.md"},
    {"q": "苏堤有多少座桥？", "keywords": ["六", "6", "六桥"], "source": "scenic_intro.md"},
    # ════════════════════════════════════════════════
    # 票务类（10题）— 文档: ticket_info.md
    # ════════════════════════════════════════════════
    {"q": "西湖大门票多少钱？", "keywords": ["免费", "不设大门票", "免费开放"], "source": "ticket_info.md"},
    {"q": "雷峰塔门票多少钱？", "keywords": ["40", "40元"], "source": "ticket_info.md"},
    {"q": "灵隐寺门票多少钱？", "keywords": ["75", "75元"], "source": "ticket_info.md"},
    {"q": "三潭印月船票多少钱？", "keywords": ["55", "55元"], "source": "ticket_info.md"},
    {"q": "岳王庙门票多少钱？", "keywords": ["25", "25元"], "source": "ticket_info.md"},
    {"q": "老人去西湖有什么优惠？", "keywords": ["70", "免票", "半票"], "source": "ticket_info.md"},
    {"q": "学生去西湖收费景点有优惠吗？", "keywords": ["半票", "半价", "学生证"], "source": "ticket_info.md"},
    {"q": "雷峰塔开放时间？", "keywords": ["08:00", "17:30", "18:30"], "source": "ticket_info.md"},
    {"q": "西湖哪些景点需要买票？", "keywords": ["雷峰塔", "岳王庙", "灵隐寺"], "source": "ticket_info.md"},
    {"q": "西湖 WIFI 的 SSID 是什么？", "keywords": ["i-Xihu", "xihu"], "source": "ticket_info.md"},
    # ════════════════════════════════════════════════
    # 交通/路线类（8题）— 文档: route_map.md
    # ════════════════════════════════════════════════
    {"q": "去西湖坐地铁几号线？", "keywords": ["1号线", "1号"], "source": "route_map.md"},
    {"q": "西湖可以骑自行车吗？", "keywords": ["可以", "共享单车", "骑行"], "source": "route_map.md"},
    {"q": "西湖有观光巴士吗？", "keywords": ["环湖", "观光巴士", "招手即停"], "source": "route_map.md"},
    {"q": "从杭州东站怎么去西湖？", "keywords": ["地铁", "1号线"], "source": "route_map.md"},
    {"q": "骑行环湖需要多久？", "keywords": ["1.5", "1.5小时"], "source": "route_map.md"},
    {"q": "西湖半日游推荐路线？", "keywords": ["断桥", "苏堤", "雷峰塔"], "source": "route_map.md"},
    {"q": "西湖一日游需要多长时间？", "keywords": ["6", "8", "小时"], "source": "route_map.md"},
    {"q": "西湖音乐喷泉几点开始？", "keywords": ["19:00", "20:00"], "source": "route_map.md"},
    # ════════════════════════════════════════════════
    # 餐饮类（8题）— 文档: dining_guide.md
    # ════════════════════════════════════════════════
    {"q": "西湖附近有什么杭帮菜推荐？", "keywords": ["楼外楼", "西湖醋鱼", "东坡肉"], "source": "dining_guide.md"},
    {"q": "楼外楼的特色菜是什么？", "keywords": ["西湖醋鱼", "东坡肉", "龙井虾仁"], "source": "dining_guide.md"},
    {"q": "知味观有什么推荐小吃？", "keywords": ["片儿川", "猫耳朵", "小笼包"], "source": "dining_guide.md"},
    {"q": "西湖龙井哪里买正宗？", "keywords": ["龙井村", "梅家坞", "湖畔居"], "source": "dining_guide.md"},
    {"q": "西湖有什么特色小吃？", "keywords": ["定胜糕", "葱包烩", "荷花酥"], "source": "dining_guide.md"},
    {"q": "杭州有什么素食推荐？", "keywords": ["净慈寺", "素斋"], "source": "dining_guide.md"},
    {"q": "外婆家有什么推荐菜？", "keywords": ["茶香鸡", "糖醋里脊"], "source": "dining_guide.md"},
    {"q": "河坊街有什么特色小吃？", "keywords": ["定胜糕", "葱包烩", "荷花酥"], "source": "dining_guide.md"},
    # ════════════════════════════════════════════════
    # 游览类（6题）— 文档: scenic_intro.md / route_map.md
    # ════════════════════════════════════════════════
    {"q": "哪个季节去西湖最美？", "keywords": ["四季", "各有特色"], "source": "route_map.md"},
    {"q": "西湖适合带孩子去吗？", "keywords": ["适合", "花港观鱼", "亲子"], "source": "faq.md"},
    {"q": "西湖用轮椅方便吗？", "keywords": ["方便", "平坦", "通行"], "source": "faq.md"},
    {"q": "西湖文化传说有哪些？", "keywords": ["白蛇传", "苏东坡", "白居易"], "source": "faq.md"},
    {"q": "西湖周边有什么博物馆？", "keywords": ["西湖博物馆", "丝绸博物馆"], "source": "scenic_intro.md"},
    {"q": "西湖有寄存行李的地方吗？", "keywords": ["寄存", "游客中心"], "source": "faq.md"},
    # ════════════════════════════════════════════════
    # 其他/扩展类（6题）— 文档: 混合来源
    # ════════════════════════════════════════════════
    {"q": "西湖有多少平方公里？", "keywords": ["6.39", "6.39平方千米"], "source": "scenic_intro.md"},
    {"q": "西湖三面环山对吗？", "keywords": ["对", "三面", "环山"], "source": "scenic_intro.md"},
    {"q": "雷峰塔有多高？", "keywords": ["71", "71米"], "source": "scenic_intro.md"},
    {"q": "西湖最适合穿什么鞋游览？", "keywords": ["舒适", "步行鞋", "运动鞋"], "source": "route_map.md"},
    {"q": "杭州西湖博物馆在哪里？", "keywords": ["南山路", "钱王祠"], "source": "scenic_intro.md"},
    {"q": "西湖有讲解服务吗？", "keywords": ["讲解", "导游"], "source": "faq.md"},
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

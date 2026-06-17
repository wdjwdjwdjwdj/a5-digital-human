"""准确率测试：使用西湖景区测试集验证问答准确率 ≥ 90%。

用法：
    python scripts/test_accuracy.py

覆盖 5 个知识库文档：
    景点介绍、票务信息、餐饮推荐、路线指引、FAQ
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


# ── 测试集：25 题覆盖全部 5 个知识库文档 ──────────────
# 每项：(question, [expected_keywords])
# 答中包含任一关键词即视为正确

_TEST_SET: list[tuple[str, list[str]]] = [
    # ── 景点介绍 (scenic_intro.md) ──
    ("西湖的面积是多少？", ["6.39", "6.39平方千米"]),
    ("西湖三面环山，面积约多少？", ["6.39", "平方千米"]),
    ("断桥残雪的名字是怎么来的？", ["似断非断", "雪"]),
    ("苏堤是谁修建的？", ["苏轼", "苏东坡"]),
    ("雷峰塔建于哪一年？", ["975", "公元975"]),
    ("雷峰塔高多少米？", ["71米", "71"]),
    ("三潭印月岛上有哪些建筑？", ["开网亭", "闲放台", "先贤祠"]),
    # ── 票务信息 (ticket_info.md) ──
    ("西湖景区要门票吗？", ["免费", "不设大门票", "免费开放"]),
    ("雷峰塔门票多少钱？", ["40", "40元"]),
    ("三潭印月的游船票多少钱？", ["55", "55元", "含船票"]),
    ("灵隐寺门票多少钱？", ["75", "飞来峰45", "灵隐寺30"]),
    ("70岁以上老人去西湖收费景点有什么优惠？", ["免票", "70周岁"]),
    ("学生去西湖有什么优惠？", ["半票", "学生证"]),
    # ── 餐饮推荐 (dining_guide.md) ──
    ("楼外楼有什么特色菜？", ["西湖醋鱼", "东坡肉", "龙井虾仁"]),
    ("知味观的人均消费多少？", ["60", "100"]),
    ("外婆家有什么推荐菜？", ["茶香鸡", "糖醋里脊"]),
    ("西湖有哪些特色小吃？", ["定胜糕", "葱包烩", "荷花酥", "西湖藕粉"]),
    # ── 路线指引 (route_map.md) ──
    ("西湖半日游的经典路线是什么？", ["断桥残雪", "苏堤春晓", "花港观鱼", "雷峰塔"]),
    ("坐几号地铁可以到西湖？", ["地铁1号线", "1号线"]),
    ("西湖哪个季节最美？", ["春季", "夏季", "秋季", "冬季"]),
    ("西湖音乐喷泉几点开始？", ["19:00", "20:00"]),
    # ── FAQ (faq.md) ──
    ("西湖适合带孩子去吗？", ["非常适合", "花港观鱼", "亲子"]),
    ("西湖龙井茶在哪里买正宗？", ["龙井村", "梅家坞", "湖畔居"]),
    ("西湖有什么文化传说？", ["白蛇传", "许仙", "白素贞", "断桥"]),
    ("西湖能用轮椅或婴儿车吗？", ["可以", "通行", "平坦"]),
]


def load_test_set() -> list[tuple[str, list[str]]]:
    """加载测试集。

    Returns:
        测试用例列表，每项为 (question, expected_keywords)
    """
    return _TEST_SET


def evaluate_keywords(reply: str, keywords: list[str]) -> bool:
    """检查回答是否包含任一关键词。

    Args:
        reply: LLM 回答文本
        keywords: 期望出现的关键词列表（命中任一即算正确）

    Returns:
        包含关键词返回 True
    """
    reply_lower = reply.lower()
    return any(kw.lower() in reply_lower for kw in keywords)


async def evaluate_accuracy() -> float:
    """评估问答准确率。

    Returns:
        准确率（0.0 ~ 1.0）
    """
    from backend.services.chatbot import chatbot

    test_cases = load_test_set()
    if not test_cases:
        logger.warning("未加载测试集，返回 0.0")
        return 0.0

    total = len(test_cases)
    correct = 0
    failed: list[tuple[str, list[str], str]] = []

    _out(f"\n{'=' * 60}")
    _out(f"  西湖景区知识问答准确率测试（共 {total} 题）")
    _out(f"{'=' * 60}\n")

    for i, (question, keywords) in enumerate(test_cases, 1):
        reply = await chatbot.chat(query=question)
        if reply and evaluate_keywords(reply, keywords):
            correct += 1
            status = "✅"
        else:
            failed.append((question, keywords, reply or "None"))
            status = "❌"

        # 只输出错误题目的详情
        if status == "❌":
            _out(f"  {status} [{i:02d}] {question}")
            _out(f"      期望关键词: {keywords}")
            _out(f"      实际回答:   {reply or 'None'}")

    accuracy = correct / total
    _out(f"\n{'─' * 60}")
    result_line = f"  结果: {accuracy * 100:.1f}% ({correct}/{total})"
    if accuracy >= 0.9:
        result_line += " ✅ 通过（目标 ≥ 90%）"
    else:
        result_line += " ❌ 未通过（目标 ≥ 90%）"
    _out(result_line)
    _out(f"{'─' * 60}\n")

    if failed:
        _out(f"  失败详情（{len(failed)} 题失败）:")
        for question, keywords, reply in failed:
            _out(f"    · {question}")
            _out(f"      期望: {keywords}")
            _out(f"      回答: {reply[:80] if reply else 'None'}")

    return accuracy


if __name__ == "__main__":
    import asyncio

    asyncio.run(evaluate_accuracy())

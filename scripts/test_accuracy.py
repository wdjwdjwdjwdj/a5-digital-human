"""准确率测试：使用 100 题标准测试集验证问答准确率 ≥ 90%。"""

import json


def load_test_set() -> list[dict]:
    """加载测试集。

    Returns:
        测试用例列表，每项含 question 和 expected_keywords
    """
    # TODO: 从测试集文件加载
    return []


def evaluate_accuracy() -> float:
    """评估问答准确率。

    Returns:
        准确率（0.0 ~ 1.0）
    """
    test_cases = load_test_set()
    if not test_cases:
        print("⚠️  未加载测试集，返回 0.0")
        return 0.0

    correct = 0
    for case in test_cases:
        # TODO: 调用对话引擎获取回答，检查关键词
        pass

    accuracy = correct / len(test_cases)
    print(f"准确率: {accuracy * 100:.1f}% ({correct}/{len(test_cases)})")
    return accuracy


if __name__ == "__main__":
    evaluate_accuracy()

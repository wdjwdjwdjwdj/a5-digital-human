import httpx
from openai import OpenAI

# 创建自定义 HTTP 客户端，跳过 SSL 证书验证
http_client = httpx.Client(verify=False)

# SenseNova API 配置
client = OpenAI(
    base_url="https://token.sensenova.cn/v1",
    api_key="sk-yd6MZ2zEAcBEBV8nUltPTX1wOw7hjMxz",
    http_client=http_client
)

# 模型1: SenseNova 6.7 Flash-Lite (轻量多模态模型，支持文本+图像)
MODEL_FLASH_LITE = "sensenova-6.7-flash-lite"

# 模型2: DeepSeek V4 Flash (高性能推理模型)
MODEL_DEEPSEEK = "deepseek-v4-flash"


def chat_with_flash_lite(messages, temperature=0.6, max_tokens=65535, stream=False):
    """使用 SenseNova 6.7 Flash-Lite 模型进行对话"""
    response = client.chat.completions.create(
        model=MODEL_FLASH_LITE,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream
    )
    if stream:
        return response
    return response.choices[0].message.content


def chat_with_deepseek(messages, reasoning_effort="medium", temperature=1.0,
                       max_tokens=65536, stream=False):
    """使用 DeepSeek V4 Flash 模型进行对话"""
    response = client.chat.completions.create(
        model=MODEL_DEEPSEEK,
        messages=messages,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        max_tokens=max_tokens,
        stream=stream
    )
    if stream:
        return response

    result = {
        "content": response.choices[0].message.content,
        "reasoning": getattr(response.choices[0].message, 'reasoning_content', None)
    }
    return result


def chat_with_image(image_url, text_prompt, detail="auto"):
    """使用 Flash-Lite 进行图像理解 (多模态)"""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_prompt},
                {"type": "image_url", "image_url": {"url": image_url, "detail": detail}}
            ]
        }
    ]
    response = client.chat.completions.create(
        model=MODEL_FLASH_LITE,
        messages=messages,
        temperature=0.6
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    print("=" * 50)
    print("【模型1】SenseNova 6.7 Flash-Lite 测试")
    print("=" * 50)
    reply = chat_with_flash_lite([
        {"role": "user", "content": "你好，请简单介绍一下自己"}
    ])
    print(f"回复: {reply}\n")

    print("=" * 50)
    print("【模型2】DeepSeek V4 Flash 测试")
    print("=" * 50)
    result = chat_with_deepseek([
        {"role": "user", "content": "你好，请简单介绍一下自己"}
    ])
    print(f"回复: {result['content']}\n")
    print("配置成功！两个模型均可正常使用。")

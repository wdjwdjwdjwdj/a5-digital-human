"""测试 SenseNova 流式模式"""
import asyncio
import sys
import time
sys.path.insert(0, '.')

from backend.services.sensenova import SenseNovaClient

async def test():
    client = SenseNovaClient()
    
    messages = [
        {'role': 'system', 'content': '你是无锡灵山胜境的AI导游灵灵。回答不超过100字。'},
        {'role': 'user', 'content': '灵山大佛有多高？'}
    ]
    
    print('流式测试：灵山大佛有多高？')
    print('=' * 50)
    
    tokens = []
    start = time.monotonic()
    first_token_time = None
    
    async for token in client.chat_stream(messages, max_tokens=1024):
        if first_token_time is None:
            first_token_time = time.monotonic()
            latency = (first_token_time - start) * 1000
            print(f'首 token 延迟: {latency:.0f}ms')
            print('开始输出:', end=' ', flush=True)
        print(token, end='', flush=True)
        tokens.append(token)
    
    print()
    print('=' * 50)
    total_latency = (time.monotonic() - start) * 1000
    full_answer = ''.join(tokens)
    print(f'总延迟: {total_latency:.0f}ms')
    print(f'Token 数: {len(tokens)}')
    print(f'完整回答: {full_answer}')

if __name__ == '__main__':
    asyncio.run(test())

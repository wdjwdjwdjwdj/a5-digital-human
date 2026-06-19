export const meta = {
  name: 'fix-p2-issues',
  description: '修复 P2 核心链路搭建中识别的 7 个代码问题',
  phases: [
    { title: 'Fix Issues', detail: '并行修复 4 个代码域的问题' },
    { title: 'Verify', detail: '运行测试验证修复' },
  ],
}

phase('Fix Issues')

const results = await parallel([
  // Agent A: Fix ASR blocking + FunASR preloading
  () => agent('修复 ASR 阻塞和模型预热问题。任务：1) backend/services/asr_service.py 中 transcribe() 方法，将 model.generate() 同步调用改为 await asyncio.to_thread() 异步执行；2) backend/routes/chat.py 中 voice_chat() 的 transcribe 调用加 await；3) main.py lifespan 中添加 FunASR 模型预热。保持最小改动，不改无关代码。', {
    label: 'Fix ASR + preloading',
    phase: 'Fix Issues',
  }),

  // Agent B: Fix SQLite connection reuse + WAL mode
  () => agent('修复 backend/repository/chat_repo.py 中的 SQLite 连接管理问题。改动：1) __init__ 中创建持久连接 check_same_thread=False；2) 添加 PRAGMA journal_mode=WAL；3) 添加 threading.Lock 保护写操作；4) save_conversation/get_history 复用 self._conn 而非每次新建连接。不修改其他文件。', {
    label: 'Fix SQLite WAL',
    phase: 'Fix Issues',
  }),

  // Agent C: Fix chatbot empty reply + _using_fallback
  () => agent('修复 backend/services/chatbot.py 的两个问题。问题1：_chat_fallback() 中 _add_history 和 _add_to_cache 不在 if reply: 块内，空回复也被记入历史。将这三行挪入 if reply: 块，但 return reply 保留在块外。问题2：self._using_fallback 从未被赋值为 True，在 DeepSeek 切换至通义千问时设置 _using_fallback=True，成功恢复后设回 False。', {
    label: 'Fix chatbot',
    phase: 'Fix Issues',
  }),

  // Agent D: Fix chat.py DRY + naming + TTS cleanup
  () => agent('修复 backend/routes/chat.py 的三个问题。问题1：音频保存逻辑在 send_message() 和 voice_chat() 中重复出现（DRY 违规）。提取模块级函数 _save_audio()，两处调用替换为 audio_url = _save_audio(audio_data)。问题2：/chat/stream 端点的 docstring 强化说明它是普通 JSON 响应而非流式响应。问题3：在 _save_audio 中添加 _cleanup_old_audio() 逻辑，保留最近 200 个文件，删除超过 60 分钟的旧音频。不修改其他文件。', {
    label: 'Fix chat.py',
    phase: 'Fix Issues',
  }),
])

// Phase 2: Verify
phase('Verify')

const testResults = await agent('在 c:/Users/29688/Desktop/a5-digital-human 运行 python -m pytest tests/ -v，报告所有测试结果。如果失败分析原因。', {
  label: 'Run tests',
  phase: 'Verify',
})

return { results, testResults }

# prototype-v2 三端集成迁移指南

## 当前状态（回滚后）

- `frontend/index.html` — 已恢复到原始西湖主题的原始状态（~1171 行，含 VRM Three.js）
- 所有原型文件在 `prototype-v2/` 目录：`mobile-prototype.html`(2273行)、`dashboard.html`(1211行)、`admin.html`(2178行)
- 后端已有路由：`chat_router`(`/chat/message`, `/chat/voice`, `/chat/stream-tts`) — 灵山主题降级上下文已改；`scenic_router`(`/api/scenic/spots`, `/api/scenic/routes` 等 CRUD)；`vrm_router`(`/api/vrm/model`, `/api/vrm/models`)
- 管理后台：Streamlit 保留（`streamlit run admin/app.py`）

## 总体架构

```
frontend/index.html           ← mobile-prototype.html 改造（主界面）
frontend/dashboard.html       ← dashboard.html 适配（数据大屏）
frontend/admin.html           ← admin.html 适配（管理面板）
frontend/static/js/api-adapter.js  ← 共享 API 层（新建）
frontend/static/vrm/          ← VRM 模型文件
main.py                       ← 新增 /dashboard 和 /admin 路由
backend/routes/scenic.py      ← 已有景区数据 CRUD API
```

## 配色系统（灵山）

```css
--primary: #2B5F75   /* 黛青 */
--accent: #C73E3A    /* 朱红 */
--bg: #F5F0E8        /* 素白 */
--warm: #D4A373      /* 琥珀 */
--ink: #2C1810       /* 墨色 */
```

---

## 5 个并行 Agent 任务

### Agent 1: mobile-prototype → frontend/index.html（核心）

**目标**：将 `prototype-v2/mobile-prototype.html` 改造为带 VRM 数字人的真实前端

**输入文件**：
- `prototype-v2/mobile-prototype.html` — 原型 HTML（2273 行）
- `frontend/index.html` — 当前原始页面（含 VRM Three.js 模块）

**要做的事**：

1. **替换标题和 meta**：`杭州西湖 · 水墨导览` → `灵山胜境 · AI 数字人导游`

2. **保留现有 VRM 模块**（`frontend/index.html` L550-680 的 `<script type="module">`）：
   - Three.js + @pixiv/three-vrm 的 importmap
   - VRM 加载、场景初始化、动画循环
   - `window.playVRMAudio()` 函数
   - `window.setVRMExpression()` 函数

3. **将 VRM 嵌入 mobile-prototype 的 chat-3d-avatar 区域**：
   - 原型 L535-588 的 `.chat-3d-avatar` 容器（160×180px）
   - 3D canvas 放这里，fallback 保留

4. **保留 mobile-prototype 的完整结构**：
   - 4-tab 底部导航（首页/地图/AI导游/我的）
   - SPA 页面切换（CSS transition）
   - Chat 页面：消息列表、输入区、快捷问题、语音按钮
   - Map 页面：Leaflet.js + 高德底图
   - 首页：景点卡片、活动列表
   - 我的页面：个人信息框架

5. **替换数据源**：
   - 删除所有对 `LingshanData` 全局对象的引用
   - 改为调用 `api-adapter.js` 中的 API 函数

6. **Chat 接口对接**：
   - `sendMessage(text)` → `POST /chat/message` → `data.reply` + `data.audio_url`
   - 收到 `data.audio_url` 后调用 `playVRMAudio()` 触发口型同步
   - 保留情绪标签 `[情绪: happy/sad/angry/surprise/neutral]`

7. **保留打字动画和骨架屏**：原型已有 skeleton loading，保留

8. **提取 CSS 变量**：替换为灵山配色系统

**验收标准**：
- [ ] 首页正常显示，4 个 tab 可切换
- [ ] VRM 数字人渲染正常，说话时口型动
- [ ] 发送文字消息可收到 AI 回复 + TTS 播报
- [ ] 语音按钮可录音并发送
- [ ] 地图页 Leaflet 加载正常
- [ ] 移动端 390px 布局正常

---

### Agent 2: dashboard.html 适配

**目标**：将 `prototype-v2/dashboard.html` 改为使用真实后端数据

**输入文件**：
- `prototype-v2/dashboard.html` — 暗色主题数据大屏（1211 行）
- `backend/routes/scenic.py` — `/api/scenic/stats` 端点

**要做的事**：

1. **保留暗色主题**（`#0A0A0F` 底色，4 层透明度文字/面板）

2. **替换数据源**：
   - `LingshanData.dashboard` → `fetch('/api/scenic/stats')`
   - KPI 数据（今日客流、在园人数、满意度、AI 对话数）→ 后端真实数据
   - 趋势图/热力图/柱状图/词云 → ECharts 用真实数据渲染

3. **保留 ECharts 自定义暗色主题配置**（原型 L706-1061）

4. **保留 4 个 KPI 卡片 + sparkline + 30s 自动刷新**

5. **保留实时对话列表**（原型 L1063-1125，8s 轮询）

**验收标准**：
- [ ] 4 个 KPI 卡片显示真实数据
- [ ] ECharts 四个图表渲染正常
- [ ] 实时对话列表周期性刷新
- [ ] 暗色主题完整

---

### Agent 3: admin.html 适配

**目标**：将 `prototype-v2/admin.html` 改为 CRUD 对接后端

**输入文件**：
- `prototype-v2/admin.html` — 管理后台原型（2178 行）
- `backend/routes/scenic.py` — 景区 CRUD API

**要做的事**：

1. **保留布局**：240px 侧栏 + sticky 顶栏 + 内容区

2. **替换数据源**：
   - `LingshanData.spots` → `fetch('/api/scenic/spots')` (GET/POST/PUT/DELETE)
   - 侧栏导航项、筛选标签、数据表格、分页均改为 API 驱动

3. **保留 UI 交互**：
   - 表格排序、行 hover 效果、40px 缩略图
   - 筛选标签（类型/状态/搜索）+ 清空全部
   - 分页组件（第 X 页/共 Y 页, 5 个可见页码）
   - Modal 表单（新增/编辑景点，P0-3 即时校验）
   - Toast 通知（4 种类型：success/error/info/warning）
   - 通知中心（铃铛图标 + 下拉面板 + 未读计数）

4. **API 对接**：
   - GET `/api/scenic/spots` — 列表（支持 `?page=&limit=&search=&type=`）
   - POST `/api/scenic/spots` — 新增
   - PUT `/api/scenic/spots/{id}` — 编辑
   - DELETE `/api/scenic/spots/{id}` — 删除

**验收标准**：
- [ ] 景点列表从后端加载
- [ ] 新增/编辑/删除景点功能正常
- [ ] 筛选和搜索正常
- [ ] 分页正常
- [ ] Toast 通知正常

---

### Agent 4: 后端 API 扩展

**目标**：补充后端 API，支持三端需求

**输入文件**：
- `backend/routes/scenic.py` — 已有景区 CRUD
- `main.py` — 路由注册
- `backend/routes/chat.py` — 对话接口

**要做的事**：

1. **新增路由**（在 `main.py`）：
   ```python
   @app.get("/dashboard")
   async def dashboard_page():
       return FileResponse(str(STATIC_DIR.parent / "dashboard.html"))

   @app.get("/admin")
   async def admin_page():
       return FileResponse(str(STATIC_DIR.parent / "admin.html"))
   ```

2. **新增统计端点**（在已有 `/api/scenic/stats` 基础上补充完整 dashboard 数据）

3. **调整 CORS 策略**：确保 dashboard 和 admin 跨域正常

4. **确保静态文件挂载**覆盖 `frontend/` 下所有文件

**验收标准**：
- [ ] `GET /dashboard` 返回 dashboard.html
- [ ] `GET /admin` 返回 admin.html
- [ ] `/api/scenic/stats` 返回完整统计 JSON

---

### Agent 5: api-adapter.js 共享层

**创建** `frontend/static/js/api-adapter.js`

**内容**：

```js
const API = {
  async sendMessage(query, sessionId = 'default') { ... },
  async sendVoice(audioBlob, text = '') { ... },
  async getSpots(params = {}) { ... },
  async createSpot(data) { ... },
  async updateSpot(id, data) { ... },
  async deleteSpot(id) { ... },
  async getStats() { ... },
  async getAIResponses() { ... },
  async getVRMModels() { ... },
  async switchVRMModel(path) { ... },
};
```

**要点**：
- 统一错误处理，返回 `{ error: message }`
- 对话接口保留情绪标签支持
- 请求超时 15s

**验收标准**：
- [ ] 所有端可引入后调用
- [ ] 错误统一处理
- [ ] Chat 接口返回格式正确

---

## 执行顺序

```
第 1 批（并行）：
  Agent 4（后端 API 扩展）
  Agent 5（api-adapter.js）

第 2 批（并行，依赖 API + adapter 完成）：
  Agent 1（mobile-prototype → index.html）← 最核心
  Agent 2（dashboard 适配）
  Agent 3（admin 适配）
```

## 关键注意点

1. **VRM 模块必须保留**：现有 `frontend/index.html` L8-17 importmap + L550-680 Three.js/VRM 代码是核心资产
2. **Chat 返回格式**：`{ reply: string, audio_url: string|null, emotion: string|null }`
3. **不要删除 Streamlit**：保留 `streamlit run admin/app.py`
4. **移动优先**：手机 390px 断点优先
5. **配色替换**：西湖颜色 → 灵山颜色

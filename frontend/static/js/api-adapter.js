/**
 * api-adapter.js — 灵山胜境 AI 数字人共享 API 层
 *
 * 所有前端页面（index.html / dashboard.html / admin.html）
 * 通过此适配器访问后端 API，统一错误处理与超时控制。
 *
 * 引入方式：
 *   <script src="/static/js/api-adapter.js"></script>
 *   之后通过 window.API 调用所有方法。
 */

(function () {
  'use strict';

  var BASE_URL = '';

  var DEFAULT_TIMEOUT = 15000; // 15s

  var BASE_HEADERS = {
    'Content-Type': 'application/json',
  };

  /**
   * 带超时的 fetch 封装
   * @param {string} url
   * @param {object} [options]
   * @param {number} [timeout]
   * @returns {Promise<any>}
   */
  function _request(url, options, timeout) {
    options = options || {};
    timeout = timeout || DEFAULT_TIMEOUT;

    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, timeout);

    var opts = {
      signal: controller.signal,
      headers: Object.assign({}, BASE_HEADERS, options.headers || {}),
    };

    // 如果是 FormData，删除 Content-Type 让浏览器自动设置 boundary
    if (options.body instanceof FormData) {
      delete opts.headers['Content-Type'];
    }

    if (options.method) opts.method = options.method;
    if (options.body !== undefined) opts.body = options.body;

    return fetch(url, opts)
      .then(function (res) {
        clearTimeout(timer);
        if (!res.ok) {
          return res.text().then(function (text) {
            var msg = 'HTTP ' + res.status;
            try {
              var json = JSON.parse(text);
              if (json.error) msg = json.error;
              if (json.detail) msg = json.detail;
            } catch (_) {
              if (text) msg = text;
            }
            throw new Error(msg);
          });
        }
        return res.json();
      })
      .catch(function (err) {
        clearTimeout(timer);
        if (err.name === 'AbortError') {
          throw new Error('请求超时 (' + (timeout / 1000) + 's)');
        }
        throw err;
      });
  }

  /**
   * 统一处理景区数据接口响应格式 {success, data, error}
   * 成功时返回 data，失败时返回 { error }
   * @param {object} json
   * @returns {any}
   */
  function _unwrapScenic(json) {
    if (json && json.success === true) {
      return json.data;
    }
    return { error: (json && json.error) || '未知错误' };
  }

  // ============================================================
  // 对外 API
  // ============================================================
  var API = {
    // ─────────── 对话接口 ───────────

    /**
     * 发送文字消息
     * @param {string} query  用户输入文本
     * @param {string} [sessionId='default'] 会话 ID
     * @returns {Promise<{reply: string, audio_url: string|null, emotion: string|null}>}
     */
    sendMessage: function (query, sessionId) {
      sessionId = sessionId || 'default';
      return _request(BASE_URL + '/chat/message', {
        method: 'POST',
        body: JSON.stringify({ query: query, session_id: sessionId }),
      });
    },

    /**
     * 发送语音消息（用 FormData 上传音频 Blob）
     * @param {Blob}  audioBlob  录音文件 (WAV/WebM)
     * @param {string} [text='']  前端 ASR 识别的文本
     * @param {string} [sessionId='default']  会话 ID
     * @returns {Promise<{reply: string, audio_url: string|null, asr_text: string, emotion: string|null}>}
     */
    sendVoice: function (audioBlob, text, sessionId) {
      text = text || '';
      sessionId = sessionId || 'default';
      var form = new FormData();
      form.append('audio', audioBlob, 'recording.wav');
      form.append('text', text);
      form.append('session_id', sessionId);
      return _request(BASE_URL + '/chat/voice', {
        method: 'POST',
        body: form,
      });
    },

    // ─────────── 景区数据接口 ───────────

    /**
     * 获取景区基础信息
     * @returns {Promise<object>}
     */
    getArea: function () {
      return _request(BASE_URL + '/api/v1/scenic/area').then(_unwrapScenic);
    },

    /**
     * 获取景点列表（支持按 category 过滤）
     * @param {object} [params]  { category?: string }
     * @returns {Promise<Array>}
     */
    getSpots: function (params) {
      params = params || {};
      var qs = [];
      if (params.category) qs.push('category=' + encodeURIComponent(params.category));
      var url = BASE_URL + '/api/v1/scenic/spots';
      if (qs.length) url += '?' + qs.join('&');
      return _request(url).then(_unwrapScenic);
    },

    /**
     * 获取单个景点详情
     * @param {string} spotId
     * @returns {Promise<object>}
     */
    getSpot: function (spotId) {
      return _request(BASE_URL + '/api/v1/scenic/spots/' + encodeURIComponent(spotId)).then(_unwrapScenic);
    },

    /**
     * 获取活动列表
     * @returns {Promise<Array>}
     */
    getActivities: function () {
      return _request(BASE_URL + '/api/v1/scenic/activities').then(_unwrapScenic);
    },

    /**
     * 获取路线列表
     * @returns {Promise<Array>}
     */
    getRoutes: function () {
      return _request(BASE_URL + '/api/v1/scenic/routes').then(_unwrapScenic);
    },

    /**
     * 获取单个路线详情
     * @param {number|string} routeId
     * @returns {Promise<object>}
     */
    getRoute: function (routeId) {
      return _request(BASE_URL + '/api/v1/scenic/routes/' + encodeURIComponent(routeId)).then(_unwrapScenic);
    },

    /**
     * 获取景区统计信息
     * @returns {Promise<object>}
     */
    getStats: function () {
      return _request(BASE_URL + '/api/v1/scenic/stats').then(_unwrapScenic);
    },

    /**
     * 获取 AI 问答映射配置
     * @returns {Promise<object>}
     */
    getAIResponses: function () {
      return _request(BASE_URL + '/api/v1/scenic/ai-responses').then(_unwrapScenic);
    },

    // ─────────── 配置接口 ───────────

    /**
     * 获取景区配置
     * @returns {Promise<object>}
     */
    getConfig: function () {
      return _request(BASE_URL + '/api/v1/scenic/config').then(_unwrapScenic);
    },

    /**
     * 更新景区配置（需管理员 token）
     * @param {object} data  配置字段
     * @param {string} token  管理员 token
     * @returns {Promise<object>}
     */
    updateConfig: function (data, token) {
      return _request(BASE_URL + '/api/v1/scenic/config', {
        method: 'PUT',
        headers: { 'X-Admin-Token': token },
        body: JSON.stringify(data),
      }).then(_unwrapScenic);
    },

    // ─────────── 管理 CRUD（需 admin token） ───────────

    /**
     * 新增景点
     * @param {object} data  { name, category, ... }
     * @param {string} token
     * @returns {Promise<object>}
     */
    createSpot: function (data, token) {
      return _request(BASE_URL + '/api/v1/scenic/spots', {
        method: 'POST',
        headers: { 'X-Admin-Token': token },
        body: JSON.stringify(data),
      }).then(_unwrapScenic);
    },

    /**
     * 更新景点
     * @param {string} id
     * @param {object} data
     * @param {string} token
     * @returns {Promise<object>}
     */
    updateSpot: function (id, data, token) {
      return _request(BASE_URL + '/api/v1/scenic/spots/' + encodeURIComponent(id), {
        method: 'PUT',
        headers: { 'X-Admin-Token': token },
        body: JSON.stringify(data),
      }).then(_unwrapScenic);
    },

    /**
     * 删除景点
     * @param {string} id
     * @param {string} token
     * @returns {Promise<object>}
     */
    deleteSpot: function (id, token) {
      return _request(BASE_URL + '/api/v1/scenic/spots/' + encodeURIComponent(id), {
        method: 'DELETE',
        headers: { 'X-Admin-Token': token },
      }).then(_unwrapScenic);
    },

    // ─────────── VRM 接口 ───────────

    /**
     * 获取可用 VRM 模型列表
     * @returns {Promise<Array<{name: string, path: string}>>}
     */
    getVRMModels: function () {
      return _request(BASE_URL + '/api/vrm/models');
    },

    /**
     * 切换 VRM 模型
     * @param {string} path  模型文件名（如 AliciaSolid.vrm）
     * @returns {Promise<{success: boolean, model_path: string, message: string}>}
     */
    switchVRMModel: function (path) {
      return _request(BASE_URL + '/api/vrm/model', {
        method: 'POST',
        body: JSON.stringify({ path: path }),
      });
    },
  };

  // 暴露到全局
  window.API = API;
})();

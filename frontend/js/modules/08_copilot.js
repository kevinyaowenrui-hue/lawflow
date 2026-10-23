/**
 * LawFlow Module: 08_copilot.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const COPILOT_TAB_HTML = `      
      <!-- 08 模块顶部通栏工作台指示条 -->
      <div class="card" style="margin-bottom: 14px; padding: 14px 18px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; background: #0D1526; color: #FFFFFF; border: 1px solid rgba(255, 255, 255, 0.1);">
        <div style="display: flex; align-items: center; gap: 12px;">
          <div style="width: 38px; height: 38px; border-radius: 50%; background: rgba(197, 133, 50, 0.2); border: 1.5px solid #C58532; display: flex; align-items: center; justify-content: center; color: #F59E0B;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
          </div>
          <div>
            <div style="font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 8px;">
              <span>08 智律 AI 语音中枢 · 全模块联动工作台</span>
              <span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #4ADE80; font-size: 11px; border: 1px solid rgba(34, 197, 94, 0.3);">全域总线贯通</span>
            </div>
            <div style="font-size: 12px; color: #94A3B8; margin-top: 2px;">
              支持免提连续通话与按键口述，一句话自动执行 01~07 全模块精算/法典检索/起诉状装配与办案任务自动归纳
            </div>
          </div>
        </div>
        <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="syncCaseContextToCopilotUI()" style="color: #E2E8F0; border-color: rgba(255,255,255,0.2); background: rgba(255,255,255,0.06);" title="将全局当前在办案件上下文同步至语音总控">
            🔄 同步案件总线
          </button>
          <button type="button" class="btn btn-amber btn-sm" onclick="openCreateTaskModal()">
            ＋ 新建办案任务
          </button>
        </div>
      </div>

      <!-- 双栏网格主体：左侧语音通话与调度流 + 右侧智能办案任务看板 -->
      <div class="copilot-grid-layout">

        <!-- 左栏：语音实时交互中心与跨模块执行进度链 -->
        <div class="copilot-voice-panel">
          
          <!-- 声波交互画布与实时状态指示 -->
          <div class="copilot-visualizer-container">
            <canvas id="copilot-voice-canvas" class="copilot-canvas"></canvas>
            <div class="visualizer-overlay-info">
              <div class="voice-call-status-pill" id="copilot-status-pill">
                <span class="pulse-dot" id="copilot-status-dot" style="background: #22C55E;"></span>
                <span id="copilot-status-text">通话空闲 · 随时可口述案情</span>
              </div>
              <div style="font-size: 11px; color: #94A3B8; letter-spacing: 0.5px;">
                <span id="copilot-mode-label">双模智能语音引擎</span> · <span id="copilot-vad-tip">静音 1.5s 自动断句发送</span>
              </div>
            </div>
          </div>

          <!-- 语音控制操作工具条 -->
          <div class="voice-control-toolbar">
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <button type="button" class="call-btn-primary" id="btn-toggle-call" onclick="toggleVoiceCall()">
                <span id="call-icon">🎙️</span>
                <span id="call-label">开启免提实时通话</span>
              </button>
              <button type="button" class="ptt-talk-btn" id="btn-ptt-talk" onmousedown="startPttSpeech()" onmouseup="stopPttSpeech()" ontouchstart="startPttSpeech()" ontouchend="stopPttSpeech()" title="按住说话，松开发送">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
                <span id="ptt-label">按住口述 (PTT)</span>
              </button>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
              <select aria-label="选择自然真人发音人声"  id="copilot-voice-select" onchange="onVoiceSelectionChanged(this.value)" title="选择自然真人发音人声" style="background: #0A101D; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.18); border-radius: 4px; padding: 4px 8px; font-size: 11px; outline: none; cursor: pointer; max-width: 220px;">
                <option value="">正在检测高质量人声...</option>
              </select>
              <button type="button" class="btn btn-secondary btn-sm" onclick="testCurrentVoice()" title="试听当前所选人声音色" style="color: #F59E0B; background: rgba(245,158,11,0.1); border-color: rgba(245,158,11,0.3); font-size: 11px; padding: 3px 8px;">
                <span>🔊 试听</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" id="btn-toggle-tts" onclick="toggleTtsMute()" style="color: #CBD5E1; background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.15); font-size: 11px;">
                <span id="tts-icon">🔊</span> <span id="tts-label">AI语音播报: 开</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="clearCopilotMessagesUI()" style="color: #94A3B8; background: transparent; border-color: rgba(255,255,255,0.1); font-size: 11px;">
                清空对话
              </button>
            </div>
          </div>

          <!-- 实时语音转录预览条 -->
          <div class="speech-transcript-preview" id="copilot-transcript-box">
            <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
              <span style="font-size: 11px; color: #F59E0B; font-weight: 700; white-space: nowrap;">[实时转录]</span>
              <span id="copilot-transcript-text" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">点击上方按钮开启免提通话，或按住说话口述案情与交办要求...</span>
            </div>
            <span id="copilot-vad-indicator" style="font-size: 10px; color: #64748B; white-space: nowrap;">VAD 待命</span>
          </div>

          <!-- 快捷语音指令推荐 Chips -->
          <div style="padding: 8px 14px; background: #0E1626; border-bottom: 1px solid rgba(255,255,255,0.06); display: flex; gap: 6px; flex-wrap: wrap;">
            <span style="font-size: 10.5px; color: #64748B; line-height: 22px;">推荐指令:</span>
            <button type="button" class="badge" style="background: rgba(255,255,255,0.06); color: #93C5FD; border: 1px solid rgba(147,197,253,0.25); cursor: pointer; padding: 2px 8px; font-size: 11px;" onclick="triggerQuickVoiceCommand('帮我把借款本金调为85万元，从2023年5月1日按LPR算逾期利息并同步全案')">
              ⚡ 核算85万LPR利息并同步
            </button>
            <button type="button" class="badge" style="background: rgba(255,255,255,0.06); color: #FCD34D; border: 1px solid rgba(252,211,77,0.25); cursor: pointer; padding: 2px 8px; font-size: 11px;" onclick="triggerQuickVoiceCommand('查下民法典第667条关于借款合同的法条依据')">
              ⚡ 检索借款合同法条
            </button>
            <button type="button" class="badge" style="background: rgba(255,255,255,0.06); color: #6EE7B7; border: 1px solid rgba(110,231,183,0.25); cursor: pointer; padding: 2px 8px; font-size: 11px;" onclick="triggerQuickVoiceCommand('把当事人李四诉张三要素装配到02起诉状并记一个调取微信转账记录的任务')">
              ⚡ 装配起诉状并记待办
            </button>
            <button type="button" class="badge" style="background: rgba(255,255,255,0.06); color: #C4B5FD; border: 1px solid rgba(196,181,253,0.25); cursor: pointer; padding: 2px 8px; font-size: 11px;" onclick="triggerQuickVoiceCommand('新增一个任务：向朝阳法院提交财产保全续保申请，优先级紧急，截止本周五')">
              ⚡ 记保全续保任务
            </button>
          </div>

          <!-- 协同对话流水（含跨模块动作执行链卡片） -->
          <div class="copilot-messages-stream" id="copilot-messages-stream">
            <!-- 初始欢迎卡 -->
            <div class="copilot-chat-bubble assistant">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <span style="font-weight: 700; color: #F59E0B; display: flex; align-items: center; gap: 5px;">
                  <span>⚖️</span> 智律 AI 协同总控
                </span>
                <span style="font-size: 10.5px; color: #64748B;">系统就绪</span>
              </div>
              <div style="font-size: 12.5px; color: #E2E8F0; line-height: 1.6;">
                律师您好！我是您的 <strong>全模块 AI 语音协同副驾</strong>。您可以直接像打电话一样对我口述案情，例如：<br>
                <em>“帮我把借款本金调为85万，算下从2023年5月1日起算的LPR利息，查下借款合同法条，顺便记一个调取银行流水的待办”</em>。<br>
                我将自动解析意图、同步当前在办案情，并调度 01~07 各模块执行计算与文书装配。
              </div>
            </div>
          </div>

          <!-- 底部键盘输入备用栏（无麦克风或嘈杂环境一键文字打通） -->
          <div style="padding: 10px 14px; background: #111A2E; border-top: 1px solid rgba(255,255,255,0.08); display: flex; gap: 8px;">
            <input aria-label="向智律 AI 副驾发送指令或交办案件任务"  type="text" id="copilot-text-input" class="quick-input" style="flex: 1; background: #080D1A; color: #F8FAFC; border: 1px solid rgba(255,255,255,0.15);" placeholder="口述或输入指令，如：核算85万利息并记一个调取流水待办..." onkeydown="if(event.key==='Enter') sendCopilotTextMessage()">
            <button type="button" class="btn btn-amber btn-sm" onclick="sendCopilotTextMessage()" style="white-space: nowrap;">
              发送指令
            </button>
          </div>

        </div>

        <!-- 右栏：智能办案任务看板 -->
        <div class="copilot-task-panel">
          
          <!-- 看板头部与统计 -->
          <div class="task-panel-header">
            <div>
              <div style="font-size: 14px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 8px;">
                <span>📋 智能办案任务看板</span>
                <span class="badge" style="background: #EEF2F6; color: var(--primary-navy); font-size: 11px;" id="task-header-count">共 0 项任务</span>
              </div>
              <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 2px;">
                语音对话中交办的工作将自动提炼并按办案阶段与优先级落盘归纳
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="batchMarkAllTasksDoneUI()" title="将当前筛选的所有待办一键标为已完成">
                ✓ 全部完成
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="loadCopilotTasksUI()" title="重新从数据库拉取最新任务">
                🔄 刷新
              </button>
            </div>
          </div>

          <!-- 阶段筛选栏 -->
          <div class="task-stage-filter-bar">
            <button type="button" class="task-filter-pill active" onclick="filterTaskByStage(this, 'all')">全部 (<span id="cnt-stage-all">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '立案')">立案 (<span id="cnt-stage-立案">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '精算')">精算 (<span id="cnt-stage-精算">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '证据')">证据 (<span id="cnt-stage-证据">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '检索')">检索 (<span id="cnt-stage-检索">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '庭审')">庭审 (<span id="cnt-stage-庭审">0</span>)</button>
            <button type="button" class="task-filter-pill" onclick="filterTaskByStage(this, '执行')">执行 (<span id="cnt-stage-执行">0</span>)</button>
          </div>

          <!-- 任务状态切换条 -->
          <div style="padding: 6px 16px; background: #FFFFFF; border-bottom: 1px solid var(--border-hairline); display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; gap: 8px;">
              <span role="button" tabindex="0"  style="font-size: 11.5px; color: var(--text-secondary); cursor: pointer;" id="tab-status-all" onclick="filterTaskByStatus('all')"><strong>全部</strong></span>
              <span role="button" tabindex="0"  style="font-size: 11.5px; color: var(--text-muted); cursor: pointer;" id="tab-status-todo" onclick="filterTaskByStatus('todo')">待处理 (<span id="cnt-status-todo">0</span>)</span>
              <span role="button" tabindex="0"  style="font-size: 11.5px; color: var(--text-muted); cursor: pointer;" id="tab-status-in_progress" onclick="filterTaskByStatus('in_progress')">进行中 (<span id="cnt-status-in_progress">0</span>)</span>
              <span role="button" tabindex="0"  style="font-size: 11.5px; color: var(--text-muted); cursor: pointer;" id="tab-status-done" onclick="filterTaskByStatus('done')">已完成 (<span id="cnt-status-done">0</span>)</span>
            </div>
            <span style="font-size: 11px; color: var(--text-muted);">点击复选框即时更新状态</span>
          </div>

          <!-- 任务卡片列表容器 -->
          <div class="task-list-container" id="copilot-task-list">
            <!-- 动态渲染任务卡片 -->
          </div>

        </div>

      </div>

    </section>

  </main>

  <!-- 轻量悬浮 Toast 消息提示 -->
  <div class="toast-container" id="toast-container"></div>
  <div class="global-disclaimer-bar" id="global-disclaimer-bar">本输出由软件自动生成，仅供执业律师参考，不构成法律意见，须经律师审核后使用。</div>
`;

export function renderTabCopilot() {
  const el = document.getElementById('tab-copilot');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = COPILOT_TAB_HTML;
  }
}


    // =========================================================================
    let isCopilotCallActive = false;
    let isCopilotListening = false;
    let isCopilotThinking = false;
    let isCopilotSpeaking = false;
    let isCopilotTtsMuted = false;
    let copilotRecognition = null;
    let copilotVadTimer = null;
    let copilotLastTranscript = "";
    let copilotVoiceState = "idle"; // "idle" | "listening" | "thinking" | "speaking"

    // 高质量真人人声与防回声自激锁
    let selectedCopilotVoice = null;
    let availableCopilotVoices = [];
    let lastSpokenText = "";
    let lastExecutedCommand = "";
    let lastExecutedTimestamp = 0;
    let ttsEchoSafetyTimeout = null;

    let copilotTasksCache = [];
    let copilotFilterStage = "all";
    let copilotFilterStatus = "all";

    // 声波可视化变量 (严格遵守零分配准则，循环外预分配)
    let visualizerCanvas = null;
    let visualizerCtx = null;
    let visualizerAnimId = null;
    let visualizerWavePhase = 0;
    const VISUALIZER_DPR = Math.min(window.devicePixelRatio || 1, 1.5);

    function initCopilotWorkspace() {
      initCopilotCanvas();
      initSpeechRecognitionEngine();
      loadCopilotTasksUI();
      populateVoicesList();
    }

    // 动态提取并优选高质量自然人声 (优先挑选微软云希/晓晓大模型真人音色)
    function populateVoicesList() {
      if (!('speechSynthesis' in window)) return;
      const voices = window.speechSynthesis.getVoices();
      if (!voices || voices.length === 0) return;

      // 筛选中文语音
      availableCopilotVoices = voices.filter(v =>
        v.lang === 'zh-CN' || v.lang === 'zh_CN' || v.lang.startsWith('zh') || (v.name && v.name.includes('Chinese'))
      );

      if (availableCopilotVoices.length === 0) {
        availableCopilotVoices = voices;
      }

      // 自然真人语音打分排序：微软晓晓/云希自然大模型女声/男声排在最前
      availableCopilotVoices.sort((a, b) => {
        const getScore = (v) => {
          let score = 0;
          const name = (v.name || '').toLowerCase();
          if (name.includes('xiaoxiao')) score += 100;
          if (name.includes('yunxi')) score += 90;
          if (name.includes('xiaoyi')) score += 80;
          if (name.includes('natural')) score += 50;
          if (name.includes('online')) score += 40;
          if (name.includes('huihui')) score += 20;
          if (v.lang === 'zh-CN') score += 10;
          return score;
        };
        return getScore(b) - getScore(a);
      });

      // 默认选中综合评分最高的真人声音
      if (!selectedCopilotVoice && availableCopilotVoices.length > 0) {
        selectedCopilotVoice = availableCopilotVoices[0];
      }

      // 更新大屏与抽屉的下拉框
      const selects = [
        document.getElementById('copilot-voice-select'),
        document.getElementById('drawer-voice-select')
      ];

      selects.forEach(sel => {
        if (!sel) return;
        sel.innerHTML = '';
        availableCopilotVoices.forEach(v => {
          const opt = document.createElement('option');
          opt.value = v.name;
          let label = v.name;
          if (v.name.includes('Xiaoxiao')) label = "🌟 晓晓 (微软顶级情感拟真女声)";
          else if (v.name.includes('Yunxi')) label = "🌟 云希 (微软沉稳专业律师男声)";
          else if (v.name.includes('Xiaoyi')) label = "🌟 晓伊 (微软自然亲和女声)";
          else if (v.name.includes('Yunjian')) label = "🌟 云健 (微软自然男声)";
          else if (v.name.includes('Natural')) label = `✨ ${v.name.replace(/Microsoft | - Chinese \(Mainland\)/g, '')} (自然声)`;
          else if (v.name.includes('Huihui')) label = "👤 慧慧 (经典播报女声)";
          opt.innerText = label;
          if (selectedCopilotVoice && selectedCopilotVoice.name === v.name) {
            opt.selected = true;
          }
          sel.appendChild(opt);
        });
      });
    }

    if ('speechSynthesis' in window) {
      window.speechSynthesis.onvoiceschanged = populateVoicesList;
      setTimeout(populateVoicesList, 200);
      setTimeout(populateVoicesList, 1000);
    }

    function onVoiceSelectionChanged(voiceName) {
      const found = availableCopilotVoices.find(v => v.name === voiceName);
      if (found) {
        selectedCopilotVoice = found;
        const s1 = document.getElementById('copilot-voice-select');
        const s2 = document.getElementById('drawer-voice-select');
        if (s1 && s1.value !== voiceName) s1.value = voiceName;
        if (s2 && s2.value !== voiceName) s2.value = voiceName;
        showToast(`已切换人声音色为：${found.name.split(' ')[1] || found.name}`);
      }
    }

    function testCurrentVoice() {
      speakTextTTS("您好！我是智律协同副驾。这套拟真专业律师人声听起来是否从容自然？");
    }

    // 声波画布初始化与轻量流畅逐帧渲染
    function initCopilotCanvas() {
      visualizerCanvas = document.getElementById('copilot-voice-canvas');
      if (!visualizerCanvas) return;
      visualizerCtx = visualizerCanvas.getContext('2d');
      resizeCopilotCanvas();
      window.addEventListener('resize', resizeCopilotCanvas);
      if (!visualizerAnimId) {
        visualizerAnimId = requestAnimationFrame(renderVoiceVisualizerLoop);
      }
    }

    function resizeCopilotCanvas() {
      if (!visualizerCanvas || !visualizerCtx) return;
      const rect = visualizerCanvas.getBoundingClientRect();
      const w = rect.width || 600;
      const h = rect.height || 140;
      visualizerCanvas.width = Math.floor(w * VISUALIZER_DPR);
      visualizerCanvas.height = Math.floor(h * VISUALIZER_DPR);
      visualizerCtx.scale(VISUALIZER_DPR, VISUALIZER_DPR);
    }

    function renderVoiceVisualizerLoop() {
      if (!visualizerCanvas || !visualizerCtx) {
        visualizerAnimId = requestAnimationFrame(renderVoiceVisualizerLoop);
        return;
      }

      const rect = visualizerCanvas.getBoundingClientRect();
      const w = rect.width;
      const h = rect.height;
      visualizerCtx.clearRect(0, 0, w, h);

      visualizerWavePhase += 0.04;
      const centerY = h / 2;

      let baseAmp = 8;
      let strokeColor1 = "rgba(16, 185, 129, 0.4)";
      let strokeColor2 = "rgba(56, 189, 248, 0.35)";

      if (copilotVoiceState === 'listening') {
        baseAmp = 28;
        strokeColor1 = "rgba(34, 197, 94, 0.85)";
        strokeColor2 = "rgba(56, 189, 248, 0.75)";
      } else if (copilotVoiceState === 'thinking') {
        baseAmp = 18;
        strokeColor1 = "rgba(245, 158, 11, 0.85)";
        strokeColor2 = "rgba(234, 179, 8, 0.65)";
      } else if (copilotVoiceState === 'speaking') {
        baseAmp = 24;
        strokeColor1 = "rgba(56, 189, 248, 0.9)";
        strokeColor2 = "rgba(129, 140, 248, 0.8)";
      }

      // 波形 1
      visualizerCtx.beginPath();
      visualizerCtx.lineWidth = 2;
      visualizerCtx.strokeStyle = strokeColor1;
      for (let x = 0; x <= w; x += 4) {
        const norm = x / w;
        const envelope = Math.sin(norm * Math.PI); // 两头低中间高
        const y = centerY + Math.sin(norm * 10 + visualizerWavePhase) * baseAmp * envelope;
        if (x === 0) visualizerCtx.moveTo(x, y);
        else visualizerCtx.lineTo(x, y);
      }
      visualizerCtx.stroke();

      // 波形 2 (反相稍小)
      visualizerCtx.beginPath();
      visualizerCtx.lineWidth = 1.5;
      visualizerCtx.strokeStyle = strokeColor2;
      for (let x = 0; x <= w; x += 4) {
        const norm = x / w;
        const envelope = Math.sin(norm * Math.PI);
        const y = centerY + Math.cos(norm * 8 - visualizerWavePhase * 1.2) * (baseAmp * 0.7) * envelope;
        if (x === 0) visualizerCtx.moveTo(x, y);
        else visualizerCtx.lineTo(x, y);
      }
      visualizerCtx.stroke();

      visualizerAnimId = requestAnimationFrame(renderVoiceVisualizerLoop);
    }

    // 状态更新与指示器切换
    function setCopilotStatus(state, statusText) {
      copilotVoiceState = state;
      const statusPill = document.getElementById('copilot-status-pill');
      const statusDot = document.getElementById('copilot-status-dot');
      const statusLabel = document.getElementById('copilot-status-text');

      const drawerDot = document.getElementById('drawer-voice-dot');
      const drawerStatus = document.getElementById('drawer-voice-status');
      const orb = document.getElementById('global-voice-orb');
      const orbDot = document.getElementById('global-orb-status-dot');

      if (statusPill) {
        statusPill.className = `voice-call-status-pill ${state}`;
      }
      if (statusLabel) {
        statusLabel.innerText = statusText;
      }

      let color = "#22C55E";
      if (state === 'thinking') color = "#F59E0B";
      else if (state === 'speaking') color = "#38BDF8";
      else if (state === 'idle') color = "#10B981";

      if (statusDot) statusDot.style.background = color;
      if (drawerDot) drawerDot.style.background = color;
      if (drawerStatus) drawerStatus.innerText = statusText;
      if (orbDot) orbDot.style.background = color;

      if (orb) {
        if (state === 'listening' || state === 'speaking') {
          orb.classList.add('calling');
        } else {
          orb.classList.remove('calling');
        }
      }
    }

    // 麦克风识别自愈与状态维护看门狗
    function ensureRecognitionRunning() {
      if (!isCopilotCallActive || isCopilotSpeaking) return;
      if (!copilotRecognition) {
        initSpeechRecognitionEngine();
        return;
      }
      try {
        copilotRecognition.start();
        isCopilotListening = true;
      } catch (e) {
        if (e.name === 'InvalidStateError') {
          // 已经处于启动中或运行中，标记为已监听
          isCopilotListening = true;
        } else {
          console.warn("[Copilot] 麦克风自愈唤醒提示:", e);
        }
      }
    }

    // 定时心跳看门狗：防止任何意外边缘情况导致麦克风中断未自愈
    setInterval(() => {
      if (isCopilotCallActive && !isCopilotSpeaking && !isCopilotListening) {
        ensureRecognitionRunning();
      }
    }, 1200);

    // Web Speech API 实时识别初始化
    function initSpeechRecognitionEngine() {
      const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!SpeechRecognition) {
        console.warn("当前浏览器环境未探测到 Web Speech API，降级为精准文本指令模式");
        const tipEl = document.getElementById('copilot-mode-label');
        if (tipEl) tipEl.innerText = "文字指令模式 (浏览器无内置麦克风API)";
        return;
      }

      copilotRecognition = new SpeechRecognition();
      copilotRecognition.lang = 'zh-CN';
      copilotRecognition.continuous = true;
      copilotRecognition.interimResults = true;

      copilotRecognition.onstart = () => {
        isCopilotListening = true;
        setCopilotStatus('listening', '正在实时倾听案情与指令...');
        const vadInd = document.getElementById('copilot-vad-indicator');
        if (vadInd) vadInd.innerText = "🎤 麦克风已激活 · 请随时口述";
      };

      copilotRecognition.onresult = (event) => {
        // 关键防自激：如果 AI 正在播报发声，物理丢弃所有录入内容，严禁抓取扬声器回音
        if (isCopilotSpeaking) {
          clearTimeout(copilotVadTimer);
          copilotLastTranscript = "";
          return;
        }

        let interimTranscript = '';
        let finalTranscript = '';

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            finalTranscript += event.results[i][0].transcript;
          } else {
            interimTranscript += event.results[i][0].transcript;
          }
        }

        const displayText = (finalTranscript || interimTranscript).trim();
        if (!displayText) return;

        // 过滤环境底噪、咳嗽与极短无意义虚词（杜绝无指令误触发）
        if (displayText.length < 2 || ['嗯', '啊', '哦', '好的', '好', '对', '喂', '呃', '...', '好的。'].includes(displayText)) {
          return;
        }

        // 过滤回声特征与刚刚播报过的文案
        if (lastSpokenText && (lastSpokenText.includes(displayText) || displayText.includes(lastSpokenText.slice(0, 8)))) {
          console.log("[AEC] 物理屏蔽自身扬声器回声:", displayText);
          return;
        }

        copilotLastTranscript = displayText;
        const mainPreview = document.getElementById('copilot-transcript-text');
        const drawerPreview = document.getElementById('drawer-transcript-text');
        if (mainPreview) mainPreview.innerText = displayText;
        if (drawerPreview) drawerPreview.innerText = displayText;

        // 动态停顿检测：句子过短留足停顿余地 (2200ms)；句子完整有标点/关键词 (1300ms)
        if (isCopilotCallActive) {
          clearTimeout(copilotVadTimer);
          const vadInd = document.getElementById('copilot-vad-indicator');
          const isCompleteClause = /[。！？，元万条度项]/.test(displayText) || displayText.length >= 10;
          const vadDelay = isCompleteClause ? 1300 : 2200;

          if (vadInd) vadInd.innerText = "🎙️ 正在口述... (停顿后自动执行)";

          copilotVadTimer = setTimeout(() => {
            if (isCopilotSpeaking || isCopilotThinking) {
              copilotLastTranscript = "";
              return;
            }
            if (copilotLastTranscript.trim()) {
              const textToSend = copilotLastTranscript.trim();
              copilotLastTranscript = "";
              executeCopilotCommand(textToSend, "voice");
            }
          }, vadDelay);
        }
      };

      copilotRecognition.onerror = (event) => {
        // 'no-speech' 与 'aborted' 是正常的静音事件，严格不断开通话！
        if (event.error === 'no-speech' || event.error === 'aborted') {
          if (isCopilotCallActive && !isCopilotSpeaking) {
            setTimeout(ensureRecognitionRunning, 80);
          }
          return;
        }
        if (event.error === 'not-allowed') {
          showToast("麦克风权限未授予，请允许浏览器使用麦克风！");
          stopCopilotCall();
        }
      };

      copilotRecognition.onend = () => {
        isCopilotListening = false;
        // 关键自愈：用户哪怕说话中途中断、停顿，无论何时触发 onend，立即在 60ms 内无缝恢复录入！
        if (isCopilotCallActive && !isCopilotSpeaking) {
          setTimeout(ensureRecognitionRunning, 60);
        } else if (!isCopilotCallActive) {
          setCopilotStatus('idle', '通话空闲 · 随时可口述案情');
          const vadInd = document.getElementById('copilot-vad-indicator');
          if (vadInd) vadInd.innerText = "VAD 待命";
        }
      };
    }

    // 免提连续通话开关
    function toggleVoiceCall() {
      if (isCopilotCallActive) {
        stopCopilotCall();
      } else {
        startCopilotCall();
      }
    }

    function startCopilotCall() {
      if (!copilotRecognition) {
        initSpeechRecognitionEngine();
      }
      isCopilotCallActive = true;
      const btn = document.getElementById('btn-toggle-call');
      const drawerBtn = document.getElementById('drawer-btn-call');
      if (btn) {
        btn.classList.add('active-hangup');
        btn.innerHTML = `<span>🛑</span> <span>挂断免提通话</span>`;
      }
      if (drawerBtn) {
        drawerBtn.classList.add('btn-secondary');
        drawerBtn.classList.remove('btn-amber');
        drawerBtn.innerText = "🛑 挂断通话";
      }

      ensureRecognitionRunning();
      showToast("已开启免提连续通话模式！请直接口述案情或交办指令");
    }

    function stopCopilotCall() {
      isCopilotCallActive = false;
      clearTimeout(copilotVadTimer);
      clearTimeout(ttsEchoSafetyTimeout);
      copilotLastTranscript = "";

      // 充分挂断并中止任何发音
      if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
      }
      isCopilotSpeaking = false;

      const btn = document.getElementById('btn-toggle-call');
      const drawerBtn = document.getElementById('drawer-btn-call');
      if (btn) {
        btn.classList.remove('active-hangup');
        btn.innerHTML = `<span id="call-icon">🎙️</span> <span id="call-label">开启免提实时通话</span>`;
      }
      if (drawerBtn) {
        drawerBtn.classList.remove('btn-secondary');
        drawerBtn.classList.add('btn-amber');
        drawerBtn.innerText = "🎙️ 开启通话";
      }

      if (copilotRecognition) {
        try {
          copilotRecognition.abort();
        } catch (e) {}
      }
      setCopilotStatus('idle', '通话已挂断 · 待命就绪');
      const vadInd = document.getElementById('copilot-vad-indicator');
      if (vadInd) vadInd.innerText = "VAD 待命";
    }

    // 按键说话 (PTT 模式)
    function startPttSpeech() {
      if (isCopilotCallActive) return;
      const btn = document.getElementById('btn-ptt-talk');
      if (btn) btn.classList.add('pressing');
      if (!copilotRecognition) initSpeechRecognitionEngine();
      try {
        copilotRecognition.start();
      } catch (e) {}
    }

    function stopPttSpeech() {
      if (isCopilotCallActive) return;
      const btn = document.getElementById('btn-ptt-talk');
      if (btn) btn.classList.remove('pressing');
      if (copilotRecognition) {
        try {
          copilotRecognition.stop();
        } catch (e) {}
      }
      setTimeout(() => {
        if (copilotLastTranscript.trim()) {
          const text = copilotLastTranscript.trim();
          copilotLastTranscript = "";
          executeCopilotCommand(text, "voice");
        }
      }, 300);
    }

    // TTS 语音播报开关
    function toggleTtsMute() {
      isCopilotTtsMuted = !isCopilotTtsMuted;
      const btn = document.getElementById('btn-toggle-tts');
      if (btn) {
        if (isCopilotTtsMuted) {
          btn.innerHTML = `<span>🔇</span> <span>AI语音播报: 关</span>`;
          btn.style.color = "#94A3B8";
          if ('speechSynthesis' in window) window.speechSynthesis.cancel();
          isCopilotSpeaking = false;
          clearTimeout(ttsEchoSafetyTimeout);
        } else {
          btn.innerHTML = `<span>🔊</span> <span>AI语音播报: 开</span>`;
          btn.style.color = "#CBD5E1";
        }
      }
      showToast(isCopilotTtsMuted ? "已静音 AI 语音朗读" : "已开启 AI 语音朗读");
    }

    function speakTextTTS(text) {
      if (isCopilotTtsMuted || !('speechSynthesis' in window)) return;
      if (!text || !text.trim()) return;

      try {
        // 1. 半双工硬件抑制：在发声前立刻物理中断麦克风监听，清空缓存，阻止麦克风收录自身声音
        if (copilotRecognition) {
          try { copilotRecognition.abort(); } catch (e) {}
        }
        clearTimeout(copilotVadTimer);
        clearTimeout(ttsEchoSafetyTimeout);
        copilotLastTranscript = "";

        isCopilotSpeaking = true;
        setCopilotStatus('speaking', 'AI 助手正在语音播报 (已屏蔽麦克风)...');

        window.speechSynthesis.cancel();
        const clean = text.replace(/[*#`_\[\]()]/g, ' ').trim();
        lastSpokenText = clean;

        const utter = new SpeechSynthesisUtterance(clean);
        utter.lang = 'zh-CN';
        // 语速 1.02，音调 1.02，最贴近自然正常人的律师助理从容语调
        utter.rate = 1.02;
        utter.pitch = 1.02;

        if (selectedCopilotVoice) {
          utter.voice = selectedCopilotVoice;
        } else if (availableCopilotVoices.length > 0) {
          utter.voice = availableCopilotVoices[0];
        }

        utter.onstart = () => {
          isCopilotSpeaking = true;
          if (copilotRecognition) {
            try { copilotRecognition.abort(); } catch (e) {}
          }
        };

        const handleSpeechEnd = () => {
          clearTimeout(ttsEchoSafetyTimeout);
          ttsEchoSafetyTimeout = setTimeout(() => {
            isCopilotSpeaking = false;
            if (isCopilotCallActive) {
              setCopilotStatus('listening', '免提监听中 · 请随时口述');
              const vadInd = document.getElementById('copilot-vad-indicator');
              if (vadInd) vadInd.innerText = "🎤 麦克风已就绪";
              ensureRecognitionRunning();
            } else {
              setCopilotStatus('idle', '通话空闲 · 随时可口述案情');
            }
          }, 500);
        };

        utter.onend = handleSpeechEnd;
        utter.onerror = handleSpeechEnd;

        // 看门狗：防止浏览器偶尔丢失 utter.onend 事件导致麦克风被永久屏蔽
        const maxSpeechDurationMs = Math.max(3500, clean.length * 300);
        setTimeout(() => {
          if (isCopilotSpeaking) {
            console.log("[TTS] 看门狗保底触发，恢复麦克风");
            handleSpeechEnd();
          }
        }, maxSpeechDurationMs);

        window.speechSynthesis.speak(utter);
      } catch (e) {
        console.warn("TTS 朗读异常:", e);
        isCopilotSpeaking = false;
        if (isCopilotCallActive) ensureRecognitionRunning();
      }
    }

    // 快捷推荐语音指令触发
    function triggerQuickVoiceCommand(text) {
      executeCopilotCommand(text, "text");
    }

    function sendCopilotTextMessage() {
      const input = document.getElementById('copilot-text-input');
      if (!input) return;
      const val = input.value.trim();
      if (!val) return;
      input.value = "";
      executeCopilotCommand(val, "text");
    }

    function sendDrawerTextMessage() {
      const input = document.getElementById('drawer-text-input');
      if (!input) return;
      const val = input.value.trim();
      if (!val) return;
      input.value = "";
      executeCopilotCommand(val, "text");
    }

    // 核心中枢：指令发送、LLM 编排与跨模块自动联动
    async function executeCopilotCommand(commandText, mode = "voice") {
      if (!commandText || !commandText.trim()) return;
      const text = commandText.trim();

      // 指令防抖与回声特征拦截
      const now = Date.now();
      if (text === lastExecutedCommand && (now - lastExecutedTimestamp < 4000)) {
        console.log("[Copilot] 拦截4秒内相同高频指令:", text);
        return;
      }
      const echoKeywords = ["已为您将诉讼标的", "已更新标的金额", "核算LPR利息", "已挂载实体法条", "已在办案看板", "协同编排简报", "指令已执行完成", "我是智律 AI"];
      if (echoKeywords.some(kw => text.includes(kw))) {
        console.log("[Copilot] 拦截自身回声特征文本:", text);
        return;
      }

      lastExecutedCommand = text;
      lastExecutedTimestamp = now;

      // 1. 渲染用户消息气泡
      appendCopilotMessageUI("user", text);
      isCopilotThinking = true;
      setCopilotStatus('thinking', 'AI 正在深度思考并跨模块调度...');

      // 2. 收集当前在办案件上下文
      let caseContext = {};
      if (window.CaseContextStore) {
        caseContext = window.CaseContextStore.get();
      }

      // 获取当前活跃 Tab
      const activeNav = document.querySelector('.nav-item.active');
      const currentTab = activeNav ? activeNav.getAttribute('onclick')?.match(/switchNavTab\('([^']+)'/)?.[1] || "tab-copilot" : "tab-copilot";

      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/converse`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_input: text,
            matter_id: "default",
            current_tab: currentTab,
            case_context: caseContext,
            mode: mode
          })
        });

        if (!resp.ok) {
          const err = await resp.json();
          appendCopilotMessageUI("assistant", `执行异常: ${err.detail || "服务响应错误"}`);
          setCopilotStatus('idle', '执行失败');
          return;
        }

        const data = await resp.json();

        // 若被后端自激回声过滤器拦截或静默忽略，不渲染气泡也不发声
        if (data.status === "ignored") {
          console.log("[Copilot] 收到忽略应答，保持静默");
          setCopilotStatus(isCopilotCallActive ? 'listening' : 'idle', isCopilotCallActive ? '免提监听中...' : '通话空闲');
          return;
        }

        // 3. 渲染助手消息（含跨模块动作执行链）
        appendCopilotMessageUI("assistant", data.text_reply, data.module_actions, data.speech_reply);

        // 4. 同步更新前端案情总线 (CaseContextStore)
        if (data.context_patch && Object.keys(data.context_patch).length > 0 && window.CaseContextStore) {
          const cur = window.CaseContextStore.get();
          // 深度合并
          if (data.context_patch.amount) cur.amount = data.context_patch.amount;
          if (data.context_patch.cause) cur.cause = data.context_patch.cause;
          if (data.context_patch.plaintiff) {
            cur.plaintiff = { ...(cur.plaintiff || {}), ...data.context_patch.plaintiff };
          }
          if (data.context_patch.defendant) {
            cur.defendant = { ...(cur.defendant || {}), ...data.context_patch.defendant };
          }
          if (data.context_patch.interest_calc) {
            cur.interest_calc = { ...(cur.interest_calc || {}), ...data.context_patch.interest_calc };
          }
          if (data.context_patch.statutes && data.context_patch.statutes.length > 0) {
            cur.statutes = data.context_patch.statutes;
          }
          window.CaseContextStore.save(cur);

          // 若当前就在 01 精算页面，立即刷新精算表单与结果
          const lprP = document.getElementById('lpr-p');
          if (lprP && data.context_patch.amount) {
            lprP.value = data.context_patch.amount;
            if (typeof triggerLprCalculation === 'function') triggerLprCalculation();
          }
        }

        // 5. 更新任务看板
        if (data.tasks) {
          copilotTasksCache = data.tasks;
          renderCopilotTasksUI();
        } else {
          loadCopilotTasksUI();
        }

        // 6. 语音播报（仅在存在明确有效播报文案时发声）
        if (data.speech_reply && data.speech_reply.trim()) {
          speakTextTTS(data.speech_reply);
        } else {
          setCopilotStatus(isCopilotCallActive ? 'listening' : 'idle', isCopilotCallActive ? '免提监听中...' : '通话空闲');
        }

        if ((data.module_actions || []).length > 0) {
          showToast(`AI 调度成功！已自动联动 ${data.module_actions.length} 项功能模块`);
        }

      } catch (e) {
        console.error("Copilot 指令请求异常:", e);
        appendCopilotMessageUI("assistant", `网络或服务连接异常: ${e.message}`);
        setCopilotStatus('idle', '连接异常');
      } finally {
        isCopilotThinking = false;
        // 关键保活：无论指令执行成功、失败还是静默，如果 AI 不在播报，立即恢复麦克风录入！
        if (isCopilotCallActive && !isCopilotSpeaking) {
          setTimeout(ensureRecognitionRunning, 60);
        }
      }
    }

    // 渲染消息气泡至大屏与抽屉
    function appendCopilotMessageUI(role, content, moduleActions = [], speechReply = "") {
      const mainStream = document.getElementById('copilot-messages-stream');
      const drawerStream = document.getElementById('drawer-messages-stream');

      const timeStr = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });

      let actionsHtml = '';
      if (moduleActions && moduleActions.length > 0) {
        actionsHtml = `
          <div class="action-pipeline-chain">
            <div style="font-size: 11px; color: #94A3B8; font-weight: 600; margin-bottom: 2px;">⚡ 跨模块自动化执行链：</div>
            ${moduleActions.map(a => `
              <div class="action-step-card">
                <div style="display: flex; align-items: center; gap: 6px; min-width: 0;">
                  <span class="action-step-badge">${a.module_name || '联动模块'}</span>
                  <span style="font-size: 11.5px; color: #F1F5F9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${a.summary || a.action_name}</span>
                </div>
                <button type="button" class="action-step-btn" onclick="jumpToTaskModule('${a.module_id}', '${a.target_tab}')">
                  前往查看 ↗
                </button>
              </div>
            `).join('')}
          </div>
        `;
      }

      let replayBtnHtml = '';
      if (role === 'assistant' && speechReply) {
        replayBtnHtml = `
          <button type="button" onclick="speakTextTTS('${speechReply.replace(/'/g, "\\'")}')" style="background: transparent; border: none; color: #C58532; font-size: 11px; cursor: pointer; display: inline-flex; align-items: center; gap: 4px; padding: 2px 4px;">
            🔊 重播语音
          </button>
        `;
      }

      // 轻量格式化 Markdown
      const formattedContent = content
        .replace(/^### (.*$)/gim, '<div style="font-size: 13px; font-weight: 700; color: #F59E0B; margin: 4px 0;">$1</div>')
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color: #FFFFFF;">$1</strong>')
        .replace(/\n/g, '<br>');

      const bubbleHtml = `
        <div class="copilot-chat-bubble ${role}">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-size: 11px; font-weight: 700; color: ${role === 'user' ? '#93C5FD' : '#F59E0B'};">
              ${role === 'user' ? '👤 律师口述/指令' : '⚖️ 智律 AI 协同总控'}
            </span>
            <div style="display: flex; align-items: center; gap: 6px;">
              ${replayBtnHtml}
              <span style="font-size: 10px; color: #64748B;">${timeStr}</span>
            </div>
          </div>
          <div>${formattedContent}</div>
          ${actionsHtml}
        </div>
      `;

      if (mainStream) {
        mainStream.insertAdjacentHTML('beforeend', bubbleHtml);
        mainStream.scrollTop = mainStream.scrollHeight;
      }
      if (drawerStream) {
        drawerStream.insertAdjacentHTML('beforeend', bubbleHtml);
        drawerStream.scrollTop = drawerStream.scrollHeight;
      }
    }

    function clearCopilotMessagesUI() {
      const mainStream = document.getElementById('copilot-messages-stream');
      const drawerStream = document.getElementById('drawer-messages-stream');
      const initialAssistant = `
        <div class="copilot-chat-bubble assistant">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <span style="font-weight: 700; color: #F59E0B;">⚖️ 智律 AI 协同总控</span>
            <span style="font-size: 10.5px; color: #64748B;">系统就绪</span>
          </div>
          <div style="font-size: 12.5px; color: #E2E8F0;">
            对话记录已重置。您可以直接开启免提通话口述案情，或在下方输入指令。
          </div>
        </div>
      `;
      if (mainStream) mainStream.innerHTML = initialAssistant;
      if (drawerStream) drawerStream.innerHTML = initialAssistant;
      showToast("已清空对话记录");
    }

    function syncCaseContextToCopilotUI() {
      if (window.CaseContextStore) {
        const c = window.CaseContextStore.get();
        showToast(`已从案件总线同步：${c.title} (标的额 ¥${(c.amount || 0).toLocaleString()})`);
      }
    }

    // 智能办案任务看板 CRUD 与交互
    async function loadCopilotTasksUI() {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/tasks?matter_id=default&status=all&stage=all`);
        if (!resp.ok) return;
        const data = await resp.json();
        copilotTasksCache = data.tasks || [];
        renderCopilotTasksUI(data.counts);
      } catch (e) {
        console.warn("加载办案任务看板失败:", e);
      }
    }

    function renderCopilotTasksUI(counts) {
      const container = document.getElementById('copilot-task-list');
      if (!container) return;

      // 更新统计徽标
      const allTasks = copilotTasksCache;
      const cntAll = allTasks.length;
      const cntTodo = allTasks.filter(t => t.status === 'todo').length;
      const cntProg = allTasks.filter(t => t.status === 'in_progress').length;
      const cntDone = allTasks.filter(t => t.status === 'done').length;

      const headerCount = document.getElementById('task-header-count');
      if (headerCount) headerCount.innerText = `共 ${cntAll} 项任务`;

      const elCntAll = document.getElementById('cnt-stage-all');
      if (elCntAll) elCntAll.innerText = cntAll;
      const elCntTodo = document.getElementById('cnt-status-todo');
      if (elCntTodo) elCntTodo.innerText = cntTodo;
      const elCntProg = document.getElementById('cnt-status-in_progress');
      if (elCntProg) elCntProg.innerText = cntProg;
      const elCntDone = document.getElementById('cnt-status-done');
      if (elCntDone) elCntDone.innerText = cntDone;

      ['立案', '精算', '证据', '检索', '庭审', '执行'].forEach(stg => {
        const badge = document.getElementById(`cnt-stage-${stg}`);
        if (badge) {
          badge.innerText = allTasks.filter(t => t.stage === stg).length;
        }
      });

      // 过滤任务
      let filtered = allTasks;
      if (copilotFilterStage !== 'all') {
        filtered = filtered.filter(t => t.stage === copilotFilterStage);
      }
      if (copilotFilterStatus !== 'all') {
        filtered = filtered.filter(t => t.status === copilotFilterStatus);
      }

      if (filtered.length === 0) {
        container.innerHTML = `
          <div style="padding: 30px; text-align: center; color: var(--text-muted); font-size: 12.5px;">
            暂无符合筛选条件的办案任务。您可以随时通过语音说出“加一个任务...”自动归纳。
          </div>
        `;
        return;
      }

      container.innerHTML = filtered.map(t => { // safe-html: contains nested HTML fragment interpolations
        const isDone = t.status === 'done';
        const priorityClass = `priority-${escapeHtml(t.priority || 'medium')}`;
        const priorityLabels = { high: '紧急/高', medium: '常规/中', low: '次要/低' };
        const priorityColors = { high: '#EF4444', medium: '#F59E0B', low: '#3B82F6' };

        const moduleNames = {
          phase1_calc: '01 实务精算与核验',
          phase1_litigation: '02 立案文书流水线',
          phase2_evidence: '03 证据清洗与庭审',
          phase5_statutes: '06 法条库与图谱',
          phase4_deep_matrix: '05 深度要件推演',
          matter_vault: '07 案件空间'
        };

        const targetTabs = {
          phase1_calc: 'tab-calc',
          phase1_litigation: 'tab-litigation',
          phase2_evidence: 'tab-evidence',
          phase5_statutes: 'tab-statutes',
          phase4_deep_matrix: 'tab-deep-matrix',
          matter_vault: 'tab-graphs'
        };

        const targetTab = (t.action_payload && t.action_payload.target_tab) || targetTabs[t.linked_module] || 'tab-litigation';
        const moduleName = moduleNames[t.linked_module] || '对应模块';

        return `
          <div class="task-card-item ${escapeHtml(priorityClass)} ${escapeHtml(isDone ? 'done' : '')}" id="task-item-${escapeHtml(t.task_id)}">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
              <div style="display: flex; align-items: flex-start; gap: 8px; flex: 1; min-width: 0;">
                <input type="checkbox" aria-label="标记任务完成状态" ${escapeHtml(isDone ? 'checked' : '')} onchange="toggleTaskDone('${escapeHtml(t.task_id)}', '${escapeHtml(t.status)}')" style="margin-top: 3px; cursor: pointer;">
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); text-decoration: ${escapeHtml(isDone ? 'line-through' : 'none')}; word-break: break-all;">
                    ${escapeHtml(t.title)}
                  </div>
                  ${t.description ? `<div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 3px; line-height: 1.5;">${t.description}</div>` : ''} // safe-html: static or pre-escaped HTML fragment
                </div>
              </div>
              <div style="display: flex; align-items: center; gap: 4px;">
                <span class="badge" style="font-size: 10.5px; background: rgba(0,0,0,0.04); color: ${escapeHtml(priorityColors[t.priority] || '#F59E0B')}; border: 1px solid ${escapeHtml(priorityColors[t.priority] || '#F59E0B')}40;">
                  ${escapeHtml(priorityLabels[t.priority] || '常规')}
                </span>
                <span class="badge" style="font-size: 10.5px; background: #F1F5F9; color: var(--primary-navy);">
                  ${escapeHtml(t.stage || '立案')}
                </span>
              </div>
            </div>

            <!-- 卡片底栏：截止时限与模块直达 -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 4px; padding-top: 6px; border-top: 1px dashed var(--border-hairline); flex-wrap: wrap; gap: 6px;">
              <span style="font-size: 11px; color: var(--text-muted);">
                ⏱ 截止: <strong>${escapeHtml(t.due_date || '待定')}</strong>
              </span>
              <div style="display: flex; align-items: center; gap: 6px;">
                <button type="button" class="btn btn-secondary btn-sm" onclick="jumpToTaskModule('${escapeHtml(t.linked_module)}', '${escapeHtml(targetTab)}')" style="font-size: 11px; padding: 2px 7px;">
                  ⚡ 前往 ${escapeHtml(moduleName.split(' ')[0])}
                </button>
                <button type="button" onclick="deleteTaskUI('${escapeHtml(t.task_id)}')" style="background: transparent; border: none; color: #94A3B8; font-size: 12px; cursor: pointer; padding: 2px 4px;" title="删除任务">
                  ✕
                </button>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    async function toggleTaskDone(taskId, currentStatus) {
      const nextStatus = currentStatus === 'done' ? 'todo' : 'done';
      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/tasks/${taskId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: nextStatus })
        });
        if (resp.ok) {
          const idx = copilotTasksCache.findIndex(t => t.task_id === taskId);
          if (idx !== -1) {
            copilotTasksCache[idx].status = nextStatus;
          }
          renderCopilotTasksUI();
          showToast(nextStatus === 'done' ? "✓ 任务已标记完成！" : "已恢复为待办状态");
        }
      } catch (e) {
        console.warn("更新任务状态失败:", e);
      }
    }

    async function deleteTaskUI(taskId) {
      if (!confirm("确定要删除此项办案任务吗？")) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/tasks/${taskId}`, { method: 'DELETE' });
        if (resp.ok) {
          copilotTasksCache = copilotTasksCache.filter(t => t.task_id !== taskId);
          renderCopilotTasksUI();
          showToast("任务已删除");
        }
      } catch (e) {
        console.warn("删除任务失败:", e);
      }
    }

    function filterTaskByStage(btn, stage) {
      document.querySelectorAll('.task-stage-filter-bar .task-filter-pill').forEach(b => b.classList.remove('active'));
      if (btn) btn.classList.add('active');
      copilotFilterStage = stage;
      renderCopilotTasksUI();
    }

    function filterTaskByStatus(status) {
      copilotFilterStatus = status;
      ['all', 'todo', 'in_progress', 'done'].forEach(s => {
        const el = document.getElementById(`tab-status-${s}`);
        if (el) {
          if (s === status) {
            el.innerHTML = `<strong>${escapeHtml(el.innerText.replace(/[()0-9 ]/g, ''))}</strong>`;
            el.style.color = "var(--primary-navy)";
          } else {
            el.style.color = "var(--text-muted)";
          }
        }
      });
      renderCopilotTasksUI();
    }

    async function batchMarkAllTasksDoneUI() {
      const todoIds = copilotTasksCache.filter(t => t.status !== 'done').map(t => t.task_id);
      if (todoIds.length === 0) {
        showToast("当前没有待办任务！");
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/tasks/batch-status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_ids: todoIds, new_status: 'done' })
        });
        if (resp.ok) {
          copilotTasksCache.forEach(t => t.status = 'done');
          renderCopilotTasksUI();
          showToast(`已将 ${todoIds.length} 项任务全部标记为已完成！`);
        }
      } catch (e) {
        console.warn("批量更新状态失败:", e);
      }
    }

    function jumpToTaskModule(moduleId, targetTab) {
      const moduleTitles = {
        'tab-calc': '01 实务精算与核验',
        'tab-litigation': '02 立案文书流水线',
        'tab-evidence': '03 证据清洗与庭审',
        'tab-rag-sign': '04 类案检索与签署',
        'tab-deep-matrix': '05 深度要件与质证推演',
        'tab-statutes': '06 法条库与子母法图谱',
        'tab-graphs': '07 案件空间与核心图谱中枢'
      };

      const navIds = {
        'tab-calc': 'nav-calc',
        'tab-litigation': 'nav-litigation',
        'tab-evidence': 'nav-evidence',
        'tab-rag-sign': 'nav-rag-sign',
        'tab-deep-matrix': 'nav-deep-matrix',
        'tab-statutes': 'nav-statutes',
        'tab-graphs': 'nav-graphs'
      };

      const title = moduleTitles[targetTab] || '工作台模块';
      const btnElem = document.getElementById(navIds[targetTab]);
      if (btnElem) {
        switchNavTab(targetTab, title, btnElem);
        showToast(`已为您无缝切入 ${title}！`);
      }
    }

    // 全局悬浮 AI 语音副驾抽屉开关
    function toggleGlobalVoiceDrawer() {
      const drawer = document.getElementById('global-voice-drawer');
      const orb = document.getElementById('global-voice-orb');
      if (!drawer) return;
      drawer.classList.toggle('open');
      if (drawer.classList.contains('open')) {
        const input = document.getElementById('drawer-text-input');
        if (input) setTimeout(() => input.focus(), 280);
      }
    }

    // 手动新建任务模态框
    function openCreateTaskModal() {
      const modal = document.getElementById('modal-copilot-task');
      if (!modal) return;
      document.getElementById('task-modal-id').value = "";
      document.getElementById('task-form-title').value = "";
      document.getElementById('task-form-desc').value = "";
      document.getElementById('task-form-due').value = "明日 18:00";
      modal.classList.add('show');
    }

    function closeCreateTaskModal() {
      const modal = document.getElementById('modal-copilot-task');
      if (modal) modal.classList.remove('show');
    }

    function handleTaskModalBackdropClick(e) {
      if (e.target.id === 'modal-copilot-task') {
        closeCreateTaskModal();
      }
    }

    async function submitSaveTaskModal() {
      const title = document.getElementById('task-form-title').value.trim();
      if (!title) {
        showToast("请输入任务名称！");
        return;
      }
      const stage = document.getElementById('task-form-stage').value;
      const priority = document.getElementById('task-form-priority').value;
      const due = document.getElementById('task-form-due').value.trim() || "待定";
      const mod = document.getElementById('task-form-module').value;
      const desc = document.getElementById('task-form-desc').value.trim();

      try {
        const resp = await api.request(`${API_BASE}/api/v1/copilot/tasks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            stage: stage,
            priority: priority,
            due_date: due,
            linked_module: mod,
            description: desc,
            matter_id: "default"
          })
        });

        if (resp.ok) {
          const res = await resp.json();
          copilotTasksCache.unshift(res.task);
          renderCopilotTasksUI();
          closeCreateTaskModal();
          showToast("办案任务创建成功！");
        }
      } catch (e) {
        console.warn("保存任务异常:", e);
      }
    }

    // =========================================================================
    // 司法级全格式离线转码中枢 (Filee 协同)

export {
  initCopilotWorkspace,
  populateVoicesList,
  onVoiceSelectionChanged,
  testCurrentVoice,
  initCopilotCanvas,
  resizeCopilotCanvas,
  renderVoiceVisualizerLoop,
  setCopilotStatus,
  ensureRecognitionRunning,
  initSpeechRecognitionEngine,
  toggleVoiceCall,
  startCopilotCall,
  stopCopilotCall,
  startPttSpeech,
  stopPttSpeech,
  toggleTtsMute,
  speakTextTTS,
  triggerQuickVoiceCommand,
  sendCopilotTextMessage,
  sendDrawerTextMessage,
  executeCopilotCommand,
  appendCopilotMessageUI,
  clearCopilotMessagesUI,
  syncCaseContextToCopilotUI,
  loadCopilotTasksUI,
  renderCopilotTasksUI,
  toggleTaskDone,
  deleteTaskUI,
  filterTaskByStage,
  filterTaskByStatus,
  batchMarkAllTasksDoneUI,
  jumpToTaskModule,
  toggleGlobalVoiceDrawer,
  openCreateTaskModal,
  closeCreateTaskModal,
  handleTaskModalBackdropClick,
  submitSaveTaskModal,
};

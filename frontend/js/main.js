/**
 * LawFlow Main Entry (main.js)
 * 组装与挂载 01~08 模块、初始化模态框、事件绑定与全局兼容导出
 */
import { api, ApiError, API_BASE, getApiToken, withDownloadToken, escapeHtml } from './api.js';
import { showToast } from './ui/toast.js';
import { initModals, setupModalFocusManagement } from './modules/modals.js';
import * as CalcModule from './modules/01_calc.js';
import * as LitigationModule from './modules/02_litigation.js';
import * as EvidenceModule from './modules/03_evidence.js';
import * as AppealSigningModule from './modules/04_appeal_signing.js';
import * as EnforcementModule from './modules/05_enforcement.js';
import * as CitationGuardModule from './modules/06_citation_guard.js';
import * as MattersModule from './modules/07_matters.js';
import * as CopilotModule from './modules/08_copilot.js';
import * as SettingsModule from './modules/settings.js';
import * as ConverterModule from './modules/converter.js';

// 将所有模块导出的函数绑定到 window，保持原有 HTML onclick 属性兼容
const allModules = [
  CalcModule,
  LitigationModule,
  EvidenceModule,
  AppealSigningModule,
  EnforcementModule,
  CitationGuardModule,
  MattersModule,
  CopilotModule,
  SettingsModule,
  ConverterModule,
];

for (const mod of allModules) {
  for (const [key, val] of Object.entries(mod)) {
    if (typeof window !== 'undefined') {
      window[key] = val;
    }
  }
}
if (typeof window !== 'undefined') {
  window.navigateToPipelineStep = navigateToPipelineStep;
  window.toggleStepperView = toggleStepperView;
  window.updatePipelineStepperActive = updatePipelineStepperActive;
  window.toggleSidebar = toggleSidebar;
  window.switchNavTab = switchNavTab;
  window.initDate = initDate;
  window.copyToClipboard = copyToClipboard;
  window.copyBadgeText = copyBadgeText;
  window.copyElementText = copyElementText;
  window.copyLegalStatement = copyLegalStatement;
  window.mountAllTabs = mountAllTabs;
}

// 通用工具与导航函数
    // S-01：从服务端注入的 meta 读取同源 API Token；统一包装 fetch 与下载链接
    const LAWFLOW_TOKEN = (document.querySelector('meta[name="lawflow-token"]') || {}).content || "";
    const LAWFLOW_DISCLAIMER = "本输出由软件自动生成，仅供执业律师参考，不构成法律意见，须经律师审核后使用。";
    const _nativeFetch = window.fetch.bind(window);

    function lfDisclaimerHtml() {
      return `<div class="lf-disclaimer-line">${LAWFLOW_DISCLAIMER}</div>`;
    }

    /** 在结果容器底部追加免责声明小字（幂等） */
    function appendResultDisclaimer(el) {
      if (!el) return;
      if (el.querySelector && el.querySelector('.lf-disclaimer-line')) return;
      const wrap = document.createElement('div');
      wrap.className = 'lf-disclaimer-line';
      wrap.textContent = LAWFLOW_DISCLAIMER;
      el.appendChild(wrap);
    }

    function initResultCardDisclaimers() {
      document.querySelectorAll('.docket-receipt-paper, .surface-card').forEach(appendResultDisclaimer);
    }
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initResultCardDisclaimers);
    } else {
      initResultCardDisclaimers();
    }



    window.fetch = function lawflowFetch(input, init) {
      const opts = init ? Object.assign({}, init) : {};
      const headers = new Headers(opts.headers || (typeof input !== 'string' && input && input.headers) || {});
      let url = typeof input === 'string' ? input : (input && input.url) ? input.url : '';
      const isApi = (typeof url === 'string') && (url.indexOf('/api/') !== -1 || (API_BASE === '' && url.charAt(0) === '/' && url.indexOf('/api/') === 0) || (API_BASE && url.indexOf(API_BASE + '/api/') === 0) || (url.indexOf('/api/') >= 0));
      // 同源 /api/ 请求自动附加鉴权头
      if (LAWFLOW_TOKEN && typeof url === 'string' && url.indexOf('/api/') !== -1) {
        if (!headers.has('X-LawFlow-Token')) {
          headers.set('X-LawFlow-Token', LAWFLOW_TOKEN);
        }
      }
      opts.headers = headers;
      return _nativeFetch(input, opts);
    };

    // =========================================================================
    // 0. 全局导航切换与时间初始化
    // =========================================================================
    function toggleSidebar() {
      const sidebar = document.querySelector('.sidebar');
      if (sidebar) {
        sidebar.classList.toggle('collapsed');
      }
    }

    function switchNavTab(tabId, title, btnElem) {
      document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.workspace-tab').forEach(t => t.classList.remove('active'));
      
      btnElem.classList.add('active');
      document.getElementById(tabId).classList.add('active');
      
      const badgeText = title.split(' ')[0] || "01";
      document.getElementById('current-module-badge').innerText = '模块 ' + badgeText;
      document.getElementById('current-module-title').innerText = title.substring(3).trim();
      updatePipelineStepperActive(tabId);

      if (tabId === 'tab-copilot') {
        if (typeof loadCopilotTasksUI === 'function') loadCopilotTasksUI();
        if (typeof resizeCopilotCanvas === 'function') setTimeout(resizeCopilotCanvas, 50);
      }
    }

    // 更新顶部日期
    function initDate() {
      const d = new Date();
      const dateStr = `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
      const dateEl = document.getElementById('current-date-text');
      if (dateEl) dateEl.innerText = dateStr;
    }



    function copyToClipboard(text, successMsg) {
      if (!text) return;
      navigator.clipboard.writeText(text).then(() => {
        showToast(successMsg || "已成功复制到剪贴板");
      }).catch(() => {
        // 兼容降级
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        ta.remove();
        showToast(successMsg || "已成功复制到剪贴板");
      });
    }

    function copyBadgeText(badgeId, msg) {
      const elem = document.getElementById(badgeId);
      if (elem) {
        const text = elem.innerText.trim();
        copyToClipboard(text, msg);
      }
    }

    function copyElementText(elId, msg) {
      const elem = document.getElementById(elId);
      if (elem) {
        copyToClipboard(elem.innerText.trim(), msg);
      }
    }

    function copyLegalStatement() {
      copyElementText('legal-statement-text', '已复制公文段落');
    }

    // =========================================================================
    // 1. 模块 01：高频要素即时速查条 (人民币大写实时转 + 主体资格秒查)


export function mountAllTabs() {
  if (typeof CalcModule.renderTabCalc === 'function') CalcModule.renderTabCalc();
  if (typeof LitigationModule.renderTabLitigation === 'function') LitigationModule.renderTabLitigation();
  if (typeof EvidenceModule.renderTabEvidence === 'function') EvidenceModule.renderTabEvidence();
  if (typeof AppealSigningModule.renderTabAppealSigning === 'function') AppealSigningModule.renderTabAppealSigning();
  if (typeof EnforcementModule.renderTabEnforcement === 'function') EnforcementModule.renderTabEnforcement();
  if (typeof CitationGuardModule.renderTabCitationGuard === 'function') CitationGuardModule.renderTabCitationGuard();
  if (typeof MattersModule.renderTabMatters === 'function') MattersModule.renderTabMatters();
  if (typeof CopilotModule.renderTabCopilot === 'function') CopilotModule.renderTabCopilot();
}

// DOMContentLoaded 初始化
window.addEventListener('DOMContentLoaded', () => {
  // 1. 挂载所有模块 Tab 视图与模态框
  mountAllTabs();
  initModals();
  setupModalFocusManagement();

  // 2. 初始化全局时钟与拖拽
  if (typeof initDate === 'function') initDate();
  if (typeof setupVaultDnD === 'function') setupVaultDnD();
  if (typeof initConverterDropZone === 'function') initConverterDropZone();
  if (typeof initResultCardDisclaimers === 'function') initResultCardDisclaimers();

  // 3. 初始化在办案件状态机与案件列表
  // Restore batch-16 startup calls dropped in the batch-17 split (engine status, case bar, vault, RAG, converter status)
  if (typeof renderGlobalCaseBar === 'function') renderGlobalCaseBar();
  if (typeof updateTabContextDisplays === 'function') updateTabContextDisplays();
  if (typeof initMatterVault === 'function') initMatterVault();
  if (typeof runDualRAGSearch === 'function') runDualRAGSearch();
  if (typeof fetchEngineHealth === 'function') fetchEngineHealth();
  if (typeof fetchConverterStatus === 'function') fetchConverterStatus();
  if (typeof fetchSystemHealth === 'function') fetchSystemHealth();
  if (typeof runDeepMatrixAnalyze === 'function') runDeepMatrixAnalyze();

  if (window.CaseContextStore && typeof window.CaseContextStore.init === 'function') {
    window.CaseContextStore.init();
  }
  if (typeof loadVaultMatters === 'function') loadVaultMatters();

  // 4. 初始化法典库与副驾中枢
  if (typeof reloadStatutesCorpus === 'function') reloadStatutesCorpus();
  if (typeof executeStatuteSearch === 'function') executeStatuteSearch();
  if (typeof initCopilotWorkspace === 'function') initCopilotWorkspace();
  if (typeof onPlaybookChange === 'function') onPlaybookChange();
});

    function updatePipelineStepperActive(tabId) {
      const stepMap = {
        'tab-graphs': 1,
        'tab-calc': 2,
        'tab-evidence': 3,
        'tab-litigation': 4,
        'tab-deep-matrix': 5
      };
      const activeStep = stepMap[tabId] || 0;
      for (let i = 1; i <= 5; i++) {
        const node = document.getElementById(`step-node-${i}`);
        if (node) {
          node.classList.toggle('active-step', i === activeStep);
        }
      }
    }

    function navigateToPipelineStep(stepIndex) {
      if (stepIndex === 1) {
        const btn = document.getElementById('nav-graphs');
        if (btn) switchNavTab('tab-graphs', '07 案件空间与核心图谱中枢', btn);
        showToast("阶段 1：案件空间管理与利冲排查");
      } else if (stepIndex === 2) {
        const btn = document.getElementById('nav-calc');
        if (btn) switchNavTab('tab-calc', '01 实务精算与核验', btn);
        showToast("阶段 2：诉讼本息与受理费精算");
      } else if (stepIndex === 3) {
        const btn = document.getElementById('nav-evidence');
        if (btn) switchNavTab('tab-evidence', '03 证据清洗与庭审', btn);
        showToast("阶段 3：证据合卷与绝对页码目录");
      } else if (stepIndex === 4) {
        const btn = document.getElementById('nav-litigation');
        if (btn) switchNavTab('tab-litigation', '02 立案文书流水线', btn);
        showToast("阶段 4：移动微法院标准立案四件套生成");
      } else if (stepIndex === 5) {
        const btn = document.getElementById('nav-deep-matrix');
        if (btn) switchNavTab('tab-deep-matrix', '05 要件推演与执行破局', btn);
        showToast("阶段 5：庭审对抗提纲与七维要件推演");
      }
    }

    function toggleStepperView() {
      const track = document.getElementById('stepper-steps-track');
      const btn = document.getElementById('btn-toggle-stepper');
      if (!track || !btn) return;
      const isHidden = track.style.display === 'none';
      track.style.display = isHidden ? 'flex' : 'none';
      btn.innerText = isHidden ? '展开向导 ▾' : '收起向导 ▴';
    }

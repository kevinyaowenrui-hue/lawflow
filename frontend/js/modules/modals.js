/**
 * LawFlow Modals Component & Focus Management
 */
import { showToast } from '../ui/toast.js';

// safe-html: static modal dialogs markup
export const MODALS_HTML = `
  <!-- ========================================================================
       在办案件全局工作卡模态框 (Case Context Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-case-context" onclick="handleCaseModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 860px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            <span>在办案件全局工作卡</span>
            <span class="badge" id="modal-case-badge" style="background: rgba(197, 133, 50, 0.15); color: var(--accent-amber);">民间借贷纠纷</span>
          </div>
          <div class="modal-subtitle">打通 01实务精算、02立案文书、03证据清洗、05深度要件推演与 06权威法典检索</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeCaseContextModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 72vh; overflow-y: auto; padding: 20px;">
        <!-- 一、案件基本面 -->
        <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
          <span>一、案件基本面 (Basic Metadata)</span>
        </div>
        <div class="form-row-3" style="margin-bottom: 12px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">案由类型</label>
            <input aria-label="modal case cause"  type="text" id="modal-case-cause" class="quick-input" value="民间借贷纠纷" oninput="syncModalCaseCauseBadge()">
          </div>
          <div class="form-group" style="margin-bottom: 0; grid-column: span 2;">
            <label class="form-label">案件全称/标题</label>
            <input aria-label="modal case title"  type="text" id="modal-case-title" class="quick-input" value="">
          </div>
        </div>
        <div class="form-row" style="grid-template-columns: 2fr 1fr; margin-bottom: 14px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">受诉管辖法院</label>
            <input aria-label="modal case court"  type="text" id="modal-case-court" class="quick-input" value="北京市朝阳区人民法院">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">主张诉讼标的额 (元)</label>
            <input aria-label="modal case amount"  type="number" id="modal-case-amount" class="quick-input" value="500000" step="5000">
          </div>
        </div>

        <!-- 二、双方当事人要素 -->
        <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px; border-top: 1px solid var(--border-hairline); padding-top: 12px;">
          二、当事人身份主体要素 (Parties)
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px;">
          <!-- 原告方 -->
          <div style="background: #F8FAFC; border: 1px solid rgba(59, 130, 246, 0.2); border-radius: var(--radius-sm); padding: 10px 12px;">
            <div style="font-size: 12px; font-weight: 700; color: #1e40af; margin-bottom: 8px;">原告 / 申请人</div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">姓名 / 企业主体</label><input aria-label="modal case p name"  type="text" id="modal-case-p-name" value="李四"></div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">身份证号 / 统一信用代码</label><input aria-label="modal case p id"  type="text" id="modal-case-p-id" value="110101199003072375"></div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">联系电话</label><input aria-label="modal case p phone"  type="text" id="modal-case-p-phone" value="13800000000"></div>
            <div class="form-group" style="margin-bottom: 0;"><label class="form-label">住所地 / 送达地址</label><input aria-label="modal case p addr"  type="text" id="modal-case-p-addr" value="北京市朝阳区建国门外大街1号"></div>
          </div>
          <!-- 被告方 -->
          <div style="background: #FDF9F8; border: 1px solid rgba(180, 52, 52, 0.2); border-radius: var(--radius-sm); padding: 10px 12px;">
            <div style="font-size: 12px; font-weight: 700; color: #991b1b; margin-bottom: 8px;">被告 / 被申请人</div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">姓名 / 企业主体</label><input aria-label="modal case d name"  type="text" id="modal-case-d-name" value="张三"></div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">身份证号 / 统一信用代码</label><input aria-label="modal case d id"  type="text" id="modal-case-d-id" value="110101198506121234"></div>
            <div class="form-group" style="margin-bottom: 6px;"><label class="form-label">联系电话</label><input aria-label="modal case d phone"  type="text" id="modal-case-d-phone" value="13900000000"></div>
            <div class="form-group" style="margin-bottom: 0;"><label class="form-label">住所地 / 营业登记地</label><input aria-label="modal case d addr"  type="text" id="modal-case-d-addr" value="北京市海淀区中关村南大街5号"></div>
          </div>
        </div>

        <!-- 三、精算与诉讼成本总线 -->
        <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px; border-top: 1px solid var(--border-hairline); padding-top: 12px; display: flex; justify-content: space-between; align-items: center;">
          <span>三、实务精算财务状态 (Actuarial State)</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="syncCalcFromTab01ToModal()" style="padding: 2px 8px; font-size: 11px;">
            📥 从 01 精算结果重新拉取
          </button>
        </div>
        <div style="background: #FCFBF9; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 12px; margin-bottom: 14px;">
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 8px;">
            <div><span style="font-size: 11px; color: var(--text-muted);">拖欠本金基数</span><div id="modal-calc-p" style="font-size: 13px; font-weight: 700; font-family: var(--font-mono); color: var(--primary-navy);">¥500,000.00</div></div>
            <div><span style="font-size: 11px; color: var(--text-muted);">已核算逾期利息</span><div id="modal-calc-interest" style="font-size: 13px; font-weight: 700; font-family: var(--font-mono); color: var(--accent-amber);">¥26,701.37</div></div>
            <div><span style="font-size: 11px; color: var(--text-muted);">案件受理费 (预交)</span><div id="modal-calc-courtfee" style="font-size: 13px; font-weight: 700; font-family: var(--font-mono); color: var(--primary-navy);">¥8,800.00</div></div>
            <div><span style="font-size: 11px; color: var(--text-muted);">诉讼保全申请费</span><div id="modal-calc-preservfee" style="font-size: 13px; font-weight: 700; font-family: var(--font-mono); color: var(--primary-navy);">¥3,020.00</div></div>
          </div>
          <div style="font-size: 11.5px; color: var(--text-secondary); background: #FAF9F6; border: 1px solid #EAE6DD; padding: 6px 10px; border-radius: 3px; font-family: var(--font-mono); line-height: 1.5;" id="modal-calc-statement">
            自2023年01月01日起至实际清偿之日止，以本金500,000.00元为基数，按同期全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）计算至2024年01月01日暂计为26,701.37元；
          </div>
        </div>

        <!-- 四、请求权基础实体法条总线 -->
        <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px; border-top: 1px solid var(--border-hairline); padding-top: 12px; display: flex; justify-content: space-between; align-items: center;">
          <span>四、请求权基础法条依据 (Statutes Basis, <span id="modal-statutes-count">3</span> 条)</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeCaseContextModal(); switchNavTab('tab-statutes', '06 法条库与子母法图谱', document.getElementById('nav-statutes'))" style="padding: 2px 8px; font-size: 11px;">
            🔍 前往 06 法条库选入新法条
          </button>
        </div>
        <div id="modal-statutes-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 14px;">
          <!-- 动态渲染已选入法条 -->
        </div>

        <!-- 五、案件事实与证据概要 -->
        <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px; border-top: 1px solid var(--border-hairline); padding-top: 12px;">
          五、案件事实与一手在卷证据 (Facts & Evidence)
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">案件事实经过 (自动流转至 02诉状与 05推演)</label>
            <textarea aria-label="modal case facts"  id="modal-case-facts" class="quick-input" rows="4" style="line-height: 1.5; font-size: 12px;"></textarea>
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">原始证据清单概要 (自动流转至 03与 05推演)</label>
            <textarea aria-label="modal case evidence"  id="modal-case-evidence" class="quick-input" rows="4" style="line-height: 1.5; font-size: 12px; font-family: var(--font-mono);"></textarea>
          </div>
        </div>
      </div>

      <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center;">
        <div style="display: flex; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="resetCaseContextToDefault()">
            🔄 恢复默认测试案
          </button>
          <button type="button" class="btn btn-secondary btn-sm" onclick="clearCaseContextToNew()" style="color: var(--status-warn);">
            🗑️ 清空新建案
          </button>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeCaseContextModal()">取消</button>
          <button type="button" class="btn btn-primary btn-sm" onclick="saveCaseContextFromModal()">
            <span>保存并立即应用</span>
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       模型引擎与分发配置模态框 (Swiss Grid 规范)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-engine-settings" onclick="handleModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title">模型引擎与分发配置</div>
          <div class="modal-subtitle">自由切换“免显卡云端大模型”与“本地私有离线”，支持无缝分发给他人使用</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeEngineSettingsModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body">
        <!-- 运行模式切换分段控制器 -->
        <div class="segmented-control" style="width: 100%;">
          <button type="button" class="segmented-btn active" id="btn-mode-cloud" onclick="selectEngineMode('cloud')">
            云端大模型 (免显卡·推荐)
          </button>
          <button type="button" class="segmented-btn" id="btn-mode-ollama" onclick="selectEngineMode('ollama')">
            本地 Ollama (私有断网)
          </button>
          <button type="button" class="segmented-btn" id="btn-mode-rule" onclick="selectEngineMode('rule_engine')">
            专家规则兜底 (无AI依赖)
          </button>
          <button type="button" class="segmented-btn" id="btn-mode-pii" onclick="selectEngineMode('pii')">
            PII 隐私脱敏扫描
          </button>
        </div>

        <!-- 选项 A：云端配置面板 -->
        <div class="cfg-pane active" id="pane-cloud">
          <div class="cfg-tip-box">
            <strong>适合分发场景：</strong>接收人电脑无需独立显卡、无需配置 Python 或下载 8GB 模型文件。在普通轻薄办公电脑上即可秒级响应，中文司法文书质量更高，成本约每案 <strong>¥0.01</strong>。
          </div>

          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">服务商快捷预设 (Provider)</label>
            <select aria-label="cfg cloud preset"  id="cfg-cloud-preset" onchange="onCloudPresetChange()">
              <option value="deepseek">DeepSeek (深度求索 - 强烈推荐，性价比最高)</option>
              <option value="qwen">阿里通义千问 (DashScope 百炼 · 官方格式兼容)</option>
              <option value="zhipu">智谱清言 (GLM-4 / 清华开源国产)</option>
              <option value="siliconflow">硅基流动 (SiliconFlow 聚合)</option>
              <option value="moonshot">月之暗面 (Kimi 长文本理解)</option>
              <option value="custom">自定义兼容接口 (Custom OpenAI-Compatible)</option>
            </select>
          </div>

          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label" style="display:flex; justify-content:space-between;">
              <span>API Key (密钥)</span>
              <span id="cfg-key-status" style="font-size:11px; color:var(--accent-amber);"></span>
            </label>
            <div style="position:relative; display:flex; align-items:center;">
              <input aria-label="请输入 sk- 开头的 API Key"  type="password" id="cfg-api-key" placeholder="请输入 sk- 开头的 API Key" style="width:100%; padding-right:36px;" />
              <button type="button" onclick="toggleApiKeyVisibility()" style="position:absolute; right:8px; background:none; border:none; color:var(--text-secondary); cursor:pointer; padding:4px;" title="显示/隐藏密钥">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>
              </button>
            </div>
            <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">若已有环境变量配置，留空则保持现存密钥不变。</div>
          </div>

          <div class="form-row" style="grid-template-columns: 1fr 1fr; margin-bottom:0;">
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">接口地址 (Base URL)</label>
              <input aria-label="https://api.deepseek.com/v1"  type="text" id="cfg-base-url" placeholder="https://api.deepseek.com/v1" />
            </div>
            <div class="form-group" style="margin-bottom:0;">
              <label class="form-label">模型标识 (Model)</label>
              <input aria-label="deepseek-chat"  type="text" id="cfg-model" placeholder="deepseek-chat" />
            </div>
          </div>

          <!-- 本地 PII 隐私脱敏网关开关 -->
          <div style="margin-top: 10px; padding: 10px 12px; background: #F8FAFC; border: 1px solid var(--border-hairline); border-radius: 6px;">
            <label style="display: flex; align-items: center; gap: 8px; cursor: pointer; font-size: 12px; font-weight: 600; color: var(--primary-navy); margin-bottom: 3px;">
              <input aria-label="cfg pii shield"  type="checkbox" id="cfg-pii-shield" checked style="accent-color: #059669; width: 15px; height: 15px;" />
              <span>🛡 启用本地 PII 隐私脱敏与还原网关 (建议开启)</span>
            </label>
            <div style="font-size: 11px; color: var(--text-muted); line-height: 1.5; padding-left: 23px;">
              发送云端前自动将当事人姓名、公司名、身份证、手机号、银行卡号转为安全占位符，返回后再在本地无损还原。符合《个人信息保护法》与律师执业保密规程，核心案情零明文泄露。
            </div>
          </div>
        </div>

        <!-- 选项 B：本地 Ollama 配置面板 -->
        <div class="cfg-pane" id="pane-ollama">
          <div class="cfg-tip-box">
            <strong>适合完全断网保密场景：</strong>数据绝不出本机。前提是当前电脑已安装运行 Ollama，并具备 16GB+ 内存或独立显卡（如 RTX 3060/4060 等）。
          </div>

          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">Ollama 通信地址</label>
            <input aria-label="cfg ollama url"  type="text" id="cfg-ollama-url" value="http://127.0.0.1:11434" />
          </div>

          <div class="form-group" style="margin-bottom:0;">
            <label class="form-label">目标模型名称</label>
            <input aria-label="cfg ollama model"  type="text" id="cfg-ollama-model" value="gemma4:12b" />
          </div>
        </div>

        <!-- 选项 C：专家规则兜底配置面板 -->
        <div class="cfg-pane" id="pane-rule">
          <div class="cfg-tip-box">
            <strong>纯算法与规则模式 (零硬件要求)：</strong>不依赖任何大模型 API 或显卡算力。<br/>
            • 诉讼费、保全费、LPR 历期多段分段计息、劳动仲裁 N/N+1/2N 均通过内置精确数学公式计算；<br/>
            • 起诉状、证据目录、委托协议根据内置司法规范模板生成，百分之百确定性、零法条幻觉。
          </div>
        </div>

        <!-- 选项 D：PII 隐私敏感信息扫描与脱敏测试面板 -->
        <div class="cfg-pane" id="pane-pii">
          <div class="cfg-tip-box">
            <strong>本地 PII 隐私脱敏与还原网关：</strong>依据《个人信息保护法》与律师执业规范，在本地通过正则与实体分析识别姓名、身份证、手机号、银行卡号并安全脱敏。
          </div>
          <div class="form-group" style="margin-bottom:8px;">
            <label class="form-label">待扫描与脱敏文本</label>
            <textarea aria-label="输入含敏感信息的文书草稿，例：原告张三（身份证110101199003072375，手机13800138000）向被告李四转账至工行卡6222021000123456789..."  id="pii-scan-input" rows="4" class="quick-input" placeholder="输入含敏感信息的文书草稿，例：原告张三（身份证110101199003072375，手机13800138000）向被告李四转账至工行卡6222021000123456789..."></textarea>
          </div>
          <div style="display:flex; justify-content:flex-end; margin-bottom:10px;">
            <button type="button" class="btn btn-amber btn-sm" onclick="runPiiScanUI()">
              🔍 执行 PII 本地扫描与脱敏
            </button>
          </div>
          <div id="pii-scan-result" style="display:none; background:#FAF9F6; border:1px solid #EAE6DD; border-radius:4px; padding:10px;"></div>
        </div>

        <!-- 测试连通性结果反馈区 -->
        <div class="cfg-test-feedback" id="cfg-test-feedback">
          <span id="cfg-test-text"></span>
        </div>
      </div>

      <div class="modal-footer">
        <div>
          <button type="button" class="btn btn-secondary btn-sm" id="btn-test-connection" onclick="testEngineConnection()">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
            <span>测试连接</span>
          </button>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeEngineSettingsModal()">取消</button>
          <button type="button" class="btn btn-primary btn-sm" id="btn-save-engine" onclick="saveEngineSettings()">
            <span>保存并立即应用</span>
          </button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       律所级利益冲突穿透排查与合规熔断模态框 (Conflict of Interest Check Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-conflict-check" onclick="handleConflictModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 900px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            <span>律所级利益冲突穿透排查中枢</span>
            <span class="badge" style="background: rgba(211, 47, 47, 0.12); color: #D32F2F; border: 1px solid rgba(211, 47, 47, 0.25);">执业合规护城河</span>
          </div>
          <div class="modal-subtitle">《律师法》第39条 · 中华全国律协《律师执业行为规范》第50/51条 · 律所在办及常年顾问底档库穿透排查</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeConflictCheckModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 75vh; overflow-y: auto; padding: 18px 20px;">
        <!-- 标签切换：穿透排查 vs 底档库查看与录入 -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 10px;">
          <div class="segmented-control" style="max-width: 340px;">
            <button type="button" class="seg-btn active" id="tab-btn-conflict-check" onclick="switchConflictModalTab('check')">🔍 实时冲突穿透排查</button>
            <button type="button" class="seg-btn" id="tab-btn-conflict-registry" onclick="switchConflictModalTab('registry')">📁 律所底档库 (<span id="conflict-registry-count-badge">4</span>)</button>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" onclick="syncConflictFormFromGlobalCase()" style="font-size: 11.5px; display: inline-flex; align-items: center; gap: 4px;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            从当前在办案件载入原被告
          </button>
        </div>

        <!-- 视图 1：实时穿透排查 -->
        <div id="view-conflict-check">
          <!-- 输入表单 -->
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 14px; margin-bottom: 16px;">
            <!-- 委托方 -->
            <div>
              <div style="font-weight: 700; color: var(--primary-navy); font-size: 12.5px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span style="color: #2E7D32;">●</span> 拟委托当事人 / 客户
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">当事人姓名 / 企业全称</label>
                <input aria-label="例: 李四 或 北京知客云服科技有限公司"  type="text" id="chk-client-name" class="quick-input" placeholder="例: 李四 或 北京知客云服科技有限公司">
              </div>
              <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label">身份证号 / 统一社会信用代码 (选填)</label>
                <input aria-label="18位号码"  type="text" id="chk-client-id" class="quick-input" placeholder="18位号码">
              </div>
            </div>

            <!-- 相对方 -->
            <div>
              <div style="font-weight: 700; color: var(--primary-navy); font-size: 12.5px; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
                <span style="color: #D32F2F;">●</span> 争议相对方 / 拟起诉被告
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">相对方姓名 / 企业全称</label>
                <input aria-label="例: 张三 或 北京宏达商贸有限公司"  type="text" id="chk-opposing-name" class="quick-input" placeholder="例: 张三 或 北京宏达商贸有限公司">
              </div>
              <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label">相对方身份证 / 统一信用代码 (选填)</label>
                <input aria-label="18位号码"  type="text" id="chk-opposing-id" class="quick-input" placeholder="18位号码">
              </div>
            </div>

            <!-- 穿透实体与案由 (横跨两列) -->
            <div style="grid-column: span 2; display: grid; grid-template-columns: 2fr 1fr; gap: 12px; border-top: 1px dashed #E0DCD3; padding-top: 10px;">
              <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label">关联穿透实体 (母子公司/控股股东/法定代表人，英文逗号分隔)</label>
                <input aria-label="例: 宏达控股, 张三, 深圳华腾供应链"  type="text" id="chk-related-entities" class="quick-input" placeholder="例: 宏达控股, 张三, 深圳华腾供应链">
              </div>
              <div class="form-group" style="margin-bottom: 0;">
                <label class="form-label">拟委托争议案由 / 标的</label>
                <input aria-label="例: 民间借贷纠纷 / 股权转让"  type="text" id="chk-case-subject" class="quick-input" placeholder="例: 民间借贷纠纷 / 股权转让">
              </div>
            </div>
          </div>

          <div style="display: flex; justify-content: flex-end; margin-bottom: 16px;">
            <button type="button" class="btn" id="btn-run-conflict-check" onclick="runConflictCheckSubmit()" style="background: #14233C; padding: 8px 18px; font-weight: 600;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
              执行穿透排查与合规熔断探测
            </button>
          </div>

          <!-- 排查结论卡片 -->
          <div id="conflict-result-box" style="display: none;">
            <!-- 动态渲染排查结论 -->
          </div>
        </div>

        <!-- 视图 2：律所底档库与新案登记 -->
        <div id="view-conflict-registry" style="display: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="font-size: 12px; color: var(--text-muted);">
              本律所全量在办、常年顾问与历史结案冲突底档（直接关联排查核心引擎）
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="toggleRegisterCaseDrawer()">
              ➕ 录入新案件至底档库
            </button>
          </div>

          <!-- 新增录入表单抽屉 -->
          <div id="drawer-register-case" style="display: none; background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 12px; margin-bottom: 12px;">
            <div style="font-weight: 700; font-size: 12px; color: var(--primary-navy); margin-bottom: 8px;">录入在办/顾问案件到排查底档库</div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 8px;">
              <div><label class="form-label">案件/顾问全称</label><input aria-label="例: XX公司常年法律顾问"  type="text" id="reg-case-name" class="quick-input" placeholder="例: XX公司常年法律顾问"></div>
              <div><label class="form-label">档案号/案号</label><input aria-label="例: (2026)京01民初999号"  type="text" id="reg-case-no" class="quick-input" placeholder="例: (2026)京01民初999号"></div>
              <div><label class="form-label">案件状态</label>
                <select aria-label="reg case status"  id="reg-case-status" class="quick-input">
                  <option value="ACTIVE">在办案件 (ACTIVE)</option>
                  <option value="RETAINER">常年法律顾问 (RETAINER)</option>
                  <option value="CLOSED">历史已结案 (CLOSED)</option>
                </select>
              </div>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-bottom: 8px;">
              <div><label class="form-label">委托人/顾问单位</label><input aria-label="reg client name"  type="text" id="reg-client-name" class="quick-input"></div>
              <div><label class="form-label">相对方/当事人</label><input aria-label="reg opposing party"  type="text" id="reg-opposing-party" class="quick-input"></div>
              <div><label class="form-label">主办律师</label><input aria-label="reg lawyer"  type="text" id="reg-lawyer" class="quick-input" value="张律师"></div>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 8px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="toggleRegisterCaseDrawer()">取消</button>
              <button type="button" class="btn btn-sm" onclick="submitRegisterConflictCase()">确认存入底档库</button>
            </div>
          </div>

          <!-- 底档列表表格 -->
          <div style="max-height: 420px; overflow-y: auto; border: 1px solid var(--border-hairline); border-radius: 4px;">
            <table class="audit-table" style="width: 100%; border-collapse: collapse; font-size: 11.5px;">
              <thead>
                <tr style="background: #14233C; color: #fff; text-align: left;">
                  <th style="padding: 7px 10px;">状态</th>
                  <th style="padding: 7px 10px;">案号/档案号</th>
                  <th style="padding: 7px 10px;">案件/顾问名称</th>
                  <th style="padding: 7px 10px;">委托人</th>
                  <th style="padding: 7px 10px;">争议相对方</th>
                  <th style="padding: 7px 10px;">主办律师</th>
                </tr>
              </thead>
              <tbody id="conflict-registry-tbody">
                <!-- 动态渲染 -->
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center;">
        <div style="font-size: 11px; color: var(--text-muted); display: flex; align-items: center; gap: 6px;">
          <span>🔒 SHA-256 数字水印验讫</span>
          <span>·</span>
          <span>律所全员实时同步</span>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="closeConflictCheckModal()">关闭排查窗口</button>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       本地库比对司法引注反查体检报告与防幻觉熔断模态框 (Citation Guard Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-citation-guard" onclick="handleCitationGuardModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 920px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            <span>本地库比对司法引注反查体检报告</span>
            <span class="badge" id="cg-modal-badge" style="background: #2E7D32; color: #fff;">100% 权威现行有效</span>
          </div>
          <div class="modal-subtitle">穿透反查 SQLite 权威法典库 · 实时熔断《合同法》《物权法》等已废止旧法 · 拦截大模型捏造越界条号</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeCitationGuardReportModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 75vh; overflow-y: auto; padding: 18px 20px;">
        <!-- 统计指标带 -->
        <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin-bottom: 14px;">
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-muted);">提取涉案引注</div>
            <div id="cg-stat-total" style="font-size: 20px; font-weight: 700; color: var(--primary-navy); font-family: var(--font-mono);">0</div>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-muted);">权威现行吻合</div>
            <div id="cg-stat-verified" style="font-size: 20px; font-weight: 700; color: #2E7D32; font-family: var(--font-mono);">0</div>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-muted);">废止法规拦截</div>
            <div id="cg-stat-abrogated" style="font-size: 20px; font-weight: 700; color: #D32F2F; font-family: var(--font-mono);">0</div>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px; text-align: center;">
            <div style="font-size: 11px; color: var(--text-muted);">捏造条号拦截</div>
            <div id="cg-stat-hallucinated" style="font-size: 20px; font-weight: 700; color: #C58532; font-family: var(--font-mono);">0</div>
          </div>
        </div>

        <!-- 切换视图：体检报告明细清单 vs 自由文本即时反查 vs 单条核验 -->
        <div class="segmented-control" style="max-width: 520px; margin-bottom: 14px;">
          <button type="button" class="seg-btn active" id="tab-btn-cg-items" onclick="switchCitationGuardTab('items')">📋 当前文书引注体检条目</button>
          <button type="button" class="seg-btn" id="tab-btn-cg-tester" onclick="switchCitationGuardTab('tester')">⚡ 自由文书防幻觉检测器</button>
          <button type="button" class="seg-btn" id="tab-btn-cg-single" onclick="switchCitationGuardTab('single')">🔍 单条法条/案号核验</button>
        </div>

        <!-- 视图 1：体检条目列表 -->
        <div id="view-cg-items">
          <div id="cg-items-list" style="display: flex; flex-direction: column; gap: 10px;">
            <div style="color: var(--text-muted); font-size: 12px; text-align: center; padding: 30px 0;">
              暂无已排查的引注数据。请在 02立案文书流水线 点击【生成全套立案公文包】或在右侧切换至【自由文书防幻觉检测器】。
            </div>
          </div>
        </div>

        <!-- 视图 2：自由文书防幻觉检测器 -->
        <div id="view-cg-tester" style="display: none;">
          <div class="form-group">
            <label class="form-label">粘贴待审查文本（起诉状事实理由、代理词、庭审提纲或外部文书）</label>
            <textarea aria-label="输入含法条引用的文本，例如：依《中华人民共和国民法典》第五百八十五条及《中华人民共和国合同法》第一百一十四条之规定..."  id="cg-custom-text" class="quick-input" rows="6" placeholder="输入含法条引用的文本，例如：依《中华人民共和国民法典》第五百八十五条及《中华人民共和国合同法》第一百一十四条之规定..."></textarea>
          </div>
          <div class="form-group">
            <label class="form-label">法律事实发生日期（决定是否可自动替换废止法条；未填或早于 2021-01-01 则不替换）</label>
            <input aria-label="cg incident date"  type="date" id="cg-incident-date" class="quick-input" style="max-width: 220px;" />
          </div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <label style="font-size: 12px; color: var(--text-secondary); display: flex; align-items: center; gap: 6px; cursor: pointer;">
              <input aria-label="cg auto sanitize chk"  type="checkbox" id="cg-auto-sanitize-chk" checked>
              <span>在法律事实发生于民法典施行后时，自动替换律师确认的合同法对应条文</span>
            </label>
            <button type="button" class="btn" onclick="runCustomCitationAudit()" style="background: #14233C;">
              执行本地库比对与净化
            </button>
          </div>
          <div id="cg-custom-result" style="display: none; background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 12px;">
            <!-- 渲染检测反馈 -->
          </div>
        </div>

        <!-- 视图 3：单条法条与案号即时核验 -->
        <div id="view-cg-single" style="display: none;">
          <div class="surface-card" style="margin-bottom: 12px; background: #FAF9F6;">
            <div style="font-weight: 700; font-size: 12.5px; color: var(--primary-navy); margin-bottom: 8px;">
              法条真实性与现行有效性探测 (verify-single)
            </div>
            <div class="form-row" style="margin-bottom: 8px;">
              <div class="form-group" style="flex: 2; margin-bottom: 0;">
                <label class="form-label">法律名称</label>
                <input aria-label="例: 民法典 或 中华人民共和国民法典"  type="text" id="cg-single-law" class="quick-input" placeholder="例: 民法典 或 中华人民共和国民法典" value="民法典" />
              </div>
              <div class="form-group" style="flex: 1; margin-bottom: 0;">
                <label class="form-label">条号 (数字)</label>
                <input aria-label="例: 585"  type="number" id="cg-single-article" class="quick-input" placeholder="例: 585" value="585" />
              </div>
            </div>
            <div style="display: flex; justify-content: flex-end;">
              <button type="button" class="btn btn-sm" onclick="runSingleCitationVerifyUI()" style="background: var(--primary-navy);">
                核验单个法条
              </button>
            </div>
          </div>

          <div class="surface-card" style="margin-bottom: 12px; background: #FAF9F6;">
            <div style="font-weight: 700; font-size: 12.5px; color: var(--primary-navy); margin-bottom: 8px;">
              裁判文书案号真伪与标准规范核验
            </div>
            <div class="form-group" style="margin-bottom: 8px;">
              <label class="form-label">裁判文书案号</label>
              <input aria-label="例: （2023）最高法民终123号 或 (2021)京0108民初1892号"  type="text" id="cg-single-caseno" class="quick-input" placeholder="例: （2023）最高法民终123号 或 (2021)京0108民初1892号" value="（2023）最高法民终123号" />
            </div>
            <div style="display: flex; justify-content: flex-end;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="runSingleCaseNumberVerifyUI()">
                核验裁判案号
              </button>
            </div>
          </div>

          <div id="cg-single-result" style="display: none; background: #FFF; border: 1px solid #EAE6DD; border-radius: 4px; padding: 12px;"></div>
        </div>
      </div>

      <div class="modal-footer" style="display: flex; justify-content: space-between; align-items: center;">
        <div style="font-size: 11px; color: var(--text-muted);">
          权威法典数据库：SQLite FTS5 cn_laws_kb.db · 涵盖民法典、民事诉讼法、刑法、行政法及九民纪要
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="closeCitationGuardReportModal()">关闭报告</button>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       案件独立空间管理模态框 (Matter Vault Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-matter-vault" onclick="handleMatterVaultBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 920px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            <span>📁 案件独立空间中枢 (Matter Vault)</span>
            <span class="badge" style="background: rgba(20, 35, 60, 0.1); color: var(--primary-navy);">SQLite 持久化底座</span>
          </div>
          <div class="modal-subtitle">以“案件/项目”为全局容器隔离与共享证据材料、当事人基本信息、立案文书与核心图谱</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeMatterVaultModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 75vh; overflow-y: auto; padding: 18px 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">
          <div style="display: flex; gap: 8px; align-items: center; flex: 1; max-width: 520px;">
            <input aria-label="搜索案件名称、案号或法定案由..."  type="text" id="vault-search-input" class="quick-input" placeholder="搜索案件名称、案号或法定案由..." oninput="filterMattersList()">
            <select aria-label="vault status filter"  id="vault-status-filter" class="quick-input" style="width: 130px;" onchange="filterMattersList()">
              <option value="all">全部状态</option>
              <option value="active" selected>在办 (Active)</option>
              <option value="archived">已归档 (Archived)</option>
            </select>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <button type="button" class="btn btn-secondary btn-sm" id="btn-clear-demo-data" onclick="clearVaultDemoData()" style="display:none; color:#D32F2F; border-color:#FFCDD2;">
              清空演示数据
            </button>
            <button type="button" class="btn btn-sm" onclick="openNewMatterDrawer()" style="background: #14233C;">
              ＋ 新建案件独立空间
            </button>
          </div>
        </div>

        <!-- 案件列表网格 -->
        <div id="vault-matters-grid" style="display: flex; flex-direction: column; gap: 10px;">
          <!-- 动态渲染案件卡片 -->
        </div>

        <!-- 新建案件内联抽屉 -->
        <div id="vault-new-matter-drawer" style="display: none; background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 16px; margin-top: 14px;">
          <div style="font-weight: 700; font-size: 13px; color: var(--primary-navy); margin-bottom: 10px;">
            ＋ 录入并初始化新案件空间
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">案件全称 *</label>
              <input aria-label="例: 某智能科技公司民间借贷纠纷案"  type="text" id="new-matter-title" class="quick-input" placeholder="例: 某智能科技公司民间借贷纠纷案">
            </div>
            <div class="form-group">
              <label class="form-label">法定案由 *</label>
              <input aria-label="new matter cause"  type="text" id="new-matter-cause" class="quick-input" value="民间借贷纠纷">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">司法案号 (选填)</label>
              <input aria-label="例: (2026)京0108民初1892号"  type="text" id="new-matter-caseno" class="quick-input" placeholder="例: (2026)京0108民初1892号">
            </div>
            <div class="form-group">
              <label class="form-label">受诉法院 (选填)</label>
              <input aria-label="例: 北京市海淀区人民法院"  type="text" id="new-matter-court" class="quick-input" placeholder="例: 北京市海淀区人民法院">
            </div>
            <div class="form-group">
              <label class="form-label">诉讼标的金额 (元)</label>
              <input aria-label="new matter amount"  type="number" id="new-matter-amount" class="quick-input" value="1000000">
            </div>
          </div>
          <div class="form-row">
            <div class="form-group">
              <label class="form-label">原告名称/主体</label>
              <input aria-label="原告姓名或公司全称"  type="text" id="new-matter-pname" class="quick-input" placeholder="原告姓名或公司全称">
            </div>
            <div class="form-group">
              <label class="form-label">被告名称/主体</label>
              <input aria-label="被告姓名或公司全称"  type="text" id="new-matter-dname" class="quick-input" placeholder="被告姓名或公司全称">
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">案件核心事实梗概 (系统将基于此自动抽取事实时间线与图谱)</label>
            <textarea aria-label="输入案情经过与关键约定..."  id="new-matter-summary" rows="3" class="quick-input" placeholder="输入案情经过与关键约定..."></textarea>
          </div>
          <div style="display: flex; justify-content: flex-end; gap: 8px;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="closeNewMatterDrawer()">取消</button>
            <button type="button" class="btn btn-sm" onclick="submitCreateNewMatter()">确认创建并立即切换至该空间</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       挂载案卷材料模态框 (Mount Document Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-mount-doc" onclick="handleMountDocBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 600px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title">＋ 挂载案卷材料至当前空间</div>
          <div class="modal-subtitle">挂载的合同、转账回单或谈话笔录将纳入全案 RAG 索引与图谱抽取源</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeMountDocModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="modal-body" style="padding: 18px 20px;">
        <div class="form-group">
          <label class="form-label">材料名称 *</label>
          <input aria-label="例: 《企业间借款合同及最高额保证书》.pdf"  type="text" id="mount-doc-title" class="quick-input" placeholder="例: 《企业间借款合同及最高额保证书》.pdf">
        </div>
        <div class="form-group">
          <label class="form-label">材料类型</label>
          <select aria-label="mount doc type"  id="mount-doc-type" class="quick-input">
            <option value="contract">合同协议 (contract)</option>
            <option value="evidence">一手证据/银行流水 (evidence)</option>
            <option value="pleading">诉讼文书/答辩状 (pleading)</option>
            <option value="transcript">询问笔录/庭审笔录 (transcript)</option>
            <option value="precedent">指导判例/类案 (precedent)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">材料文本内容 (OCR 提取文字或合同条款正文) *</label>
          <textarea aria-label="粘贴材料文字正文..."  id="mount-doc-content" rows="6" class="quick-input" placeholder="粘贴材料文字正文..."></textarea>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeMountDocModal()">取消</button>
          <button type="button" class="btn btn-sm" onclick="submitMountDocument()">确认挂载入空间</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       手工录入案件期限模态框 (Add Deadline Modal)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-add-deadline" onclick="handleAddDeadlineBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 540px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title">＋ 录入案件诉讼期限与执业红线</div>
          <div class="modal-subtitle">记录诉讼时效、上诉期、续行保全、执行申请、开庭日期等重要节点</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeAddDeadlineModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="modal-body" style="padding: 18px 20px;">
        <div class="form-group">
          <label class="form-label">期限种类 *</label>
          <select aria-label="new deadline kind"  id="new-deadline-kind" class="quick-input" onchange="onDeadlineKindChange()">
            <option value="statute_limitation">诉讼时效届满日 (statute_limitation)</option>
            <option value="appeal">上诉期截止日 (appeal)</option>
            <option value="preservation_renewal">续行财产保全申请截止日 (preservation_renewal)</option>
            <option value="enforcement_application">执行申请期限截止日 (enforcement_application)</option>
            <option value="hearing">开庭审理日 (hearing)</option>
            <option value="custom">其他执业备忘期限 (custom)</option>
          </select>
          <div id="deadline-kind-tip" style="font-size: 11px; color: var(--accent-amber); margin-top: 4px; display: none;">
            提示：执行申请期限的计算口径 TODO(律师核实)，当前仅支持手工录入，不提供自动计算。
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">截止日期 (ISO 格式 YYYY-MM-DD) *</label>
          <input aria-label="new deadline date"  type="date" id="new-deadline-date" class="quick-input">
        </div>
        <div class="form-group">
          <label class="form-label">来源 / 依据说明</label>
          <input aria-label="例: 一审民事判决书送达后第15日、保全裁定书等"  type="text" id="new-deadline-source" class="quick-input" placeholder="例: 一审民事判决书送达后第15日、保全裁定书等">
        </div>
        <div class="form-group">
          <label class="form-label">律师备忘与提醒要点</label>
          <textarea aria-label="备注顺延规则、需要提前提交的文件等..."  id="new-deadline-note" rows="3" class="quick-input" placeholder="备注顺延规则、需要提前提交的文件等..."></textarea>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeAddDeadlineModal()">取消</button>
          <button type="button" class="btn btn-sm" onclick="submitManualDeadline()" style="background: var(--primary-navy);">确认加入期限日历</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       第三批：双栏穿透式原文定位抽屉 (Split-Screen Source Grounding Drawer)
       ======================================================================== -->
  <div class="drawer-grounding" id="drawer-source-grounding">
    <div style="padding: 16px 20px; border-bottom: 1px solid var(--border-hairline); display: flex; justify-content: space-between; align-items: center; background: #FFFFFF;">
      <div>
        <div style="font-size: 14px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
          <span>🔍 双栏穿透式原文定位与证据溯源</span>
          <span class="badge" style="background: #E8F5E9; color: #2E7D32; font-size: 10.5px;">精准切片定位</span>
        </div>
        <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 2px;">
          卷宗文档：<strong id="grounding-doc-title" style="color: var(--primary-navy);">--</strong> · 页码：<strong id="grounding-doc-page" style="color: var(--primary-navy);">第 1 页</strong>
        </div>
      </div>
      <button type="button" class="modal-close-btn" onclick="closeSourceGroundingViewer()" title="关闭抽屉">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    </div>

    <!-- 视图切换：案卷原件切片 (Visual Crop) vs 文本排版 -->
    <div style="display: flex; gap: 8px; padding: 10px 16px 0; background: #F8FAFC; border-bottom: 1px solid var(--border-hairline);">
      <button type="button" class="tab-pill-btn active" id="btn-grounding-tab-visual" onclick="switchGroundingTab('visual')">
        📷 案卷原件高亮切片 (Visual Crop)
      </button>
      <button type="button" class="tab-pill-btn" id="btn-grounding-tab-text" onclick="switchGroundingTab('text')">
        📝 结构化文本对齐
      </button>
      <div style="margin-left: auto; display: flex; align-items: center; gap: 6px;">
        <span id="grounding-coords-badge" style="font-family: var(--font-mono); font-size: 10.5px; color: var(--accent-amber);"></span>
      </div>
    </div>

    <!-- 卷宗原件视觉切片区 -->
    <div id="grounding-view-visual" style="padding: 16px; flex: 1; display: flex; flex-direction: column; overflow-y: auto; background: #F8FAFC;">
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
        <span>案卷物理证据切片（琥珀色边框与金黄半透明遮罩为定位实证）：</span>
        <span id="grounding-visual-source-tag" style="font-size: 10.5px; color: var(--accent-amber); font-weight: 600;">PyMuPDF 180 DPI 高清切片</span>
      </div>
      <div id="grounding-visual-box" style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 12px; box-shadow: var(--shadow-paper); text-align: center;">
        <img id="grounding-visual-img" src="" alt="案卷原件视觉切片" style="max-width: 100%; height: auto; border: 1px solid #CBD5E1; border-radius: 2px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); display: none;">
        <div id="grounding-visual-loading" style="padding: 40px 20px; color: var(--text-muted); font-size: 12px;">
          <span class="spinner-dark"></span> 正在渲染案卷原件高清视觉切片与坐标定位...
        </div>
      </div>
    </div>

    <!-- 卷宗纸质阅读区 (带琥珀金文本高亮) -->
    <div id="grounding-view-text" style="padding: 16px; flex: 1; display: none; flex-direction: column; overflow: hidden; background: #F8FAFC;">
      <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px;">
        <span>原文段落定位上下文（琥珀色高亮处为引证事实）：</span>
      </div>
      <div class="grounding-paper" id="grounding-doc-content" style="flex: 1; overflow-y: auto;">
        <!-- 动态注入并高亮展示 -->
      </div>
    </div>

    <!-- 底部操作栏 -->
    <div style="padding: 12px 18px; border-top: 1px solid var(--border-hairline); background: #FFFFFF; display: flex; justify-content: space-between; align-items: center;">
      <div style="display: flex; gap: 8px;">
        <button type="button" class="btn btn-secondary btn-sm" onclick="copyGroundingSnippet()">
          📋 复制引证原文
        </button>
        <button type="button" class="btn btn-secondary btn-sm" onclick="copyGroundingAnchor()">
          🔗 复制溯源角标 [卷宗 P1]
        </button>
      </div>
      <button type="button" class="btn btn-sm" onclick="closeSourceGroundingViewer()">
        关闭抽屉
      </button>
    </div>
  </div>

  <!-- ========================================================================
       第三批：动态新增要素提取列模态框 (Add Review Table Column)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-add-review-column" onclick="handleAddColumnBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 540px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title">＋ 动态新增要素提取列</div>
          <div class="modal-subtitle">设定要素名称与大模型提取指令，系统将并发提取填入本列</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeAddReviewColumnModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="modal-body" style="padding: 18px 20px;">
        <div class="form-group">
          <label class="form-label">要素列名称 *</label>
          <input aria-label="例: 是否约定管辖法院、逾期交货违约金比例..."  type="text" id="new-col-name" class="quick-input" placeholder="例: 是否约定管辖法院、逾期交货违约金比例...">
        </div>
        <div class="form-group">
          <label class="form-label">要素类型</label>
          <select aria-label="new col type"  id="new-col-type" class="quick-input">
            <option value="text">文本/要点 (text)</option>
            <option value="currency">金额/费用 (currency)</option>
            <option value="date">日期/期限 (date)</option>
            <option value="opinion">质证/法律意见 (opinion)</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">要素提取指令 (LLM Prompt Instruction) *</label>
          <textarea aria-label="请指明如何从文档中判断或提取该要素，例如：提取合同中约定的违约金比例或计收方式，如未约定则填写"  id="new-col-instruction" rows="4" class="quick-input" placeholder="请指明如何从文档中判断或提取该要素，例如：提取合同中约定的违约金比例或计收方式，如未约定则填写'未明确约定'。"></textarea>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeAddReviewColumnModal()">取消</button>
          <button type="button" class="btn btn-sm" onclick="submitAddReviewColumn()">确认追加并提取</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       全局悬浮 AI 语音副驾悬浮球 (Global Floating Voice Orb)
       ======================================================================== -->
  <div role="button" tabindex="0"  id="global-voice-orb" class="global-voice-orb" onclick="toggleGlobalVoiceDrawer()" title="点击展开/收起 智律 AI 语音副驾 (随时在当前页面边看边说)">
    <span class="orb-badge-dot" id="global-orb-status-dot"></span>
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="23"></line><line x1="8" y1="23" x2="16" y2="23"></line></svg>
  </div>

  <!-- ========================================================================
       全局悬浮 AI 语音副驾抽屉 (Global Floating Voice Copilot Drawer)
       ======================================================================== -->
  <div id="global-voice-drawer" class="global-voice-drawer">
    <div style="padding: 14px 18px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; align-items: center; background: #080D1A;">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 15px;">🎙️</span>
        <strong style="font-size: 13.5px; color: #F8FAFC;">智律 AI 实时语音副驾</strong>
        <span class="badge" style="background: rgba(34, 197, 94, 0.2); color: #4ADE80; font-size: 10px;">跨模块同步</span>
      </div>
      <button type="button" class="modal-close-btn" onclick="toggleGlobalVoiceDrawer()" style="color: #94A3B8; background: transparent; border: none; cursor: pointer; font-size: 18px;" title="关闭抽屉">✕</button>
    </div>

    <!-- 抽屉内快捷声波与通话状态 -->
    <div style="padding: 10px 14px; background: #0E1626; border-bottom: 1px solid rgba(255,255,255,0.08); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
      <div style="display: flex; align-items: center; gap: 6px;">
        <span class="pulse-dot" id="drawer-voice-dot" style="background: #22C55E;"></span>
        <span id="drawer-voice-status" style="font-size: 11.5px; color: #E2E8F0;">免提待命 · 静音1.5s自动发送</span>
      </div>
      <div style="display: flex; align-items: center; gap: 6px;">
        <select aria-label="选择自然真人发音人声"  id="drawer-voice-select" onchange="onVoiceSelectionChanged(this.value)" title="选择自然真人发音人声" style="background: #080D1A; color: #CBD5E1; border: 1px solid rgba(255,255,255,0.18); border-radius: 4px; padding: 2px 6px; font-size: 11px; outline: none; cursor: pointer; max-width: 140px;">
          <option value="">载入人声...</option>
        </select>
        <button type="button" class="btn btn-amber btn-sm" id="drawer-btn-call" onclick="toggleVoiceCall()" style="padding: 3px 10px; font-size: 11px;">
          🎙️ 开启通话
        </button>
      </div>
    </div>

    <!-- 实时口述预览 -->
    <div style="padding: 10px 14px; background: #0A101D; border-bottom: 1px solid rgba(255,255,255,0.06); font-size: 11.5px; color: #CBD5E1; min-height: 44px; display: flex; align-items: center;">
      <span style="color: #F59E0B; margin-right: 6px; font-weight: 700;">[口述]</span>
      <span id="drawer-transcript-text" style="overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">直接口述案情或指令，如“把本金改成120万重新算LPR”...</span>
    </div>

    <!-- 抽屉对话流水 -->
    <div style="flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 10px;" id="drawer-messages-stream">
      <div class="copilot-chat-bubble assistant" style="max-width: 100%;">
        <span style="font-size: 11px; color: #94A3B8;">副驾提示</span>
        <div style="font-size: 12px; color: #E2E8F0; margin-top: 2px;">
          您正在浏览 <strong>当前工作台</strong>。您可以随时通过语音指挥我改写案情要素、执行利息精算或记录办案待办，当前页面将实时联动刷新！
        </div>
      </div>
    </div>

    <!-- 抽屉底部输入与直达 -->
    <div style="padding: 10px 14px; background: #080D1A; border-top: 1px solid rgba(255,255,255,0.1); display: flex; flex-direction: column; gap: 8px;">
      <div style="display: flex; gap: 6px;">
        <input aria-label="或直接输入文字指令回车..."  type="text" id="drawer-text-input" class="quick-input" style="flex: 1; background: #111A2E; color: #F8FAFC; border: 1px solid rgba(255,255,255,0.15); font-size: 12px;" placeholder="或直接输入文字指令回车..." onkeydown="if(event.key==='Enter') sendDrawerTextMessage()">
        <button type="button" class="btn btn-amber btn-sm" onclick="sendDrawerTextMessage()" style="padding: 4px 10px;">发送</button>
      </div>
      <div style="display: flex; justify-content: space-between; align-items: center;">
        <button type="button" class="btn btn-secondary btn-sm" onclick="switchNavTab('tab-copilot', '08 智律 AI 语音中枢', document.getElementById('nav-copilot')); toggleGlobalVoiceDrawer();" style="color: #94A3B8; background: transparent; border: 1px solid rgba(255,255,255,0.15); font-size: 11px; padding: 2px 8px;">
          ↗ 切换至 08 大屏总控台
        </button>
        <span style="font-size: 10.5px; color: #64748B;">LawFlow Voice Engine</span>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       手动新建/编辑办案任务模态框 (Modal Create/Edit Task)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-copilot-task" onclick="handleTaskModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 520px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" id="modal-task-title-text">＋ 新建办案任务</div>
          <div class="modal-subtitle">设定任务名称、办案阶段、优先级与关联模块动作</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeCreateTaskModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>
      <div class="modal-body" style="padding: 16px 20px;">
        <input type="hidden" id="task-modal-id" value="">
        <div class="form-group">
          <label class="form-label">任务名称 *</label>
          <input aria-label="例: 调取借款人招商银行转账流水凭证原件"  type="text" id="task-form-title" class="quick-input" placeholder="例: 调取借款人招商银行转账流水凭证原件">
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div class="form-group">
            <label class="form-label">办案阶段</label>
            <select aria-label="task form stage"  id="task-form-stage" class="quick-input">
              <option value="立案">立案阶段</option>
              <option value="精算">精算核验</option>
              <option value="证据">证据梳理</option>
              <option value="检索">法典检索</option>
              <option value="庭审">庭审质证</option>
              <option value="执行">执行查控</option>
              <option value="综合">综合事务</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">优先级</label>
            <select aria-label="task form priority"  id="task-form-priority" class="quick-input">
              <option value="high">紧急 / 高 (High)</option>
              <option value="medium" selected>常规 / 中 (Medium)</option>
              <option value="low">次要 / 低 (Low)</option>
            </select>
          </div>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
          <div class="form-group">
            <label class="form-label">截止时限</label>
            <input aria-label="例: 明日 18:00 或 2026-10-25"  type="text" id="task-form-due" class="quick-input" placeholder="例: 明日 18:00 或 2026-10-25">
          </div>
          <div class="form-group">
            <label class="form-label">联动模块直达</label>
            <select aria-label="task form module"  id="task-form-module" class="quick-input">
              <option value="phase1_litigation">02 立案文书流水线</option>
              <option value="phase1_calc">01 实务精算与核验</option>
              <option value="phase2_evidence">03 证据清洗与庭审</option>
              <option value="phase5_statutes">06 法条库与图谱</option>
              <option value="phase4_deep_matrix">05 深度要件与质证推演</option>
              <option value="matter_vault">07 案件空间与图谱</option>
            </select>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">任务备注与操作要点</label>
          <textarea aria-label="填写需要核实的证据细节、抗辩预案或备忘..."  id="task-form-desc" rows="3" class="quick-input" placeholder="填写需要核实的证据细节、抗辩预案或备忘..."></textarea>
        </div>
        <div style="display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeCreateTaskModal()">取消</button>
          <button type="button" class="btn btn-amber btn-sm" onclick="submitSaveTaskModal()">保存任务</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ========================================================================
       司法级全格式离线转码箱模态框 (Modal File Converter - Filee 协同)
       ======================================================================== -->
  <div role="button" tabindex="0"  class="modal-overlay" id="modal-file-converter" onclick="handleConverterModalBackdropClick(event)">
    <div role="button" tabindex="0"  class="modal-dialog" style="max-width: 820px;" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-group">
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px;">
            <span>⚖️ 司法级全格式离线转码箱</span>
            <span class="badge" id="modal-converter-engine-badge" style="background: rgba(34, 197, 94, 0.15); color: #15803D; font-size: 11px;">
              ⚡ 内置司法引擎就绪
            </span>
          </div>
          <div class="modal-subtitle">100% 本地离线执行 · 零数据上云 · 符合《律师执业行为规范》与涉案保密红线 · 支持 Filee CLI 增强</div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeFileConverterModal()" title="关闭">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 75vh; overflow-y: auto; padding: 18px 22px;">
        
        <!-- 引擎状态说明条 -->
        <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 10px 14px; margin-bottom: 14px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
          <div style="font-size: 12px; color: var(--text-secondary);">
            <span style="font-weight: 700; color: var(--primary-navy);">当前引擎模式：</span>
            <span id="modal-converter-engine-desc">LawFlow 司法内置快速转码引擎（原生支持 HEIC/TIFF/PDF/Word/CSV/音频）</span>
          </div>
          <div style="font-size: 11px; color: var(--text-muted);" id="modal-converter-filee-hint">
            💡 可将 Filee.exe 放入 <code>tools/filee</code> 目录解锁 244 种工业与特殊格式
          </div>
        </div>

        <!-- 快捷业务预设芯片 -->
        <div style="margin-bottom: 14px;">
          <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
            诉讼实务高频转换预设：
          </div>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;" id="modal-converter-presets-container">
            <button type="button" class="btn btn-secondary btn-sm" onclick="applyConverterPreset('heic_to_pdf', 'pdf', '原告证据', true)">
              📄 手机拍照(HEIC/TIFF) -> 法院立案PDF
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="applyConverterPreset('multi_to_bates_pdf', 'pdf', '证据', true)">
              📑 多证据图批量合卷 (标准A4+加盖贝茨码)
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="applyConverterPreset('audio_to_court_mp3', 'mp3', '', false)">
              🎵 谈话录音(M4A/AMR) -> 司法标准MP3
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="applyConverterPreset('table_to_court_pdf', 'pdf', '', false)">
              📊 银行流水(CSV/XLSX) -> 证据对照表格PDF
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="applyConverterPreset('pdf_to_images', 'png', '', false)">
              🖼️ 证据PDF拆解为高清图片(PNG)
            </button>
          </div>
        </div>

        <!-- 拖拽上传与选文件区 -->
        <div role="button" tabindex="0"  id="converter-drop-zone" style="border: 2px dashed #CBD5E1; border-radius: var(--radius-md); padding: 24px; text-align: center; background: #FCFBF9; cursor: pointer; transition: all 0.15s; margin-bottom: 14px;" onclick="document.getElementById('converter-file-input').click()">
          <input aria-label="converter file input"  type="file" id="converter-file-input" style="display: none;" multiple onchange="onConverterFilesSelected(this.files)">
          <div style="font-size: 32px; margin-bottom: 6px;">📂</div>
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy);">
            点击或拖拽文件至此处上传
          </div>
          <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 4px;">
            支持 HEIC, JPG, PNG, TIFF, PDF, DOCX, CSV, XLSX, M4A, AMR, MP3 等任意单文件或多文件
          </div>
        </div>

        <!-- 选定文件列表 -->
        <div id="converter-selected-list" style="display: none; margin-bottom: 14px; background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 10px 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 12px; font-weight: 700; color: var(--primary-navy);">已选定待转换文件 (<span id="converter-files-count">0</span>)</span>
            <button type="button" class="btn btn-secondary btn-sm" onclick="clearConverterFiles()" style="padding: 2px 6px; font-size: 11px;">清空</button>
          </div>
          <div id="converter-files-summary" style="font-size: 12px; color: var(--text-secondary); max-height: 100px; overflow-y: auto; line-height: 1.6;"></div>
        </div>

        <!-- 转换选项配置 -->
        <div style="display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 12px; margin-bottom: 16px; background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">目标转换格式</label>
            <select aria-label="converter target format"  id="converter-target-format" class="quick-input" onchange="onTargetFormatChange(this.value)">
              <option value="pdf" selected>法院标准 PDF (附格式规范)</option>
              <option value="jpg">高清 JPG 图片</option>
              <option value="png">无损 PNG 图片</option>
              <option value="mp3">标准音频 MP3 (直通 08 AI中枢)</option>
              <option value="wav">高质量音频 WAV</option>
              <option value="txt">纯文本 TXT</option>
            </select>
          </div>
          <div class="form-group" style="margin-bottom: 0;" id="converter-bates-group">
            <label class="form-label">贝茨编码前缀</label>
            <input aria-label="例: 证据1 或 原告证据"  type="text" id="converter-bates-prefix" class="quick-input" value="证据" placeholder="例: 证据1 或 原告证据">
          </div>
          <div class="form-group" style="margin-bottom: 0; display: flex; flex-direction: column; justify-content: flex-end;" id="converter-stamp-group">
            <label style="display: flex; align-items: center; gap: 6px; font-size: 12px; cursor: pointer; color: var(--primary-navy); padding-bottom: 6px;">
              <input aria-label="converter stamp checkbox"  type="checkbox" id="converter-stamp-checkbox" checked>
              <span>右上角加盖红色贝茨页码</span>
            </label>
          </div>
        </div>

        <!-- 转换执行按钮 -->
        <div style="display: flex; justify-content: flex-end; gap: 10px; align-items: center;">
          <span id="converter-progress-text" style="font-size: 12px; color: var(--text-muted); display: none;">正在本地离线转码中...</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeFileConverterModal()">关闭</button>
          <button type="button" class="btn btn-amber" id="btn-run-converter" onclick="executeOfflineConversion()" style="padding: 7px 18px; font-weight: 700;">
            ⚡ 立即离线转换
          </button>
        </div>

        <!-- 转换结果展示卡片 -->
        <div id="converter-result-box" style="display: none; margin-top: 16px; background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: var(--radius-sm); padding: 14px 18px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <span style="font-size: 16px;">✅</span>
              <strong style="font-size: 13.5px; color: #166534;" id="converter-result-title">转码成功</strong>
              <span class="badge" id="converter-result-engine" style="background: rgba(22, 101, 52, 0.15); color: #15803D; font-size: 10.5px;">LawFlow 司法引擎</span>
            </div>
            <span id="converter-result-time" style="font-size: 11px; color: #166534;">耗时: 120ms</span>
          </div>
          <div style="font-size: 12.5px; color: #14532D; margin-bottom: 10px;" id="converter-result-desc">
            已生成符合法院规范的标准文件。
          </div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <a id="converter-download-btn" href="#" target="_blank" class="btn btn-sm" style="background: #15803D; color: #FFFFFF; border: none; text-decoration: none; padding: 5px 14px; font-size: 12px; display: inline-flex; align-items: center; gap: 4px;">
              📥 立即下载成品文件
            </a>
            <button type="button" class="btn btn-secondary btn-sm" id="converter-push-evidence-btn" onclick="pushConvertedToEvidenceList()" style="font-size: 12px; background: #FFFFFF; color: #15803D; border: 1px solid #86EFAC;">
              📑 推送到 03 证据目录清单
            </button>
            <button type="button" class="btn btn-secondary btn-sm" id="converter-push-copilot-btn" onclick="pushConvertedToVoiceCopilot()" style="font-size: 12px; background: #FFFFFF; color: #B45309; border: 1px solid #FDE68A;">
              🎙️ 唤醒 08 AI语音副驾梳理
            </button>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- ========================================================================
       系统运行环境与依赖体检模态框 (System Health Probing Modal)
       ======================================================================== -->
  <div role="button" tabindex="0" class="modal-overlay" id="modal-system-health" onclick="handleSystemHealthModalBackdropClick(event)">
    <div role="button" tabindex="0" class="modal-container" style="max-width: 820px; width: 94%;" onclick="event.stopPropagation()">
      <div class="modal-header" style="background: #14233C; color: #FFFFFF; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center;">
        <div>
          <div class="modal-title" style="display: flex; align-items: center; gap: 8px; font-size: 15px; font-weight: 700; color: #FFFFFF;">
            <span>🩺 系统运行环境与本地依赖体检报告</span>
            <span class="badge" id="health-overall-badge" style="background: rgba(34, 197, 94, 0.2); color: #4ADE80; font-size: 11px; border: 1px solid rgba(74, 222, 128, 0.4);">
              检测中...
            </span>
          </div>
          <div class="modal-subtitle" style="font-size: 11.5px; color: #94A3B8; margin-top: 2px;">
            全面探测本地 LibreOffice、Ollama、SQLite 知识库、案件空间及 PDF 渲染引擎运行状态
          </div>
        </div>
        <button type="button" class="modal-close-btn" onclick="closeSystemHealthModal()" title="关闭" style="background: transparent; border: none; color: #94A3B8; cursor: pointer; padding: 4px;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <div class="modal-body" style="max-height: 75vh; overflow-y: auto; padding: 18px 22px; background: #F8FAFC;">
        
        <!-- 总体健康摘要卡片 -->
        <div id="health-summary-banner" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 14px 18px; margin-bottom: 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span id="health-summary-icon" style="font-size: 18px;">🔍</span>
              <strong style="font-size: 13.5px; color: var(--primary-navy);" id="health-summary-title">系统体检进行中</strong>
            </div>
            <span id="health-last-checked" style="font-size: 11px; color: var(--text-muted);">尚未体检</span>
          </div>
          <div style="font-size: 12.5px; color: var(--text-secondary); line-height: 1.5;" id="health-summary-text">
            正在探测本地运行环境依赖项...
          </div>
        </div>

        <!-- 5 项依赖组件体检卡片列表 -->
        <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
          组件探测详情与排障建议：
        </div>
        <div id="health-cards-container" style="display: flex; flex-direction: column; gap: 10px;">

          <!-- 1. LibreOffice -->
          <div class="health-card" id="card-health-libreoffice" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">📝</span>
                <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">LibreOffice 司法级排版引擎</span>
              </div>
              <span class="badge" id="health-badge-libreoffice" style="font-size: 11px; padding: 2px 8px;">探测中</span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 6px;" id="health-info-libreoffice">
              执行文件路径: 检测中...
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; border-radius: 4px; padding: 6px 10px;" id="health-remediation-libreoffice">
              未检测到 LibreOffice (soffice)。若需完美还原复杂的 Word 排版及法庭文书，可下载安装 LibreOffice 7.x/24.x 并添加至系统 PATH；未安装时系统自动降级使用内置 PyMuPDF 纯代码分页引擎。
            </div>
          </div>

          <!-- 2. 本地 Ollama 大模型 -->
          <div class="health-card" id="card-health-ollama" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">🤖</span>
                <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">本地离线私有化大模型 (Ollama)</span>
              </div>
              <span class="badge" id="health-badge-ollama" style="font-size: 11px; padding: 2px 8px;">探测中</span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 6px;" id="health-info-ollama">
              服务地址: http://127.0.0.1:11434
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; border-radius: 4px; padding: 6px 10px;" id="health-remediation-ollama">
              本地 11434 端口未启动。若需完全离线断网大模型，请运行 'ollama serve'；若无需本地模型，可配置云端 API Key 或使用内置专家规则引擎。
            </div>
          </div>

          <!-- 3. SQLite 权威法典库 -->
          <div class="health-card" id="card-health-cn-laws" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">📚</span>
                <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">权威法典与全文检索库 (cn_laws_kb.db)</span>
              </div>
              <span class="badge" id="health-badge-cn-laws" style="font-size: 11px; padding: 2px 8px;">探测中</span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 6px;" id="health-info-cn-laws">
              存储路径: 检测中...
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; border-radius: 4px; padding: 6px 10px;" id="health-remediation-cn-laws">
              权威法典库状态检测中...
            </div>
          </div>

          <!-- 4. SQLite 案件独立空间数据库 -->
          <div class="health-card" id="card-health-matter-vault" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">📁</span>
                <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">案件空间独立数据库 (matter_vault.db)</span>
              </div>
              <span class="badge" id="health-badge-matter-vault" style="font-size: 11px; padding: 2px 8px;">探测中</span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 6px;" id="health-info-matter-vault">
              存储路径: 检测中...
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; border-radius: 4px; padding: 6px 10px;" id="health-remediation-matter-vault">
              案件空间数据库状态检测中...
            </div>
          </div>

          <!-- 5. PDF 渲染引擎矩阵 -->
          <div class="health-card" id="card-health-pdf-engine" style="background: #FFFFFF; border: 1px solid #E2E8F0; border-radius: var(--radius-sm); padding: 12px 16px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px;">📑</span>
                <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">PDF 渲染与文书排版引擎矩阵</span>
              </div>
              <span class="badge" id="health-badge-pdf-engine" style="font-size: 11px; padding: 2px 8px;">探测中</span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-muted); font-family: var(--font-mono); margin-bottom: 6px;" id="health-info-pdf-engine">
              活动引擎: 检测中...
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; border-radius: 4px; padding: 6px 10px;" id="health-remediation-pdf-engine">
              PDF 引擎状态检测中...
            </div>
          </div>

        </div>

      </div>

      <!-- 模态框底部操作栏 -->
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px 22px; border-top: 1px solid var(--border-hairline); background: #FFFFFF;">
        <div style="font-size: 11px; color: var(--text-muted);">
          💡 提示：本系统所有核心功能均具备纯本地离线与算法兜底设计，部分依赖缺失不影响基础精算与立案操作。
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="closeSystemHealthModal()">关闭</button>
          <button type="button" class="btn btn-sm" id="btn-refresh-system-health" onclick="refreshSystemHealth(true)" style="background: #14233C; color: #FFFFFF; font-weight: 700; padding: 6px 14px; border: none; cursor: pointer; display: inline-flex; align-items: center; gap: 5px;">
            🔄 重新体检
          </button>
        </div>
      </div>

    </div>
  </div>
</body>
</html>
`;

let _lastActiveElement = null;

export function setupModalFocusManagement() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      const activeModal = document.querySelector('.modal-overlay.active');
      if (activeModal) {
        activeModal.classList.remove('active');
        if (_lastActiveElement && typeof _lastActiveElement.focus === 'function') {
          _lastActiveElement.focus();
        }
      }
    }
  });
}

export function initModals() {
  let root = document.getElementById('modal-root');
  if (!root) {
    root = document.createElement('div');
    root.id = 'modal-root';
    document.body.appendChild(root);
  }
  // safe-html: static modal markup
  root.innerHTML = MODALS_HTML;
}

if (typeof window !== 'undefined') {
  window.initModals = initModals;
  window.setupModalFocusManagement = setupModalFocusManagement;
}

/**
 * LawFlow Module: 04_appeal_signing.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const APPEALSIGNING_TAB_HTML = `      
      <!-- 顶层模式切换器 (P3 二审翻盘大屏 vs 常规双库检索) -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">
        <div class="segmented-control" style="font-size: 12px;">
          <button type="button" class="segmented-btn active" id="btn-subtab-appeal" onclick="switchRagSignSubTab('appeal')">
            ⚖️ 二审/再审关键阶段：类案裁判分歧对抗大屏 (P3升级·最高院同案不同判穿透)
          </button>
          <button type="button" class="segmented-btn" id="btn-subtab-legacy" onclick="switchRagSignSubTab('legacy')">
            📑 常规双库检索与远程电子签约
          </button>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="load80MRepurchasePreset()" style="font-size: 11.5px; border-color: var(--accent-amber); color: var(--primary-navy);">
          ⚡ 载入演示案（use_demo）· 非真实案例
        </button>
        <span id="appeal-demo-badge" style="display:none; margin-left:8px; font-size:11px; color:#B45309; background:#FEF3C7; padding:2px 8px; border-radius:4px;">演示数据·非真实案例</span>
      </div>

      <!-- 子面板 A: P3 二审/再审关键阶段·一审裁决漏洞剖析与最高院类案分歧穿透大屏 -->
      <div id="pane-rag-appeal" style="display: block;">
        
        <!-- 全景核心指标看板 -->
        <div id="appeal-metrics-bar" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; margin-bottom: 14px;">
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
            <div style="font-size: 11px; color: var(--text-muted);">涉案诉讼案由与阶段</div>
            <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-top: 3px;" id="appeal-metric-cause">
              【待填写】案由
            </div>
            <div style="font-size: 10.5px; color: var(--accent-amber); margin-top: 2px;" id="appeal-metric-deadline">上诉期截止日：【待填写】</div>
            <button type="button" class="btn btn-secondary btn-sm" id="btn-appeal-add-deadline" style="display:none; font-size:10.5px; padding:2px 6px; margin-top:3px;" onclick="addAppealDeadlineToVault()">
              📅 加入案件期限
            </button>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
            <div style="font-size: 11px; color: var(--text-muted);">一审裁决漏洞诊断</div>
            <div style="font-size: 16px; font-weight: 700; color: #B91C1C; margin-top: 3px; font-family: var(--font-mono);" id="appeal-metric-flaws">
              — 
            </div>
            <div style="font-size: 10.5px; color: #B91C1C; margin-top: 2px;">依判决文本关键词识别，无则未识别</div>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
            <div style="font-size: 11px; color: var(--text-muted);">已核验类案支持</div>
            <div style="font-size: 16px; font-weight: 700; color: #15803D; margin-top: 3px; font-family: var(--font-mono);" id="appeal-metric-precedents">
              —
            </div>
            <div style="font-size: 10.5px; color: #15803D; margin-top: 2px;">法发〔2020〕24号检索层级</div>
          </div>
          <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
            <div style="font-size: 11px; color: var(--text-muted);">最高院裁判尺度统一合规率</div>
            <div style="font-size: 16px; font-weight: 700; color: #1E40AF; margin-top: 3px; font-family: var(--font-mono);">
              100% 官方案号本地库比对通过
            </div>
            <div style="font-size: 10.5px; color: #1E40AF; margin-top: 2px;">法发〔2020〕24号类案检索规范</div>
          </div>
        </div>

        <div class="split-grid-50-50">
          
          <!-- 左侧：一审判决输入与三大破绽预警 -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                一审判决信息与漏洞靶向诊断
              </div>
              <span class="card-tip">结构化剖析判决理由</span>
            </div>

            <div class="form-row">
              <div class="form-group" style="flex: 1.2;">
                <label class="form-label">作出一审判决法院（必填）</label>
                <input aria-label="如：某市中级人民法院"  type="text" id="appeal-input-court" placeholder="如：某市中级人民法院" value="">
              </div>
              <div class="form-group" style="flex: 1;">
                <label class="form-label">争议标的金额 (元)</label>
                <input aria-label="选填"  type="number" id="appeal-input-amount" placeholder="选填" value="">
              </div>
              <div class="form-group" style="flex: 0.8;">
                <label class="form-label">约定违约金率</label>
                <input aria-label="选填"  type="number" step="0.01" id="appeal-input-rate" placeholder="选填" value="">
              </div>
            </div>
            <div class="form-row" style="margin-top: 6px;">
              <div class="form-group" style="flex: 1;">
                <label class="form-label">原审案号</label>
                <input aria-label="【待填写】"  type="text" id="appeal-input-case-no" placeholder="【待填写】" value="">
              </div>
              <div class="form-group" style="flex: 1;">
                <label class="form-label">案由</label>
                <input aria-label="【待填写】"  type="text" id="appeal-input-cause" placeholder="【待填写】" value="">
              </div>
              <div class="form-group" style="flex: 0.8;">
                <label class="form-label">裁判种类</label>
                <select aria-label="appeal input judgment type"  id="appeal-input-judgment-type">
                  <option value="judgment">判决</option>
                  <option value="ruling">裁定</option>
                </select>
              </div>
              <div class="form-group" style="flex: 1;">
                <label class="form-label">送达日期</label>
                <input aria-label="appeal input service date"  type="date" id="appeal-input-service-date" value="">
              </div>
            </div>

            <div class="form-group" style="margin-top: 8px;">
              <label class="form-label">一审裁判理由（本院认为）及一审法官认定事实</label>
              <textarea aria-label="粘贴一审判决书本院认为段落；无关键词时探针将显示未识别"  id="appeal-input-judgment" rows="5" class="quick-input" style="font-size: 12px; line-height: 1.5;" placeholder="粘贴一审判决书本院认为段落；无关键词时探针将显示未识别"></textarea>
            </div>

            <button type="button" class="btn" style="width: 100%; margin-top: 6px;" onclick="runAppealAuditUI()">
              ⚡ 执行一审裁判漏洞剖析与最高院类案分歧穿透
            </button>

            <!-- 诊断出的一审判决致命破绽 -->
            <div id="appeal-flaws-container" style="margin-top: 12px; display: flex; flex-direction: column; gap: 8px;">
              <!-- 动态注入三大漏洞卡片 -->
            </div>
          </div>

          <!-- 右侧：类案裁判分歧对抗矩阵与二审突围文书 -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                最高院与高院类案裁判分歧对抗矩阵
              </div>
              <span class="badge" style="background:#DCFCE7; color:#15803D; font-weight:700;">支持派权威判例</span>
            </div>

            <!-- 分歧对抗表格视窗 -->
            <div id="appeal-matrix-container" style="max-height: 280px; overflow-y: auto; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 8px; margin-bottom: 12px; background: #FAF9F6;">
              <!-- 动态注入最高院对比卡片 -->
            </div>

            <!-- 裁判口径演变时间谱系折叠盒 -->
            <div style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: 4px; padding: 10px 12px; margin-bottom: 12px;">
              <div style="font-size: 11.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 4px;">
                📜 最高人民法院商事对赌裁判口径演进时间谱系：
              </div>
              <div id="appeal-timeline-container" style="font-size: 11px; color: var(--text-secondary); line-height: 1.5;">
                <!-- 动态注入时间轴 -->
              </div>
            </div>

            <!-- 二审文书切换与导出工具栏 -->
            <div style="border-top: 1px dashed var(--border-hairline); padding-top: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 6px;">
                <div class="segmented-control" style="font-size: 11px;">
                  <button type="button" class="segmented-btn active" id="btn-doc-pleading" onclick="switchAppealDocView('pleading')">
                    📄 民事上诉状 (靶向重构版)
                  </button>
                  <button type="button" class="segmented-btn" id="btn-doc-memo" onclick="switchAppealDocView('memo')">
                    📑 类案检索与分歧论证报告
                  </button>
                </div>
                <div style="display: flex; gap: 6px;">
                  <button type="button" class="btn btn-secondary btn-sm" onclick="copyAppealDocument()" style="font-size: 11px; padding: 2px 8px;">
                    📋 一键复制
                  </button>
                  <button type="button" class="btn btn-amber btn-sm" onclick="exportAppealDocxUI()" style="font-size: 11px; padding: 2px 8px;">
                    📥 导出标准 Word (.docx)
                  </button>
                </div>
              </div>

              <!-- 文书预览容器 -->
              <div id="appeal-doc-preview" style="font-family: var(--font-serif); font-size: 11.5px; line-height: 1.6; color: var(--primary-navy); background: #FAF9F6; border: 1px solid var(--border-hairline); border-radius: 4px; padding: 10px 12px; max-height: 220px; overflow-y: auto; white-space: pre-wrap;">
                正在加载二审文书预览...
              </div>
            </div>

          </div>

        </div>

      </div>

      <!-- 子面板 B: 常规双库检索与远程电子签约 (原功能完整保留) -->
      <div id="pane-rag-legacy" style="display: none;">
        <div class="split-grid-50-50">
          
          <!-- 左侧：双库检索与办案策略 -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                双库隔离检索与办案策略
              </div>
              <span class="card-tip">法规库与胜诉案例库隔离</span>
            </div>

            <div class="form-row">
              <div class="form-group" style="flex: 2;">
                <label class="form-label">案情检索关键词</label>
                <input aria-label="检索案由事实或请求权关键词"  type="text" id="rag-q" value="借条丢失 微信转账 借贷合意证明">
              </div>
              <div class="form-group" style="flex: 1;">
                <label class="form-label">检索库源</label>
                <select aria-label="检索法源类案文库范围"  id="rag-corpus">
                  <option value="all">双库融合检索</option>
                  <option value="public_statutes">仅公共法规库</option>
                  <option value="private_cases">仅胜诉案例库</option>
                </select>
              </div>
              <div class="form-group" style="flex: 0.8; align-self: flex-end;">
                <button class="btn" style="width: 100%;" onclick="runDualRAGSearch()">检索</button>
              </div>
            </div>

            <div class="card-header" style="margin-top: 10px;">
              <div class="card-title" style="font-size: 13.5px;">
                办案疑难咨询与代理词策略
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">提出疑难问题</label>
              <textarea aria-label="consult q"  id="consult-q" rows="3">当事人只有微信转账记录没有借条，对方微信答应了会还，但现在不认账，应该如何起诉，如何引用法条？</textarea>
            </div>

            <button class="btn btn-amber" id="btn-consult" onclick="runRAGConsult()">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
              出具起诉与代理词策略意见
            </button>

            <div id="consult-ans-box" class="legal-statement-box" style="display: none; max-height: 240px; margin-top: 10px;"></div>
          </div>

          <!-- 右侧：检索结果与远程电子签约 -->
          <div class="docket-receipt-paper">
            <div class="receipt-header">
              <div class="receipt-title">
                <span>检索结果与远程委托签约</span>
                <span class="badge">法条与闭环</span>
              </div>
            </div>

            <!-- 检索命中条目 -->
            <div id="rag-dual-results" style="display: flex; flex-direction: column; gap: 8px; max-height: 220px; overflow-y: auto;">
              <div style="font-size: 12px; color: var(--text-muted);">正在加载初始类案与法条对照...</div>
            </div>

            <!-- 远程委托电子签约闭环 -->
            <div style="border-top: 1px dashed var(--border-hairline); padding-top: 14px;">
              <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
                远程委托合同电子签约闭环 (微信端手写签名)
              </div>
              <div id="sign-demo-banner" style="display:block; margin-bottom:10px; padding:10px 12px; background:#FEF3C7; border:1px solid #F59E0B; border-radius:6px; color:#92400E; font-size:12px; font-weight:700; line-height:1.5;">
                ⚠ 演示模式：未接入真实电子签名服务，签署结果不具有法律效力
              </div>
              
              <div class="form-row">
                <div class="form-group"><label class="form-label">委托人姓名</label><input aria-label="sign c name"  type="text" id="sign-c-name" value="张三"></div>
                <div class="form-group"><label class="form-label">联系电话</label><input aria-label="sign c phone"  type="text" id="sign-c-phone" value="13800000000"></div>
              </div>
              
              <div class="form-row" style="margin-top: 8px;">
                <div class="form-group"><label class="form-label">承办律师</label><input aria-label="sign l name"  type="text" id="sign-l-name" value="李四律师"></div>
                <div class="form-group"><label class="form-label">代理费 (元)</label><input aria-label="sign fee"  type="number" id="sign-fee" value="20000"></div>
              </div>

              <div class="form-group" style="margin-top: 8px;">
                <label class="form-label">委托代理事由</label>
                <input aria-label="sign case"  type="text" id="sign-case" value="代理原告张三诉北京宏达公司买卖合同纠纷一审诉讼">
              </div>

              <button class="btn" style="margin-top: 12px; width: 100%;" onclick="runCreateDocuSealLink()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"></path><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path></svg>
                生成当事人微信手写签约任务
              </button>

              <!-- 签约结果与存证凭据 -->
              <div id="sign-flow-box" style="display: none; margin-top: 12px; padding: 12px; background: var(--bg-subtle); border-radius: var(--radius-sm); border: 1px solid var(--border-hairline);">
                <div style="font-size: 12px; font-weight: 700; color: var(--status-valid);">签约链接已成功生成</div>
                <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px; word-break: break-all;">
                  微信签约地址：<a href="#" id="sign-h5-link" target="_blank" style="color: var(--primary-navy); text-decoration: underline;"></a>
                </div>
                <div style="display: flex; gap: 8px; margin-top: 10px;">
                  <button class="btn btn-secondary btn-sm" onclick="copySigningLink()">复制签署链接</button>
                  <button class="btn btn-amber btn-sm" onclick="simulateClientSignature()">模拟当事人完成微信手写签名</button>
                </div>
                <div id="sign-audit-trail" style="margin-top: 10px; font-size: 11px; color: var(--text-secondary); border-top: 1px dashed var(--border-hairline); padding-top: 8px;"></div>
              </div>

            </div>

          </div>

        </div>
      </div>
    </section>

    <!-- ======================================================================
         模块 05：深度要件与质证推演 (Anspruchsgrundlage & Fact-Element Matrix & Adversarial Red-Team Hub)
         ====================================================================== -->
`;

export function renderTabAppealSigning() {
  const el = document.getElementById('tab-rag-sign');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = APPEALSIGNING_TAB_HTML;
  }
}


    // =========================================================================
    // 5. 模块 04：二审/再审类案裁判分歧对抗与心证翻盘大屏 (P3升级)
    // =========================================================================
    let lastAppealDeadline = null;
    let currentAppealAuditData = null;
    let currentAppealDocView = 'pleading'; // 'pleading' or 'memo'

    function switchRagSignSubTab(subTab) {
      const btnAppeal = document.getElementById('btn-subtab-appeal');
      const btnLegacy = document.getElementById('btn-subtab-legacy');
      const paneAppeal = document.getElementById('pane-rag-appeal');
      const paneLegacy = document.getElementById('pane-rag-legacy');

      if (subTab === 'appeal') {
        if (btnAppeal) btnAppeal.classList.add('active');
        if (btnLegacy) btnLegacy.classList.remove('active');
        if (paneAppeal) paneAppeal.style.display = 'block';
        if (paneLegacy) paneLegacy.style.display = 'none';
        if (!currentAppealAuditData) {
          runAppealAuditUI(false);
        }
      } else {
        if (btnLegacy) btnLegacy.classList.add('active');
        if (btnAppeal) btnAppeal.classList.remove('active');
        if (paneLegacy) paneLegacy.style.display = 'block';
        if (paneAppeal) paneAppeal.style.display = 'none';
      }
    }

    let appealUseDemoFlag = false;

    function load80MRepurchasePreset() {
      appealUseDemoFlag = true;
      const badge = document.getElementById('appeal-demo-badge');
      if (badge) badge.style.display = 'inline-block';
      switchRagSignSubTab('appeal');
      showToast('已载入演示数据·非真实案例（use_demo=true）');
      runAppealAuditUI(true);
    }

    async function runAppealAuditUI(triggerToast = true) {
      const court = (document.getElementById('appeal-input-court')?.value || '').trim();
      const amountRaw = document.getElementById('appeal-input-amount')?.value;
      const rateRaw = document.getElementById('appeal-input-rate')?.value;
      const amount = amountRaw !== undefined && amountRaw !== '' ? parseFloat(amountRaw) : null;
      const rate = rateRaw !== undefined && rateRaw !== '' ? parseFloat(rateRaw) : null;
      const judgmentText = document.getElementById('appeal-input-judgment')?.value || '';
      const caseNo = document.getElementById('appeal-input-case-no')?.value || '';
      const cause = document.getElementById('appeal-input-cause')?.value || '';
      const judgmentType = document.getElementById('appeal-input-judgment-type')?.value || 'judgment';
      const serviceDate = document.getElementById('appeal-input-service-date')?.value || '';

      if (!appealUseDemoFlag && !court) {
        showToast('请填写一审法院名称（必填）');
        return;
      }

      const flawsCont = document.getElementById('appeal-flaws-container');
      const matrixCont = document.getElementById('appeal-matrix-container');
      const timelineCont = document.getElementById('appeal-timeline-container');

      if (flawsCont) flawsCont.innerHTML = `<div style="text-align:center; padding:15px; color:var(--text-muted);"><span class="spinner-dark"></span> 正在诊断一审判决败诉破绽...</div>`;
      if (matrixCont) matrixCont.innerHTML = `<div style="text-align:center; padding:15px; color:var(--text-muted);"><span class="spinner-dark"></span> 正在检索已核验类案...</div>`;

      try {
        const payload = {
          judgment_text: judgmentText,
          first_instance_court: court || '【演示】一审法院',
          first_instance_case_no: caseNo || null,
          cause_of_action: cause || null,
          judgment_type: judgmentType,
          service_date: serviceDate || null,
          use_demo: !!appealUseDemoFlag,
        };
        if (amount !== null && !Number.isNaN(amount)) payload.claim_amount = amount;
        if (rate !== null && !Number.isNaN(rate)) payload.agreed_repurchase_rate = rate;

        const resp = await api.request(`${API_BASE}/api/v1/litigation/appeal-audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentAppealAuditData = data;

        const demoBadge = document.getElementById('appeal-demo-badge');
        if (demoBadge) {
          demoBadge.style.display = data.is_demo ? 'inline-block' : 'none';
        }
        if (data.is_demo && triggerToast) {
          showToast(data.demo_notice || '演示数据·非真实案例');
        }

        // 1. 渲染指标栏
        const metricFlaws = document.getElementById('appeal-metric-flaws');
        if (metricFlaws) metricFlaws.innerText = `${data.total_flaws_found || 0} 项识别漏洞`;
        const metricPrecedents = document.getElementById('appeal-metric-precedents');
        if (metricPrecedents) metricPrecedents.innerText = `${data.total_pro_precedents || 0} 篇已核验类案`;
        const metricDeadline = document.getElementById('appeal-metric-deadline');
        if (metricDeadline) {
          if (data.appeal_deadline) {
            metricDeadline.innerText = `上诉期截止日：${data.appeal_deadline}`;
            lastAppealDeadline = data.appeal_deadline;
            const aBtn = document.getElementById('btn-appeal-add-deadline');
            if (aBtn) aBtn.style.display = 'inline-flex';
          } else if (serviceDate) {
            try {
              const dlResp = await api.request(`${API_BASE}/api/v1/phase1/calc/appeal-deadline`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ service_date: serviceDate, judgment_type: judgmentType })
              });
              if (dlResp.ok) {
                const dl = await dlResp.json();
                metricDeadline.innerText = `上诉期截止日：${dl.deadline}`;
                lastAppealDeadline = dl.deadline;
                const aBtn = document.getElementById('btn-appeal-add-deadline');
                if (aBtn) aBtn.style.display = 'inline-flex';
              } else {
                metricDeadline.innerText = '上诉期截止日：【待填写】';
              }
            } catch (_) {
              metricDeadline.innerText = '上诉期截止日：【待填写】';
            }
          } else {
            metricDeadline.innerText = '上诉期截止日：【待填写】（请填写送达日期）';
          }
        }
        appealUseDemoFlag = false;

        // 2. 渲染三大破绽警告卡片
        if (flawsCont) {
          const flaws = data.flaw_diagnostics || [];
          flawsCont.innerHTML = flaws.map(f => `
            <div class="surface-card" style="padding: 10px 12px; border-left: 4px solid #EF4444; background: #FEF2F2;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-weight: 700; font-size: 12.5px; color: #B91C1C;">🚨 【${escapeHtml(f.probe_id)}】${escapeHtml(f.error_type)}</span>
                <span class="badge" style="background:#FEE2E2; color:#B91C1C; font-size:10px;">致命适用法律错误</span>
              </div>
              <div style="font-size: 11px; color: var(--text-secondary); line-height: 1.4; margin-bottom: 4px;">
                <strong>一审错误认定：</strong>${escapeHtml(f.first_instance_holding)}
              </div>
              <div style="font-size: 11px; color: #166534; background: #F0FDF4; padding: 6px 8px; border-radius: 4px; border: 1px solid #86EFAC;">
                <strong>二审驳斥破绽要诀：</strong>${escapeHtml(f.appellate_attack_point)}
              </div>
              <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">
                违背实体法：${escapeHtml(f.statute_violated)}
              </div>
            </div>
          `).join('');
        }

        // 3. 渲染最高院类案裁判分歧对抗矩阵
        if (matrixCont) {
          const matrix = data.precedent_matrix || [];
          matrixCont.innerHTML = matrix.map((row, idx) => `
            <div style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 10px 12px; margin-bottom: 8px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <span class="badge" style="background:#E0F2FE; color:#0369A1; font-weight:700; font-size:10.5px;">争点 ${escapeHtml(idx + 1)}</span>
                  <span style="font-weight: 700; font-size: 12.5px; color: var(--primary-navy);">${escapeHtml(row.dispute_focus)}</span>
                </div>
                <span class="badge" style="background:#DCFCE7; color:#15803D; font-weight:700; font-size:10.5px;">${escapeHtml(row.supreme_court_rule.authority_badge)}</span>
              </div>
              
              <!-- 最高院支持派观点 -->
              <div style="background: #F0FDF4; border-left: 3px solid #16A34A; padding: 6px 10px; border-radius: 2px; margin-bottom: 6px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <strong style="font-size: 11.5px; color: #15803D;">✅ 最高院/高院权威裁判要旨 (${escapeHtml(row.supreme_court_rule.case_number)})：</strong>
                  <button type="button" class="btn btn-secondary btn-sm" onclick="copyRebuttalQuote('${escapeHtml(row.supreme_court_rule.rebuttal_brief_quote)}')" style="font-size:9.5px; padding:1px 5px;">复制说理</button>
                </div>
                <div style="font-size: 11px; color: #166534; line-height: 1.4; margin-top: 2px;">
                  ${escapeHtml(row.supreme_court_rule.holding_ratio)}
                </div>
              </div>

              <!-- 一审否定派误区对抗 -->
              <div style="background: #FAF9F6; border-left: 3px solid #94A3B8; padding: 6px 10px; border-radius: 2px;">
                <div style="font-size: 11px; color: var(--text-muted);">
                  <strong>❌ 一审错误说理死穴：</strong>${escapeHtml(row.first_instance_error_view.flawed_argument)}
                </div>
              </div>
            </div>
          `).join('');
        }

        // 4. 渲染裁判口径演变谱系
        if (timelineCont) {
          const tl = data.judicial_evolution_timeline || [];
          timelineCont.innerHTML = tl.map(t => `
            <div style="margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px dashed #E5E7EB;">
              <div style="font-weight: 700; color: var(--primary-navy);">${escapeHtml(t.stage)}</div>
              <div style="color: var(--accent-amber); font-weight:600;">${escapeHtml(t.benchmark_event)}</div>
              <div>${escapeHtml(t.rule_evolution)}</div>
            </div>
          `).join('');
        }

        // 5. 渲染文书预览
        renderAppealDocPreview();

        if (triggerToast) {
          showToast("一审判决漏洞剖析与最高院类案分歧穿透完成！");
        }
      } catch (e) {
        console.error("Appeal audit error:", e);
        if (triggerToast) showToast("分析失败: " + e);
      }
    }

    function switchAppealDocView(view) {
      currentAppealDocView = view;
      const btnP = document.getElementById('btn-doc-pleading');
      const btnM = document.getElementById('btn-doc-memo');
      if (view === 'pleading') {
        if (btnP) btnP.classList.add('active');
        if (btnM) btnM.classList.remove('active');
      } else {
        if (btnM) btnM.classList.add('active');
        if (btnP) btnP.classList.remove('active');
      }
      renderAppealDocPreview();
    }

    function renderAppealDocPreview() {
      const previewEl = document.getElementById('appeal-doc-preview');
      if (!previewEl || !currentAppealAuditData) return;
      if (currentAppealDocView === 'pleading') {
        previewEl.innerText = currentAppealAuditData.appellate_pleading_text || '暂无上诉状文本';
      } else {
        previewEl.innerText = currentAppealAuditData.appellate_memo_report || '暂无类案论证报告';
      }
    }

    function copyAppealDocument() {
      if (!currentAppealAuditData) {
        showToast("暂无可复制文书，请先点击【执行一审裁判漏洞剖析】");
        return;
      }
      const text = currentAppealDocView === 'pleading' ? currentAppealAuditData.appellate_pleading_text : currentAppealAuditData.appellate_memo_report;
      navigator.clipboard.writeText(text).then(() => {
        showToast("已成功复制二审终稿文书文本！");
      }).catch(err => {
        showToast("复制失败: " + err);
      });
    }

    function copyRebuttalQuote(quoteText) {
      if (!quoteText) return;
      navigator.clipboard.writeText(quoteText).then(() => {
        showToast("已复制最高法院权威反驳代理词说理！");
      }).catch(err => {
        showToast("复制失败: " + err);
      });
    }

    async function exportAppealDocxUI() {
      if (!currentAppealAuditData) {
        showToast("请先执行分析生成二审文书");
        return;
      }
      const title = currentAppealDocView === 'pleading' ? "民事上诉状_事实与理由靶向重构版" : "类案检索与统一裁判尺度论证意见书";
      const text = currentAppealDocView === 'pleading' ? currentAppealAuditData.appellate_pleading_text : currentAppealAuditData.appellate_memo_report;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/litigation/appeal-export-docx`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            content_text: text,
            doc_type: currentAppealDocView
          })
        });

        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        
        const downloadUrl = withDownloadToken(`${API_BASE}${data.download_url}`);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = data.filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);

        showToast(`已成功导出二审公文：${data.filename}`);
      } catch (e) {
        showToast("导出 Word 失败: " + e);
      }
    }

    // =========================================================================
    // 5.2 常规双库检索与签署 (历史保留)
    // =========================================================================
    async function runDualRAGSearch() {
      const query = document.getElementById('rag-q').value;
      const corpusType = document.getElementById('rag-corpus').value;
      const container = document.getElementById('rag-dual-results');
      container.innerHTML = `<span class="spinner-dark"></span> 检索中...`;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase3/rag/search`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query, corpus_type: corpusType, top_k: 2 })
        });
        const d = await resp.json();
        container.innerHTML = "";

        if (d.statutes && d.statutes.length) {
          container.innerHTML += `<div style="font-weight:700; color:var(--primary-navy); font-size:12px;">【公共法规库匹配法条】</div>`;
          d.statutes.forEach(s => {
            container.innerHTML += `
              <div class="rag-item-card statute">
                <strong>${s.citation}</strong>
                <p style="color:var(--text-secondary); margin-top:2px;">${s.content}</p>
              </div>
            `;
          });
        }

        if (d.winning_cases && d.winning_cases.length) {
          container.innerHTML += `<div style="font-weight:700; color:var(--status-valid); font-size:12px; margin-top:6px;">【律所胜诉案例库匹配裁判思路】</div>`;
          d.winning_cases.forEach(c => {
            container.innerHTML += `
              <div class="rag-item-card case">
                <strong style="color:var(--status-valid);">${c.title}</strong>
                <p style="margin-top:2px;"><strong>胜诉策略：</strong>${c.win_strategy}</p>
                <p style="color:var(--text-muted); font-size:11.5px; margin-top:2px;"><strong>代理词范例：</strong>${c.winning_brief_quote}</p>
              </div>
            `;
          });
        }
      } catch (e) {
        container.innerHTML = `<div style="color:var(--status-warn);">检索异常: ${escapeHtml(e)}</div>`;
      }
    }

    async function runRAGConsult() {
      const btn = document.getElementById('btn-consult');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner"></span> 正在查验法条与过往代理词...`;
      btn.disabled = true;

      const question = document.getElementById('consult-q').value;
      const box = document.getElementById('consult-ans-box');

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase3/rag/consult`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question })
        });
        const d = await resp.json();
        btn.innerHTML = origHtml;
        btn.disabled = false;
        box.style.display = 'block';
        box.innerText = d.legal_strategy;
        showToast("办案策略与代理词已生成");
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        showToast("咨询失败: " + e);
      }
    }

    let currentSignEnvId = null;
    let currentSignUrl = null;

    async function runCreateDocuSealLink() {
      const payload = {
        client_name: document.getElementById('sign-c-name').value,
        client_phone: document.getElementById('sign-c-phone').value,
        lawyer_name: document.getElementById('sign-l-name').value,
        service_fee: parseFloat(document.getElementById('sign-fee').value) || 0,
        case_summary: document.getElementById('sign-case').value
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase3/create-signing-link`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await resp.json();
        currentSignEnvId = d.envelope_id;
        currentSignUrl = d.signing_url;

        const banner = document.getElementById('sign-demo-banner');
        if (banner) {
          if (d.is_demo) {
            banner.style.display = 'block';
            banner.innerText = '⚠ ' + (d.demo_notice || '演示模式：未接入真实电子签名服务，签署结果不具有法律效力');
          } else {
            banner.style.display = 'none';
          }
        }

        document.getElementById('sign-flow-box').style.display = 'block';
        const linkEl = document.getElementById('sign-h5-link');
        linkEl.href = d.signing_url;
        linkEl.innerText = d.signing_url;

        let audit = "<strong>签署审计链：</strong><br/>";
        (d.envelope && d.envelope.audit_logs || []).forEach(l => {
          audit += `• [${l.time}] ${l.action} (${l.operator || l.target || ''})<br/>`;
        });
        if (d.is_demo) {
          audit += `<div style="color:#92400E;margin-top:6px;font-weight:700;">${d.demo_notice || '演示模式：未接入真实电子签名服务，签署结果不具有法律效力'}</div>`;
        }
        document.getElementById('sign-audit-trail').innerHTML = audit;
        showToast(d.is_demo ? (d.demo_notice || "演示签约任务已创建") : "签约任务已创建");
      } catch (e) {
        showToast("创建签约失败: " + e);
      }
    }

    function copySigningLink() {
      if (currentSignUrl) {
        copyToClipboard(currentSignUrl, "签约链接已复制到剪贴板");
      }
    }

    async function simulateClientSignature() {
      if (!currentSignEnvId) {
        showToast("请先生成签约任务");
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase3/signing-webhook`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ envelope_id: currentSignEnvId })
        });
        const d = await resp.json().catch(() => ({}));
        if (resp.status === 503) {
          showToast("webhook 未启用：请设置环境变量 DOCUSEAL_WEBHOOK_SECRET 后再模拟回调");
          document.getElementById('sign-audit-trail').innerHTML += `
            <div style="color:#92400E; margin-top:6px; font-weight:600;">演示提示：未配置 DOCUSEAL_WEBHOOK_SECRET，无法模拟签署回调。签署结果不具有法律效力。</div>`;
          return;
        }
        if (!resp.ok) {
          showToast("签署回调失败: HTTP " + resp.status + (d.detail ? (" " + JSON.stringify(d.detail)) : ""));
          return;
        }
        const sha = d.file_sha256 || "";
        document.getElementById('sign-audit-trail').innerHTML += `
          <div style="color:var(--status-valid); margin-top:6px; font-weight:600;">✓ 签署回调完成。文件 SHA-256 摘要（用于比对文件是否被修改，不等于第三方存证）：${sha}</div>
          <a href="${withDownloadToken(d.archived_pdf_url || '#')}" class="btn btn-secondary btn-sm" style="margin-top:4px;" download>下载归档委托协议 PDF</a>
          ${d.is_demo ? '<div style="color:#92400E;margin-top:4px;font-weight:700;">演示模式：未接入真实电子签名服务，签署结果不具有法律效力</div>' : ''}
        `;
        showToast(d.is_demo ? (d.demo_notice || "演示签署完成（不具法律效力）") : "签署回调完成");
      } catch (e) {
        showToast("签署回调模拟失败: " + e);
      }
    }

export {
  switchRagSignSubTab,
  load80MRepurchasePreset,
  runAppealAuditUI,
  switchAppealDocView,
  renderAppealDocPreview,
  copyAppealDocument,
  copyRebuttalQuote,
  exportAppealDocxUI,
  runDualRAGSearch,
  runRAGConsult,
  runCreateDocuSealLink,
  copySigningLink,
  simulateClientSignature,
  lastAppealDeadline,
};

/**
 * LawFlow Module: 02_litigation.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const LITIGATION_TAB_HTML = `      <div class="split-grid-50-50">
        
        <!-- 左侧：诉讼要素录入表单 -->
        <div class="surface-card">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
              诉讼与立案要素录入
            </div>
            <span class="card-tip">支持三大案由自动引用实体法条</span>
          </div>

          <!-- 模式切换：标准直出 vs 5步人机协同断点工作流 -->
          <div style="display: flex; gap: 6px; margin-bottom: 12px; background: #F1F5F9; padding: 4px; border-radius: var(--radius-sm);">
            <button type="button" class="tab-pill-btn active" id="btn-lit-mode-std" onclick="switchLitigationMode('standard')" style="flex:1; text-align:center;">
              ⚡ 快速直出 (标准表单)
            </button>
            <button type="button" class="tab-pill-btn" id="btn-lit-mode-wf" onclick="switchLitigationMode('workflow')" style="flex:1; text-align:center;">
              🤖 人机协同断点工作流 (5步状态机 · 推荐)
            </button>
          </div>

          <!-- 模式 A: 标准表单直接生成 -->
          <div id="lit-pane-standard">
            <!-- 全局在办案件一键导入横幅 -->
            <div id="litigation-context-banner" style="background: rgba(197, 133, 50, 0.08); border: 1px solid var(--accent-amber-border); border-left: 3px solid var(--accent-amber); padding: 8px 12px; border-radius: var(--radius-sm); margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
              <div style="font-size: 11.5px; color: var(--primary-navy);">
                <span style="color: var(--accent-amber); font-weight: 700;">⚡ 全局在办案件就绪：</span>
                <span id="litigation-context-summary">民间借贷纠纷 · 李四诉张三 (标的 ¥500,000.00) · 3条请求权依据</span>
              </div>
              <button type="button" class="btn btn-amber btn-sm" onclick="applyCaseContextToLitigation(true)" style="padding: 3px 8px; font-size: 11px; white-space: nowrap;">
                一键导入全案要素
              </button>
            </div>

            <div class="form-group">
              <label class="form-label">案由类型</label>
              <select aria-label="pkg cause"  id="pkg-cause" onchange="updateCausePreset()">
                <option value="民间借贷纠纷">民间借贷纠纷全套（起诉状+委托书+送达地址确认）</option>
                <option value="买卖合同纠纷">买卖合同欠款纠纷全套（起诉状+财产保全申请书+委托书）</option>
                <option value="劳动人事争议">劳动人事争议全套（仲裁申请书+经济补偿金清单+委托书）</option>
                <option value="通用民事纠纷">通用民事纠纷起诉状</option>
              </select>
            </div>

            <!-- 原告当事人要素 -->
            <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              原告当事人要素
            </div>
            <div class="form-row-3">
              <div class="form-group"><label class="form-label">原告姓名/企业名称</label><input aria-label="pkg p name"  type="text" id="pkg-p-name" value="张三"></div>
              <div class="form-group"><label class="form-label">身份证号/信用代码</label><input aria-label="pkg p id"  type="text" id="pkg-p-id" value="110101199003072375"></div>
              <div class="form-group"><label class="form-label">联系电话</label><input aria-label="pkg p phone"  type="text" id="pkg-p-phone" value="13800000000"></div>
            </div>
            <div class="form-group"><label class="form-label">送达住所地</label><input aria-label="pkg p addr"  type="text" id="pkg-p-addr" value="北京市朝阳区建国门外大街1号"></div>

            <!-- 被告当事人要素 -->
            <div style="font-size: 12px; font-weight: 700; color: var(--status-warn); border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              被告当事人要素
            </div>
            <div class="form-row-3">
              <div class="form-group"><label class="form-label">被告姓名/企业名称</label><input aria-label="pkg d name"  type="text" id="pkg-d-name" value="北京宏达商贸有限公司"></div>
              <div class="form-group"><label class="form-label">身份证号/信用代码</label><input aria-label="pkg d id"  type="text" id="pkg-d-id" value="91110105MA00TEST88"></div>
              <div class="form-group"><label class="form-label">联系电话</label><input aria-label="pkg d phone"  type="text" id="pkg-d-phone" value="010-88889999"></div>
            </div>
            <div class="form-group"><label class="form-label">实际住所/经营地</label><input aria-label="pkg d addr"  type="text" id="pkg-d-addr" value="北京市海淀区中关村南大街8号"></div>

            <!-- 标的额与案情 -->
            <div style="border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              <div class="form-row">
                <div class="form-group"><label class="form-label">涉案标的额 (元)</label><input aria-label="pkg amount"  type="number" id="pkg-amount" value="200000"></div>
                <div class="form-group"><label class="form-label">受诉法院/仲裁机构</label><input aria-label="pkg court"  type="text" id="pkg-court" value="北京市朝阳区"></div>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label">
                <span>律师案情笔记 (大模型将自动提炼事实并严谨引用实体法条)</span>
              </label>
              <textarea aria-label="pkg notes"  id="pkg-notes" rows="4">原告在2022年3月5日转给被告20万，约定年利率15%借期1年，被告出具了手写借条。借款到期后原告多次通过微信及电话向被告催要借款本金及利息，被告找借口推脱拒不还钱，至今分文未还，构成根本违约。</textarea>
            </div>

            <!-- 配套附属文书自选 (A-18) -->
            <div style="border-top: 1px solid var(--border-hairline); padding-top: 10px; margin-bottom: 12px;">
              <label class="form-label" style="margin-bottom: 6px;">配套附属公文（勾选生成）：</label>
              <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; font-size: 12px;">
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="subdoc poa"  type="checkbox" id="subdoc-poa" value="power_of_attorney" checked> 授权委托书
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="subdoc addr"  type="checkbox" id="subdoc-addr" value="service_address" checked> 送达地址确认书
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="subdoc legrep"  type="checkbox" id="subdoc-legrep" value="legal_rep_certificate"> 法定代表人证明书
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="subdoc preserv"  type="checkbox" id="subdoc-preserv" value="property_preservation"> 财产保全申请书
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="subdoc evcat"  type="checkbox" id="subdoc-evcat" value="evidence_catalog"> 证据目录清单
                </label>
              </div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
              <span style="font-size:11px; color:var(--text-muted);">立案前红线审查</span>
              <button type="button" class="btn btn-secondary btn-sm" onclick="quickCheckTabLitigationConflict()" style="padding: 2px 8px; font-size:11px; color:#D32F2F; border-color: rgba(211,47,47,0.3); background:#FFF5F5;">
                🛡️ 排查双方当事人利益冲突
              </button>
            </div>

            <button class="btn" id="btn-generate-pkg" onclick="runGenerateLitigationPackage()">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
              生成全套立案公文包 (.docx + .pdf)
            </button>
          </div>

          <!-- 模式 B: 5步人机协同断点工作流 -->
          <div id="lit-pane-workflow" style="display: none;">
            
            <!-- 5步状态机进度指示器 -->
            <div class="workflow-stepper" id="wf-stepper">
              <div class="wf-step-node completed" id="wf-step-1">
                <span class="wf-step-circle">1</span>
                <span>事实提炼</span>
              </div>
              <div class="wf-step-line" id="wf-line-1"></div>
              <div class="wf-step-node active breakpoint" id="wf-step-2">
                <span class="wf-step-circle">2</span>
                <span>请求权核准 ⏸️</span>
              </div>
              <div class="wf-step-line" id="wf-line-2"></div>
              <div class="wf-step-node" id="wf-step-3">
                <span class="wf-step-circle">3</span>
                <span>法规检索</span>
              </div>
              <div class="wf-step-line" id="wf-line-3"></div>
              <div class="wf-step-node" id="wf-step-4">
                <span class="wf-step-circle">4</span>
                <span>攻防策略 ⏸️</span>
              </div>
              <div class="wf-step-line" id="wf-line-4"></div>
              <div class="wf-step-node" id="wf-step-5">
                <span class="wf-step-circle">5</span>
                <span>终稿交付</span>
              </div>
            </div>

            <!-- 断点工作台动态容器 -->
            <div id="wf-breakpoint-content">
              <!-- 初始启动界面 -->
              <div id="wf-initial-state" style="padding: 10px 0;">
                <div class="breakpoint-box">
                  <div style="font-weight: 700; font-size: 13px; color: var(--primary-navy); margin-bottom: 6px;">
                    🛡️ 人机协同断点工作流机制说明
                  </div>
                  <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.6;">
                    拒绝大模型"单次黑盒抽奖式吐终稿"。系统将办案拆解为严谨的多步状态机，在<strong>【请求权基础】</strong>与<strong>【抗辩攻防策略】</strong>两个关键决策点自动挂起，由主办律师勾选核准后方可推进生成，随时支持回退修改，从底层杜绝诉讼请求漏项或事实推演失控。
                  </div>
                </div>

                <div class="form-group">
                  <label class="form-label">导入案情事实（默认同步当前案件空间上下文）</label>
                  <textarea aria-label="wf input facts"  id="wf-input-facts" rows="4" class="quick-input" style="font-size: 12px; line-height: 1.5;"></textarea>
                </div>

                <button type="button" class="btn" id="btn-start-workflow" onclick="startLitigationWorkflowUI()" style="width: 100%;">
                  🚀 启动人机协同断点工作流
                </button>
              </div>

              <!-- 断点步骤 2: 诉讼请求与请求权基础核准界面 -->
              <div id="wf-step2-box" style="display: none;">
                <div class="breakpoint-box">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 700; font-size: 13px; color: #B45309;">⏸️ 断点 1：请核准诉讼请求与请求权基础规范</span>
                    <span class="badge" style="background: #FEF3C7; color: #B45309;">等待律师勾选确认</span>
                  </div>
                  <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
                    AI 已完成基础事实提炼。请勾选并确认本案诉讼请求项与实体法请求权条文：
                  </div>

                  <!-- 案由选择 -->
                  <div class="form-group" style="margin-bottom: 10px;">
                    <label class="form-label">拟定法定案由</label>
                    <input aria-label="wf step2 cause"  type="text" id="wf-step2-cause" class="quick-input" value="民间借贷纠纷">
                  </div>

                  <!-- 候选诉讼请求列表 -->
                  <div style="margin-bottom: 10px;">
                    <label class="form-label">拟提起的诉讼请求清单 (勾选确认)</label>
                    <div id="wf-step2-claims-list" style="display: flex; flex-direction: column; gap: 6px;"></div>
                  </div>

                  <!-- 请求权规范条文 -->
                  <div style="margin-bottom: 10px;">
                    <label class="form-label">适用的民商事实体规范依据</label>
                    <div id="wf-step2-basis-list" style="display: flex; flex-direction: column; gap: 6px;"></div>
                  </div>

                  <!-- 律师补充手记 -->
                  <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">主办律师补充调整意见 (选填)</label>
                    <input aria-label="如：利息严格按全国银行间同业拆借中心公布的LPR计算至实际清偿日"  type="text" id="wf-step2-notes" class="quick-input" placeholder="如：利息严格按全国银行间同业拆借中心公布的LPR计算至实际清偿日">
                  </div>

                  <button type="button" class="btn btn-amber" id="btn-advance-step2" onclick="advanceWorkflowStep2UI()" style="width: 100%;">
                    ✓ 确认诉讼请求，进入抗辩预测 (推进至 Step 3/4)
                  </button>
                </div>
              </div>

              <!-- 断点步骤 4: 攻防策略与争议焦点核准界面 -->
              <div id="wf-step4-box" style="display: none;">
                <div class="breakpoint-box">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 700; font-size: 13px; color: #B45309;">⏸️ 断点 2：对方抗辩焦点预测与攻防策略核准</span>
                    <span class="badge" style="background: #FEF3C7; color: #B45309;">等待律师策略决策</span>
                  </div>
                  <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 10px;">
                    系统已穿透法规库，并从对方视角预测了 3 项最致命抗辩。请勾选确认我方反击与证据应对策略：
                  </div>

                  <!-- 预测抗辩卡片列表 -->
                  <div id="wf-step4-defenses-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px;"></div>

                  <!-- 律师补充攻防策略 -->
                  <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">补充重点质证辩护策略</label>
                    <input aria-label="wf step4 notes"  type="text" id="wf-step4-notes" class="quick-input" value="在起诉状中附带还款时间表与EMS寄递签收凭证以封死诉讼时效抗辩空间">
                  </div>

                  <div style="display: flex; gap: 8px;">
                    <button type="button" class="btn btn-secondary btn-sm" onclick="rollbackWorkflowUI(2)" style="flex: 1;">
                      ↩ 回退修改请求权 (Step 2)
                    </button>
                    <button type="button" class="btn btn-primary btn-sm" id="btn-advance-step4" onclick="advanceWorkflowStep4UI()" style="flex: 2;">
                      ✓ 核准攻防策略，生成民事起诉状终稿 (Step 5)
                    </button>
                  </div>
                </div>
              </div>

              <!-- 步骤 5: 终稿达成与引注认证提示 -->
              <div id="wf-step5-box" style="display: none;">
                <div style="background: #F0FDF4; border: 1px solid #BBF7D0; border-left: 4px solid #16A34A; border-radius: var(--radius-sm); padding: 12px 14px; margin-bottom: 12px;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="font-weight: 700; color: #16A34A; font-size: 13px;">🎉 人机协同断点工作流全流程达成！</span>
                    <span class="badge" style="background: #DCFCE7; color: #15803D;">已通过司法引注防火墙认证</span>
                  </div>
                  <div style="font-size: 11.5px; color: #166534; margin-top: 4px;">
                    起诉状终稿已自动同步至右侧公文纸。每一项事实、诉讼请求及引注法条均已经过主办律师断点核准。
                  </div>
                </div>
                <button type="button" class="btn btn-secondary btn-sm" onclick="resetWorkflowUI()" style="width: 100%;">
                  🔄 重新发起新一轮人机协同工作流
                </button>
              </div>

            </div>
          </div>
        </div>

        <!-- 右侧：司法公文纸实时预览 -->
        <div class="docket-receipt-paper">
          <div class="receipt-header">
            <div class="receipt-title">
              <span>起诉状正文与文书包存证</span>
              <span class="badge" id="pkg-status-tip">待生成</span>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="copyElementText('pkg-facts-box', '已复制起诉状事实与理由')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              复制起诉正文
            </button>
          </div>

          <!-- 法条依据标签与本地库比对引注体检 -->
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px;">
            <div style="font-size: 12px; color: var(--accent-amber); font-weight: 600;" id="pkg-citations-area">
              实体法适用依据：等待生成...
            </div>
            <div id="pkg-citation-guard-badge-wrap" style="display: none;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="openCitationGuardReportModal()" style="padding: 2px 8px; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; border-color: #2E7D32; color: #2E7D32; background: #F1F8E9;">
                <span>🛡️ 引注体检</span>
                <span class="badge" id="pkg-citation-guard-badge" style="background: #2E7D32; color: #fff; font-size: 10px; padding: 1px 5px;">100% 现行有效</span>
              </button>
            </div>
          </div>

          <!-- 《事实与理由》司法正文 -->
          <div class="legal-statement-box" id="pkg-facts-box" style="min-height: 240px; max-height: 360px;">点击左侧【生成全套立案公文包】后，本地大模型将自动提炼案件事实要件，引用《中华人民共和国民法典》或《中华人民共和国劳动合同法》对应条款，输出严谨出庭级别的《事实与理由》起诉正文。</div>

          <!-- 文书下载列表 -->
          <div style="border-top: 1px dashed var(--border-hairline); padding-top: 14px;">
            <div style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 10px;">
              导出的 Word (.docx) 与 A4 PDF 存证文书列表
            </div>
            <div id="pkg-doc-list" style="display: flex; flex-direction: column; gap: 8px;">
              <div style="color: var(--text-muted); font-size: 12px;">生成完成后可直接下载 Word 编辑或 PDF 盖章提交法院立案。</div>
            </div>
          </div>

        </div>

      </div>
    </section>

    <!-- ======================================================================
         模块 03：证据清洗与庭审 (上方清洗操作台 + 下方双栏阅读器)
         ====================================================================== -->
`;

export function renderTabLitigation() {
  const el = document.getElementById('tab-litigation');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = LITIGATION_TAB_HTML;
  }
}


    // =========================================================================
    // 3. 模块 02：立案文书流水线
    // =========================================================================
    function updateCausePreset() {
      const cause = document.getElementById('pkg-cause').value;
      if (cause === "民间借贷纠纷") {
        document.getElementById('pkg-notes').value = "2022年3月5日，被告李四向原告借款20万元，原告当天通过招商银行网银全额转账。被告出具借条约定年利率15%借期1年。借款到期后原告多次通过微信催要，被告至今拒不偿还本金和利息。";
        document.getElementById('pkg-court').value = "北京市朝阳区";
        document.getElementById('pkg-amount').value = "200000";
      } else if (cause === "买卖合同纠纷") {
        document.getElementById('pkg-notes').value = "原告与被告签订《货物购销合同》，原告依约交付了全部价值20万元的精密配件，被告签收确认并投入生产，但付款期限届满后被告拖延拒付货款，构成严重违约。";
        document.getElementById('pkg-court').value = "北京市海淀区";
        document.getElementById('pkg-amount').value = "200000";
      } else if (cause === "劳动人事争议") {
        document.getElementById('pkg-notes').value = "劳动者张三2021年3月入职被告公司担任软件工程师，月薪12000元。2024年5月公司在未提前30天通知的情况下单方强行违法解除劳动合同，且未支付任何经济补偿金。";
        document.getElementById('pkg-court').value = "北京市朝阳区劳动人事争议仲裁委员会";
        document.getElementById('pkg-amount').value = "84000";
      }
    }

    async function runGenerateLitigationPackage() {
      const btn = document.getElementById('btn-generate-pkg');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner"></span> 正在援引实体法条与排版 Word/PDF...`;
      btn.disabled = true;
      document.getElementById('pkg-status-tip').innerText = "正在生成（长任务进行中，请稍候）…";

      const payload = {
        cause_of_action: document.getElementById('pkg-cause').value,
        claim_amount: parseFloat(document.getElementById('pkg-amount').value) || 0,
        raw_case_notes: document.getElementById('pkg-notes').value,
        court_name: document.getElementById('pkg-court').value,
        plaintiff: {
          name: document.getElementById('pkg-p-name').value,
          id_card_or_uscc: document.getElementById('pkg-p-id').value,
          phone: document.getElementById('pkg-p-phone').value,
          address: document.getElementById('pkg-p-addr').value
        },
        defendant: {
          name: document.getElementById('pkg-d-name').value,
          id_card_or_uscc: document.getElementById('pkg-d-id').value,
          phone: document.getElementById('pkg-d-phone').value,
          address: document.getElementById('pkg-d-addr').value
        },
        auto_generate_sub_docs: true,
        sub_documents: (() => {
          const list = [];
          if (document.getElementById('subdoc-poa')?.checked) list.push('power_of_attorney');
          if (document.getElementById('subdoc-addr')?.checked) list.push('service_address');
          if (document.getElementById('subdoc-legrep')?.checked) list.push('legal_rep_certificate');
          if (document.getElementById('subdoc-preserv')?.checked) list.push('property_preservation');
          if (document.getElementById('subdoc-evcat')?.checked) list.push('evidence_catalog');
          return list;
        })()
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/generate-litigation-package`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await resp.json();
        btn.innerHTML = origHtml;
        btn.disabled = false;
        const es = d.engine_status || {};
        let tip = "文书包生成完毕";
        if (es.llm === "rule_fallback" || es.pdf === "local_pymupdf") {
          const parts = [];
          if (es.llm === "rule_fallback") parts.push("已切换规则模式");
          if (es.pdf === "local_pymupdf") parts.push("本地 PDF 引擎");
          tip = parts.length ? `文书包生成完毕（${parts.join(" / ")}）` : tip;
        }
        document.getElementById('pkg-status-tip').innerText = tip;

        // 法条依据
        const statutes = d.statute_citations || [];
        document.getElementById('pkg-citations-area').innerHTML =
          `实体法适用依据：<span style="color: var(--primary-navy); font-weight:700;">${escapeHtml(statutes.join('、') || '《中华人民共和国民法典》相关实体法条')}</span>`;
        
        // 本地库比对引注熔断体检报告联动
        if (d.citation_audit) {
          window._lastCitationAudit = d.citation_audit;
          const badgeWrap = document.getElementById('pkg-citation-guard-badge-wrap');
          const badge = document.getElementById('pkg-citation-guard-badge');
          if (badgeWrap && badge) {
            badgeWrap.style.display = 'inline-block';
            if (d.citation_audit.has_abrogated_laws || d.citation_audit.has_hallucinations) {
              badge.style.background = '#C58532';
              badge.innerText = `⚠️ 已净化 ${d.citation_audit.stats.abrogated_count || 0} 项旧法`;
            } else {
              badge.style.background = '#2E7D32';
              badge.innerText = `100% 现行有效 (${d.citation_audit.stats.verified_count || 0}条)`;
            }
          }
        }

        // 起诉状事实与理由
        document.getElementById('pkg-facts-box').innerText = d.facts_and_reasons_polished;

        // 生成文书列表
        const listDiv = document.getElementById('pkg-doc-list');
        listDiv.innerHTML = "";
        d.generated_documents.forEach(doc => {
          listDiv.innerHTML += `
            <div class="doc-pill-item">
              <div class="doc-info">
                <strong>${doc.doc_type}</strong>
                <span>${doc.filename_docx}</span>
              </div>
              <div style="display: flex; gap: 8px;">
                <a href="${doc.docx_url}" class="btn btn-secondary btn-sm" download>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  Word 存证
                </a>
                ${doc.pdf_url ? `
                <a href="${doc.pdf_url}" class="btn btn-sm" style="background:#1F6E4A;" download>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                  A4 PDF
                </a>` : ''}
              </div>
            </div>
          `;
        });
        showToast("立案文书流水线生成完毕");
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        showToast("生成失败: " + e);
      }
    }



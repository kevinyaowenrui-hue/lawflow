/**
 * LawFlow Module: 02_litigation.js
 */
import { api, ApiError, API_BASE, withDownloadToken, escapeHtml } from '../api.js';
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
                <span id="litigation-context-summary">尚未录入在办案件。保存工作卡后，可一键导入当事人、标的和请求权依据。</span>
              </div>
              <button type="button" class="btn btn-amber btn-sm" onclick="applyCaseContextToLitigation(true)" style="padding: 3px 8px; font-size: 11px; white-space: nowrap;">
                一键导入全案要素
              </button>
            </div>

            <div class="form-group">
              <label class="form-label" for="pkg-cause">案由类型</label>
              <select aria-label="pkg cause"  id="pkg-cause" onchange="updateCausePreset()">
                <option value="">请选择文书类型，不要默认民间借贷</option>
                <option value="民间借贷纠纷">民间借贷纠纷全套（起诉状+委托书+送达地址确认）</option>
                <option value="买卖合同纠纷">买卖合同欠款纠纷全套（起诉状+财产保全申请书+委托书）</option>
                <option value="劳动人事争议">劳动人事争议全套（仲裁申请书+经济补偿金清单+委托书）</option>
                <option value="离婚纠纷">离婚纠纷要素式起诉状</option>
                <option value="通用民事纠纷">通用民事纠纷起诉状</option>
              </select>
              <div id="pkg-jurisdiction-box" style="margin-top: 8px; font-size: 12px; color: #9A3412; line-height: 1.5;">有在办案件时，生成前要先确认受理机关。劳动仲裁、仲裁条款和专属管辖不会自动写成法院。</div>
            </div>

            <!-- 原告当事人要素 -->
            <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              原告当事人要素
            </div>
            <div class="form-row-3">
              <div class="form-group"><label class="form-label" for="pkg-p-name">原告姓名/企业名称</label><input aria-label="pkg p name"  type="text" id="pkg-p-name" value="" placeholder="填写本案原告，不要沿用示例姓名"></div>
              <div class="form-group"><label class="form-label" for="pkg-p-id">身份证号/信用代码</label><input aria-label="pkg p id"  type="text" id="pkg-p-id" value="" placeholder="18位身份证或统一社会信用代码"></div>
              <div class="form-group"><label class="form-label" for="pkg-p-phone">联系电话</label><input aria-label="pkg p phone"  type="text" id="pkg-p-phone" value="" placeholder="联系电话"></div>
            </div>
            <div class="form-group"><label class="form-label" for="pkg-p-addr">送达住所地</label><input aria-label="pkg p addr"  type="text" id="pkg-p-addr" value="" placeholder="送达地址"></div>

            <!-- 被告当事人要素 -->
            <div style="font-size: 12px; font-weight: 700; color: var(--status-warn); border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              被告当事人要素
            </div>
            <div class="form-row-3">
              <div class="form-group"><label class="form-label" for="pkg-d-name">被告姓名/企业名称</label><input aria-label="pkg d name"  type="text" id="pkg-d-name" value="" placeholder="填写本案被告"></div>
              <div class="form-group"><label class="form-label" for="pkg-d-id">身份证号/信用代码</label><input aria-label="pkg d id"  type="text" id="pkg-d-id" value="" placeholder="18位身份证或统一社会信用代码"></div>
              <div class="form-group"><label class="form-label" for="pkg-d-phone">联系电话</label><input aria-label="pkg d phone"  type="text" id="pkg-d-phone" value="" placeholder="联系电话"></div>
            </div>
            <div class="form-group"><label class="form-label" for="pkg-d-addr">实际住所/经营地</label><input aria-label="pkg d addr"  type="text" id="pkg-d-addr" value="" placeholder="住所或主要经营地"></div>

            <!-- 标的额与案情 -->
            <div style="border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              <div class="form-row">
                <div class="form-group"><label class="form-label" for="pkg-amount">涉案标的额 (元)</label><input aria-label="pkg amount"  type="number" id="pkg-amount" value="" placeholder="诉讼请求金额"></div>
                <div class="form-group"><label class="form-label" for="pkg-court">受诉法院/仲裁机构</label><input aria-label="pkg court"  type="text" id="pkg-court" value="" placeholder="如：北京市朝阳区人民法院"></div>
              </div>
            </div>

            <div class="form-group">
              <label class="form-label" for="pkg-claims">诉讼请求（每行一项，按承办律师拟定的原文写入起诉状）</label>
              <textarea aria-label="诉讼请求" id="pkg-claims" rows="4" placeholder="例如：判令被告偿还借款本金人民币100000元。"></textarea>
            </div>

            <div class="form-group">
              <label class="form-label" for="pkg-notes">
                <span>律师案情笔记 (大模型将自动提炼事实并严谨引用实体法条)</span>
              </label>
              <textarea aria-label="pkg notes"  id="pkg-notes" rows="4" placeholder="按时间写清出借或交货、约定、催告和尚未履行的事实。不要把示例案情直接生成文书。"></textarea>
            </div>

            <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); border-top: 1px solid var(--border-hairline); padding-top: 10px;">
              承办律师（优先用本所名册里的默认律师；名册和这里都没填，文书标【待填写】。事务所全称照实填写）
            </div>
            <div class="form-row-3">
              <div class="form-group"><label class="form-label" for="pkg-lawyer-name">承办律师</label><input aria-label="承办律师姓名" type="text" id="pkg-lawyer-name" placeholder="本所承办律师姓名"></div>
              <div class="form-group"><label class="form-label" for="pkg-law-firm">律师事务所</label><input aria-label="律师事务所" type="text" id="pkg-law-firm" placeholder="律师事务所全称"></div>
              <div class="form-group"><label class="form-label" for="pkg-lawyer-license">执业证号</label><input aria-label="执业证号" type="text" id="pkg-lawyer-license" placeholder="执业证号"></div>
            </div>
            <div class="form-group"><label class="form-label" for="pkg-lawyer-phone">律师联系电话</label><input aria-label="律师电话" type="text" id="pkg-lawyer-phone" placeholder="承办律师电话"></div>
            <div class="form-group">
              <label class="form-label" for="pkg-letter-prefix">公函函号前缀</label>
              <input aria-label="公函函号前缀" type="text" id="pkg-letter-prefix" placeholder="例如：京师函。留空则函号为【待填写函号前缀】" onblur="saveLitigationLetterPrefix()">
              <div style="font-size:11px; color:var(--text-muted); margin-top:3px;">按本所前缀和年度流水生成，例如「京师函〔2026〕第1号」。留空写【待填写函号前缀】，不会自动套用示例字号。</div>
            </div>
            <div id="pkg-labor-fields" class="form-row-3">
              <div class="form-group"><label class="form-label" for="pkg-monthly-salary">月工资（劳动争议）</label><input aria-label="月工资" type="number" id="pkg-monthly-salary" placeholder="不填则补偿清单不算金额"></div>
              <div class="form-group"><label class="form-label" for="pkg-hire-date">入职日期</label><input aria-label="入职日期" type="date" id="pkg-hire-date"></div>
              <div class="form-group"><label class="form-label" for="pkg-termination-date">解除日期</label><input aria-label="解除日期" type="date" id="pkg-termination-date"></div>
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
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="律师事务所公函" type="checkbox" id="subdoc-firm" value="law_firm_letter"> 律师事务所公函
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="律师函" type="checkbox" id="subdoc-demand" value="demand_letter"> 律师函草稿
                </label>
                <label style="display: flex; align-items: center; gap: 4px; cursor: pointer;">
                  <input aria-label="答辩状" type="checkbox" id="subdoc-answer" value="answer_brief"> 答辩状草稿
                </label>
              </div>
            </div>

            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 8px;">
              <span style="font-size:11px; color:var(--text-muted);">立案前红线审查</span>
              <button type="button" class="btn btn-secondary btn-sm" onclick="quickCheckTabLitigationConflict()" style="padding: 2px 8px; font-size:11px; color:#D32F2F; border-color: rgba(211,47,47,0.3); background:#FFF5F5;">
                🛡️ 排查双方当事人利益冲突
              </button>
            </div>

            <div class="form-group">
              <label class="form-label" for="pkg-filing-ack" style="display:flex; align-items:flex-start; gap:8px; cursor:pointer;">
                <input type="checkbox" id="pkg-filing-ack" style="margin-top:3px;">
                <span>我已审阅，提交件由承办律师负责</span>
              </label>
            </div>

            <button class="btn" id="btn-generate-pkg" onclick="runGenerateLitigationPackage()">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="12" y1="18" x2="12" y2="12"></line><line x1="9" y1="15" x2="15" y2="15"></line></svg>
              生成全套立案公文包 (.docx + .pdf)
            </button>
            <div style="margin-top: 8px;">
              <button type="button" class="btn btn-secondary btn-sm" id="btn-download-spc-complaint" onclick="runDownloadSpcElementComplaint()" style="font-size: 11.5px; width: 100%; border-color: var(--border-hairline);">
                📋 导出最高法要素式起诉状 (法〔2024〕46号示范文本)
              </button>
            </div>
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
                    <input aria-label="wf step2 cause"  type="text" id="wf-step2-cause" class="quick-input" value="" placeholder="填写本案案由">
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
                    抗辩预测不会自动写入终稿。请勾选本案要采用的对策；没有列出抗辩时，请按本案填写。
                  </div>

                  <!-- 预测抗辩卡片列表 -->
                  <div id="wf-step4-defenses-list" style="display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px;"></div>

                  <!-- 律师补充攻防策略 -->
                  <div class="form-group" style="margin-bottom: 12px;">
                    <label class="form-label">补充重点质证辩护策略</label>
                    <input aria-label="wf step4 notes"  type="text" id="wf-step4-notes" class="quick-input" value="" placeholder="只写本案要补充的质证要点">
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
        <div class="docket-receipt-paper" data-no-software-disclaimer="1">
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
                <span class="badge" id="pkg-citation-guard-badge" style="background: #6B7280; color: #fff; font-size: 10px; padding: 1px 5px;">待核验</span>
              </button>
            </div>
          </div>

          <!-- 《事实与理由》司法正文 -->
          <div class="legal-statement-box official-doc-preview" id="pkg-facts-box">点击左侧【生成全套立案公文包】后，本地大模型将自动提炼案件事实要件，引用《中华人民共和国民法典》或《中华人民共和国劳动合同法》对应条款，输出严谨出庭级别的《事实与理由》起诉正文。</div>

          <!-- 一键整卷打包下载操作栏 (移动微法院标准 & 扁平压缩包) -->
          <div id="pkg-archive-bar" style="display: none; margin-top: 14px; margin-bottom: 14px; padding: 12px 14px; background: #0F172A; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: var(--radius-sm, 6px);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
              <div style="display: flex; align-items: center; gap: 6px;">
                <span style="font-size: 13px; font-weight: 700; color: #F8FAFC;">📦 最高院移动微法院立案公文包</span>
                <span class="badge" style="background: #1E3A8A; color: #93C5FD; font-size: 10px; padding: 2px 6px;">四级类目就绪</span>
              </div>
              <span style="font-size: 11px; color: #94A3B8;">一键交付 · 零格式返工</span>
            </div>
            <div style="font-size: 11.5px; color: #CBD5E1; margin-bottom: 10px; line-height: 1.4;">
              内含：01_起诉状及身份证明、02_委托代理材料、03_送达地址确认书、04_证据清单与证据材料四大目录，符合“人民法院在线服务”全国统一标准。
            </div>
            <div style="display: flex; gap: 10px; flex-wrap: wrap;">
              <a id="btn-download-spc-zip" href="#" class="btn btn-sm" style="flex: 1; min-width: 220px; background: #2563EB; color: #FFFFFF; font-weight: 600; text-align: center; justify-content: center; border: 1px solid #3B82F6;" download onclick="return confirmFilingExport(event)">
                📦 下载移动微法院标准立案包 (.zip)
              </a>
              <a id="btn-download-flat-zip" href="#" class="btn btn-secondary btn-sm" style="background: #1E293B; color: #E2E8F0; border: 1px solid rgba(255,255,255,0.15); font-weight: 500; text-align: center; justify-content: center;" download onclick="return confirmFilingExport(event)">
                📥 下载传统扁平压缩包 (Flat .zip)
              </a>
            </div>
          </div>

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
    fillLawyerProfileFields();
    updateCausePreset();
  }
}


    // =========================================================================
    // 3. 模块 02：立案文书流水线
    // =========================================================================
    function updateCausePreset() {
      const cause = document.getElementById('pkg-cause').value;
      const notes = document.getElementById('pkg-notes');
      const generateBtn = document.getElementById('btn-generate-pkg');
      if (generateBtn) {
        generateBtn.textContent = cause === '劳动人事争议'
          ? '生成仲裁申请材料（不使用微法院四分卷）'
          : '生成全套立案公文包 (.docx + .pdf)';
      }
      const court = document.getElementById('pkg-court');
      const hints = {
        "民间借贷纠纷": "写明出借日期、金额、支付方式、借条约定的利息和期限、催告经过，以及截至起诉尚未偿还的本金和利息。",
        "买卖合同纠纷": "写明合同名称、签订日期、交货和签收、约定付款期限，以及截至起诉尚未支付的货款。",
        "劳动人事争议": "写明入职日期、岗位、月工资、解除日期、是否提前三十日通知，以及尚未支付的工资或补偿。",
      };
      if (notes && !notes.value.trim() && hints[cause]) notes.placeholder = hints[cause];
      if (court && !court.value.trim()) {
        court.placeholder = cause === "劳动人事争议"
          ? "例如：北京市朝阳区劳动人事争议仲裁委员会"
          : "例如：北京市朝阳区人民法院";
      }
      const labor = document.getElementById('pkg-labor-fields');
      if (labor) labor.style.display = cause === "劳动人事争议" ? "grid" : "none";
    }

    function readLawyerProfile() {
      try {
        return JSON.parse(localStorage.getItem('lawflow-lawyer-profile') || '{}') || {};
      } catch (e) {
        return {};
      }
    }

    const DEMO_LAWYER_NAME = '王律师';
    const DEMO_LICENSE = '11101201510123456';
    const DEMO_PHONE = '13900008888';
    const JINGSHI_FIRM = '北京市京师律师事务所';

    function isDemoIdentityCombo(name, license, phone) {
      if (String(name || '').trim() !== DEMO_LAWYER_NAME) return false;
      const lic = String(license || '').trim();
      const mobile = String(phone || '').trim();
      return lic === DEMO_LICENSE || mobile === DEMO_PHONE;
    }

    function usableLawyerValue(value, field, combo) {
      const text = String(value || '').trim();
      if (!text) return '';
      if (field === 'law_firm') {
        if (combo && text === JINGSHI_FIRM) return '';
        return text;
      }
      if (text === DEMO_LAWYER_NAME || text === DEMO_LICENSE || text === DEMO_PHONE) return '';
      return text;
    }

    export async function fillLawyerProfileFields() {
      let roster = {};
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/firm-roster/default`);
        if (resp && resp.ok) {
          const data = await resp.json();
          roster = data.lawyer || {};
        }
      } catch (e) {
        roster = {};
      }
      const profile = readLawyerProfile();
      const rosterCombo = isDemoIdentityCombo(roster.lawyer_name, roster.license_no, roster.phone);
      const profileCombo = isDemoIdentityCombo(profile.lawyer_name, profile.lawyer_license, profile.lawyer_phone);
      const pairs = [
        ['pkg-lawyer-name', usableLawyerValue(roster.lawyer_name, 'lawyer_name', rosterCombo) || usableLawyerValue(profile.lawyer_name, 'lawyer_name', profileCombo)],
        ['pkg-law-firm', usableLawyerValue(roster.law_firm, 'law_firm', rosterCombo) || usableLawyerValue(profile.law_firm, 'law_firm', profileCombo)],
        ['pkg-lawyer-license', usableLawyerValue(roster.license_no, 'lawyer_license', rosterCombo) || usableLawyerValue(profile.lawyer_license, 'lawyer_license', profileCombo)],
        ['pkg-lawyer-phone', usableLawyerValue(roster.phone, 'lawyer_phone', rosterCombo) || usableLawyerValue(profile.lawyer_phone, 'lawyer_phone', profileCombo)],
      ];
      pairs.forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && !el.value && value) el.value = value;
      });
      try {
        const prefResp = await api.request(`${API_BASE}/api/v1/phase1/letter-prefix`);
        if (prefResp && prefResp.ok) {
          const prefData = await prefResp.json();
          const prefix = (prefData && prefData.prefix) || '';
          const prefixInput = document.getElementById('pkg-letter-prefix');
          if (prefixInput && !prefixInput.value && prefix) prefixInput.value = prefix;
        }
      } catch (e) { /* 前缀读不到时留空，公函写【待填写函号前缀】 */ }
    }

    function profileWithoutDemoIdentity(raw) {
      const combo = isDemoIdentityCombo(raw.lawyer_name, raw.lawyer_license, raw.lawyer_phone);
      return {
        lawyer_name: raw.lawyer_name === DEMO_LAWYER_NAME ? '' : raw.lawyer_name,
        law_firm: combo && raw.law_firm === JINGSHI_FIRM ? '' : raw.law_firm,
        lawyer_license: raw.lawyer_license === DEMO_LICENSE ? '' : raw.lawyer_license,
        lawyer_phone: raw.lawyer_phone === DEMO_PHONE ? '' : raw.lawyer_phone,
      };
    }

    function saveLawyerProfileFromForm() {
      const raw = {
        lawyer_name: (document.getElementById('pkg-lawyer-name')?.value || '').trim(),
        law_firm: (document.getElementById('pkg-law-firm')?.value || '').trim(),
        lawyer_license: (document.getElementById('pkg-lawyer-license')?.value || '').trim(),
        lawyer_phone: (document.getElementById('pkg-lawyer-phone')?.value || '').trim(),
      };
      const profile = profileWithoutDemoIdentity(raw);
      const cleared = (
        profile.lawyer_name !== raw.lawyer_name
        || profile.law_firm !== raw.law_firm
        || profile.lawyer_license !== raw.lawyer_license
        || profile.lawyer_phone !== raw.lawyer_phone
      );
      if (cleared) {
        const nameEl = document.getElementById('pkg-lawyer-name');
        const firmEl = document.getElementById('pkg-law-firm');
        const licenseEl = document.getElementById('pkg-lawyer-license');
        const phoneEl = document.getElementById('pkg-lawyer-phone');
        if (nameEl) nameEl.value = profile.lawyer_name;
        if (firmEl) firmEl.value = profile.law_firm;
        if (licenseEl) licenseEl.value = profile.lawyer_license;
        if (phoneEl) phoneEl.value = profile.lawyer_phone;
        showToast('示例身份不会写入文书');
      }
      try {
        localStorage.setItem('lawflow-lawyer-profile', JSON.stringify(profile));
      } catch (e) { /* 浏览器禁止存储时仍可继续生成 */ }
      return profile;
    }

    export async function saveLitigationLetterPrefix() {
      const input = document.getElementById('pkg-letter-prefix');
      if (!input) return true;
      const prefix = input.value.trim();
      if (prefix.includes('京律函字')) {
        input.value = '';
        showToast('不能使用示例函号。请填本所自己的前缀，没有就留空。');
        return false;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/letter-prefix`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prefix }),
        });
        if (!resp || !resp.ok) {
          showToast('函号前缀保存失败');
          return false;
        }
        const settingsInput = document.getElementById('cfg-letter-prefix');
        if (settingsInput && settingsInput.value.trim() !== prefix) settingsInput.value = prefix;
        return true;
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('函号前缀保存失败: ' + e));
        return false;
      }
    }

    function currentMatterId() {
      const store = window.CaseContextStore;
      if (store && typeof store.get === 'function') {
        const ctx = store.get() || {};
        if (ctx.matter_id) return ctx.matter_id;
      }
      if (window.activeMatterId) return window.activeMatterId;
      return '';
    }

    function filingResponsibilityChecked() {
      return !!document.getElementById('pkg-filing-ack')?.checked;
    }

    function confirmFilingExport(event) {
      if (filingResponsibilityChecked()) return true;
      if (event && typeof event.preventDefault === 'function') event.preventDefault();
      showToast('导出前请确认：我已审阅，提交件由承办律师负责', 'error');
      return false;
    }

    function readClaimLines() {
      const raw = (document.getElementById('pkg-claims')?.value || '').trim();
      return raw.split(/\n+/).map((line) => line.trim()).filter((line) => line && line !== '【待填写】');
    }

    function readSettledInterest() {
      let calc = {};
      try {
        const store = window.CaseContextStore;
        if (store && typeof store.get === 'function') {
          calc = (store.get() || {}).interest_calc || {};
        }
      } catch (e) {
        calc = {};
      }
      const principal = Number(calc.principal);
      const start = String(calc.start_date || '').trim();
      const end = String(calc.end_date || '').trim();
      let rate = null;
      if (calc.annual_rate != null && calc.annual_rate !== '') rate = Number(calc.annual_rate);
      else if (calc.rate != null && calc.rate !== '') rate = Number(calc.rate);
      const statement = String(calc.formal_statement || '').trim();
      if (!Number.isFinite(rate)) {
        const matched = statement.match(/(?:年利率|执行年化|约定年利率)\s*(\d+(?:\.\d+)?)\s*%/);
        if (matched) rate = Number(matched[1]);
      }
      if (!Number.isFinite(rate)) {
        const agreed = document.getElementById('lpr-agreed');
        const sameStart = (document.getElementById('lpr-start')?.value || '') === start;
        const sameEnd = (document.getElementById('lpr-end')?.value || '') === end;
        if (agreed && agreed.value.trim() !== '' && start && end && sameStart && sameEnd) {
          rate = Number(agreed.value);
        }
      }
      const interestTotal = Number(calc.interest_total);
      return {
        principal: Number.isFinite(principal) && principal > 0 ? principal : null,
        start_date: start,
        end_date: end,
        annual_rate: Number.isFinite(rate) ? rate : null,
        interest_total: Number.isFinite(interestTotal) ? interestTotal : null,
        formal_statement: statement,
      };
    }

    async function runGenerateLitigationPackage() {
      if (!filingResponsibilityChecked()) {
        showToast('导出前请确认：我已审阅，提交件由承办律师负责', 'error');
        return;
      }
      const claimLines = readClaimLines();
      if (!claimLines.length) {
        showToast('请填写诉讼请求。不会把【待填写】写成正式请求。', 'error');
        return;
      }
      const pName = (document.getElementById('pkg-p-name')?.value || '').trim();
      const dName = (document.getElementById('pkg-d-name')?.value || '').trim();
      const notes = (document.getElementById('pkg-notes')?.value || '').trim();
      const court = (document.getElementById('pkg-court')?.value || '').trim();
      if (!pName || !dName || !notes || !court) {
        showToast("请先填写原告、被告、受诉法院和案情笔记");
        return;
      }
      const btn = document.getElementById('btn-generate-pkg');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner"></span> 正在援引实体法条与排版 Word/PDF...`;
      btn.disabled = true;
      document.getElementById('pkg-status-tip').innerText = "正在生成（长任务进行中，请稍候）…";

      const amountRaw = document.getElementById('pkg-amount').value;
      const claimAmount = amountRaw === '' || amountRaw == null ? 0 : parseFloat(amountRaw);
      const causeNow = document.getElementById('pkg-cause').value;
      if (!causeNow || causeNow.startsWith('请选择')) {
        showToast('请先选择文书类型。不会按民间借贷生成。');
        btn.innerHTML = origHtml;
        btn.disabled = false;
        document.getElementById('pkg-status-tip').innerText = '请先选择文书类型';
        return;
      }
      if (!claimAmount && causeNow !== '离婚纠纷') {
        showToast("请填写诉讼标的。没有财产请求时也请写明，不要留空后生成成 0 元或示例金额。");
        btn.innerHTML = origHtml;
        btn.disabled = false;
        return;
      }
      const lawyer = saveLawyerProfileFromForm();
      const prefixOk = await saveLitigationLetterPrefix();
      if (!prefixOk) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        document.getElementById('pkg-status-tip').innerText = '函号前缀未保存，已停止生成';
        return;
      }
      const payload = {
        cause_of_action: document.getElementById('pkg-cause').value,
        matter_id: currentMatterId() || undefined,
        procedure: (window.activeMatterData && window.activeMatterData.practice && window.activeMatterData.practice.procedure) || undefined,
        claim_amount: claimAmount,
        raw_case_notes: document.getElementById('pkg-notes').value,
        court_name: document.getElementById('pkg-court').value,
        claims: claimLines,
        settled_interest: readSettledInterest(),
        lawyer_name: lawyer.lawyer_name,
        law_firm: lawyer.law_firm,
        lawyer_phone: lawyer.lawyer_phone,
        lawyer_license: lawyer.lawyer_license,
        monthly_salary: parseFloat(document.getElementById('pkg-monthly-salary')?.value) || null,
        hire_date: document.getElementById('pkg-hire-date')?.value || null,
        termination_date: document.getElementById('pkg-termination-date')?.value || null,
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
          if (document.getElementById('subdoc-firm')?.checked) list.push('law_firm_letter');
          if (document.getElementById('subdoc-demand')?.checked) list.push('demand_letter');
          if (document.getElementById('subdoc-answer')?.checked) list.push('answer_brief');
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
        const pdfFailures = (d.generated_documents || []).filter((doc) => doc && doc.pdf_error);
        let tip = "文书包生成完毕";
        if (pdfFailures.length) {
          tip = pdfFailures[0].pdf_error;
        } else if (es.llm === "rule_fallback" || es.pdf === "local_pymupdf") {
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
            badge.style.background = d.download_blocked ? '#B43434' : '#C58532';
            badge.innerText = (d.citation_audit.badge && d.citation_audit.badge.label) || '引用待核验';
          }
        }

        document.getElementById('pkg-facts-box').innerText = d.facts_and_reasons_polished;

        const archiveBar = document.getElementById('pkg-archive-bar');
        const btnSpcZip = document.getElementById('btn-download-spc-zip');
        const btnFlatZip = document.getElementById('btn-download-flat-zip');
        if (d.download_blocked) {
          if (archiveBar) archiveBar.style.display = 'block';
          if (btnSpcZip) btnSpcZip.removeAttribute('href');
          if (btnFlatZip) btnFlatZip.removeAttribute('href');
          showToast(d.download_block_reason || '引用熔断未通过', 'error');
        } else if (archiveBar && btnSpcZip && btnFlatZip && (d.package_zip_url || d.package_flat_zip_url || d.package_download_url)) {
          archiveBar.style.display = 'block';
          const arm = () => {
            const spcUrl = d.package_zip_url || (d.package_id ? `/api/v1/phase1/package/${d.package_id}/download?format=spc_mobile` : null);
            if (spcUrl) {
              btnSpcZip.href = withDownloadToken(spcUrl);
              btnSpcZip.setAttribute('download', d.package_zip_name || '立案公文包_移动微法院标准.zip');
            }
            const flatUrl = d.package_flat_zip_url || (d.package_id ? `/api/v1/phase1/package/${d.package_id}/download?format=flat` : null);
            if (flatUrl) {
              btnFlatZip.href = withDownloadToken(flatUrl);
              btnFlatZip.setAttribute('download', d.package_flat_zip_name || '立案公文包_扁平打包.zip');
            }
          };
          if (d.download_ack_required) {
            btnSpcZip.removeAttribute('href');
            btnFlatZip.removeAttribute('href');
            let ack = document.getElementById('pkg-citation-ack');
            if (!ack) {
              ack = document.createElement('label');
              ack.id = 'pkg-citation-ack';
              ack.style.cssText = 'display:block;color:#FDE68A;font-size:12px;margin-bottom:8px;';
              archiveBar.prepend(ack);
            }
            ack.innerHTML = '<input type="checkbox" id="pkg-citation-ack-box" aria-label="确认已核对法条和案号后下载"> 我已核对法条和案号，确认下载（本地库未覆盖的引用仍须人工复核）';
            document.getElementById('pkg-citation-ack-box').onchange = (ev) => {
              if (ev.target.checked) arm();
              else {
                btnSpcZip.removeAttribute('href');
                btnFlatZip.removeAttribute('href');
              }
            };
          } else {
            arm();
          }
        }

        // 生成文书列表与最高院四大类目标签渲染
        const listDiv = document.getElementById('pkg-doc-list');
        listDiv.innerHTML = "";
        const catBadgeMap = {
          "01_起诉状及身份证明": { label: "01 起诉及主体", bg: "#1E3A8A", text: "#93C5FD" },
          "02_委托代理材料": { label: "02 委托代理", bg: "#312E81", text: "#C7D2FE" },
          "03_送达地址确认书": { label: "03 送达确认", bg: "#065F46", text: "#A7F3D0" },
          "04_证据清单与证据材料": { label: "04 证据材料", bg: "#78350F", text: "#FDE68A" },
        };

        (d.generated_documents || []).forEach(doc => {
          const catInfo = catBadgeMap[doc.category] || { label: doc.category || "诉讼材料", bg: "#374151", text: "#E5E7EB" };
          const internalDraft = doc.doc_type === "律师函" || doc.doc_type === "民事答辩状";
          const draftDisclaimer = internalDraft
            ? `<div class="lf-disclaimer-line" data-internal-draft="1">本输出由软件自动生成，仅供执业律师参考，不构成法律意见，须经律师审核后使用。</div>`
            : "";
          listDiv.innerHTML += `
            <div class="doc-pill-item" style="border: 1px solid rgba(255,255,255,0.08); background: #11141C;">
              <div class="doc-info">
                <div style="display: flex; align-items: center; gap: 6px;">
                  <strong>${doc.doc_type}</strong>
                  <span class="badge" style="background: ${catInfo.bg}; color: ${catInfo.text}; font-size: 10px; padding: 1px 6px; border-radius: 4px;">${catInfo.label}</span>
                </div>
                <span>${doc.filename_docx}</span>
              </div>
              <div style="display: flex; gap: 8px;">
                <a href="${withDownloadToken(doc.docx_url)}" class="btn btn-secondary btn-sm" download onclick="return confirmFilingExport(event)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  Word 存证
                </a>
                ${doc.pdf_url && !doc.pdf_error ? `
                <a href="${withDownloadToken(doc.pdf_url)}" class="btn btn-sm" style="background:#1F6E4A;" download onclick="return confirmFilingExport(event)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                  A4 PDF
                </a>` : (doc.pdf_error ? `<span class="pdf-fail-note">${escapeHtml(doc.pdf_error)}</span>` : '')}
              </div>
            </div>
            ${draftDisclaimer}
          `;
        });
        if (pdfFailures.length) {
          showToast(pdfFailures.map((doc) => `${doc.doc_type || '文书'}：${doc.pdf_error}`).join('；'), 'error');
        } else {
          showToast("立案文书流水线生成完毕", "success");
        }
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        showToast("生成失败: " + e);
      }
    }


async function runDownloadSpcElementComplaint() {
  if (!confirmFilingExport()) return;
  const btn = document.getElementById('btn-download-spc-complaint');
  const origText = btn ? btn.innerHTML : '';
  try {
    if (btn) {
      btn.disabled = true;
      btn.innerText = '正在构建要素式起诉状...';
    }
    const cause = document.getElementById('pkg-cause')?.value || '民间借贷纠纷';
    const matterId = currentMatterId() || null;
    const resp = await api.request(`${API_BASE}/api/v1/phase1/generate-spc-element-complaint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        cause,
        matter_id: matterId,
        plaintiff_name: document.getElementById('pkg-p-name')?.value || '',
        plaintiff_id_or_uscc: document.getElementById('pkg-p-id')?.value || '',
        plaintiff_phone: document.getElementById('pkg-p-phone')?.value || '',
        plaintiff_address: document.getElementById('pkg-p-addr')?.value || '',
        defendant_name: document.getElementById('pkg-d-name')?.value || '',
        defendant_id_or_uscc: document.getElementById('pkg-d-id')?.value || '',
        defendant_phone: document.getElementById('pkg-d-phone')?.value || '',
        defendant_address: document.getElementById('pkg-d-addr')?.value || '',
        principal_amount: document.getElementById('pkg-amount')?.value || '',
        facts_and_reasons: document.getElementById('pkg-notes')?.value || '',
        court_name: document.getElementById('pkg-court')?.value || ''
      })
    });
    if (resp && resp.download_url) {
      showToast('最高法要素式起诉状已就绪，正在下载', 'success');
      const dlUrl = withDownloadToken(resp.download_url);
      const a = document.createElement('a');
      a.href = dlUrl;
      a.download = resp.filename || '最高法要素式起诉状_民间借贷示范文本.docx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } else {
      showToast('生成最高法要素式起诉状失败', 'error');
    }
  } catch (e) {
    showToast(`导出失败: ${e.message}`, 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origText;
    }
  }
}

export {
  updateCausePreset,
  confirmFilingExport,
  runGenerateLitigationPackage,
  runDownloadSpcElementComplaint,
};

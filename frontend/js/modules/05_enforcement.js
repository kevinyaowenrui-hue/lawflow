/**
 * LawFlow Module: 05_enforcement.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const ENFORCEMENT_TAB_HTML = `      
      <!-- 模式切换：执行终本破局 vs 审前要件推演 -->
      <div style="display: flex; gap: 10px; margin-bottom: 16px; border-bottom: 2px solid rgba(0,0,0,0.06); padding-bottom: 8px;">
        <button id="btn-subtab-enforcement" class="tab-sub-btn active" onclick="switchDeepMatrixSubTab('pane-deep-enforcement')" style="font-weight: 700; font-size: 13px; padding: 7px 16px; border-radius: 6px; cursor: pointer; border: 1px solid var(--accent-amber-border); background: var(--bg-card); color: var(--accent-amber); display: inline-flex; align-items: center; gap: 6px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
          <span>执行追加要件审查</span>
        </button>
        <button id="btn-subtab-classic-matrix" class="tab-sub-btn" onclick="switchDeepMatrixSubTab('pane-deep-matrix-classic')" style="font-weight: 600; font-size: 13px; padding: 7px 16px; border-radius: 6px; cursor: pointer; border: 1px solid var(--border-color); background: transparent; color: var(--text-secondary); display: inline-flex; align-items: center; gap: 6px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
          <span>⚖️ 审前要件事实与红队质证矩阵 (Classic)</span>
        </button>
      </div>

      <!-- 子面板 1: P4 级执行终本破局大屏 -->
      <div id="pane-deep-enforcement" style="display: block;">
        <!-- 顶部操作与全景指标栏 -->
        <div class="surface-card" style="margin-bottom: 16px; padding: 16px 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 16px; font-weight: 800; color: var(--text-primary); letter-spacing: 0.5px;">执行财产线索穿透与追加被执行人工作台</span>
                <span class="badge" style="background: rgba(180, 52, 52, 0.12); color: #B43434; font-weight: 700; border: 1px solid rgba(180, 52, 52, 0.2);">追加审查</span>
                <span class="badge" style="background: rgba(46, 125, 50, 0.12); color: #2E7D32; font-weight: 700; border: 1px solid rgba(46, 125, 50, 0.2);">新《公司法》&追加规定</span>
              </div>
              <div style="font-size: 12px; color: var(--text-muted); margin-top: 4px;">
                基于下方已填事实运行四大探针；缺事实时返回事实不足，不编造结论。
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-primary" onclick="runEnforcementAuditUI()" style="font-weight: 700; display: inline-flex; align-items: center; gap: 6px;">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
                <span>按已填事实审查追加要件</span>
              </button>
            </div>
          </div>

          <div style="margin-top: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
            <div class="form-group"><label class="form-label">执行法院</label><input aria-label="执行法院" type="text" id="enf-input-court" value=""></div>
            <div class="form-group"><label class="form-label">执行案号</label><input aria-label="执行案号" type="text" id="enf-input-case-no" value=""></div>
            <div class="form-group"><label class="form-label">申请执行人</label><input aria-label="申请执行人" type="text" id="enf-input-applicant" value=""></div>
            <div class="form-group"><label class="form-label">被执行人企业</label><input aria-label="被执行人企业" type="text" id="enf-input-debtor" value=""></div>
            <div class="form-group"><label class="form-label">标的额（元）</label><input aria-label="执行标的额" type="number" id="enf-input-claim" value=""></div>
            <div class="form-group"><label class="form-label">查明账面存款（元）</label><input aria-label="查明账面存款" type="number" id="enf-input-balance" value=""></div>
            <div class="form-group"><label class="form-label">实控人/原股东</label><input aria-label="实控人或原股东" type="text" id="enf-input-controller" value=""></div>
            <div class="form-group"><label class="form-label">受让人</label><input aria-label="股权受让人" type="text" id="enf-input-transferee" value=""></div>
            <div class="form-group"><label class="form-label">注册资本（元）</label><input aria-label="注册资本" type="number" id="enf-input-capital" value=""></div>
            <div class="form-group"><label class="form-label">认缴比例（0-1）</label><input aria-label="认缴比例" type="number" step="0.01" id="enf-input-ratio" value=""></div>
            <div class="form-group" style="display:flex; align-items:flex-end; gap:8px;">
              <label style="font-size:12px; color:var(--text-secondary);"><input type="checkbox" id="enf-input-one-person" aria-label="一人有限责任公司"> 一人有限公司</label>
              <label style="font-size:12px; color:var(--text-secondary);"><input type="checkbox" id="enf-input-unable-pay" aria-label="公司不能清偿到期债务"> 不能清偿到期债务</label>
            </div>
            <div class="form-group" style="grid-column: 1 / -1;"><label class="form-label">股权转让 / 混同流水等事实备注</label><textarea aria-label="执行事实备注" id="enf-input-notes" rows="3" class="quick-input" placeholder="例如：某年某月股权零对价转让；公私账户混同流水要点。缺证据处写明待补。"></textarea></div>
          </div>

          <!-- 核心指标条 -->
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-top: 16px;">
            <div style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px;">
              <div style="font-size: 11px; color: var(--text-muted); font-weight: 600;">执行生效法律文书标的</div>
              <div style="font-size: 20px; font-weight: 800; color: var(--text-primary); margin-top: 2px;" id="enf-kpi-claim">【待填写】</div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">本金及违约金孳息全额</div>
            </div>
            <div style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px;">
              <div style="font-size: 11px; color: #B43434; font-weight: 600;">执行局查明账面存款</div>
              <div style="font-size: 20px; font-weight: 800; color: #B43434; margin-top: 2px;" id="enf-kpi-balance">【待填写】</div>
              <div style="font-size: 11px; color: #B43434; margin-top: 2px;">无车无房无社保 (终本死局)</div>
            </div>
            <div style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px;">
              <div style="font-size: 11px; color: #2E7D32; font-weight: 600;">另诉财产不计入可执行金额</div>
              <div style="font-size: 20px; font-weight: 800; color: #2E7D32; margin-top: 2px;" id="enf-kpi-recoverable">【待填写】</div>
              <div style="font-size: 11px; color: #2E7D32; margin-top: 2px;">须有证据，不预估覆盖率</div>
            </div>
            <div style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 12px 14px;">
              <div style="font-size: 11px; color: var(--accent-amber); font-weight: 600;">要件是否齐备</div>
              <div style="font-size: 20px; font-weight: 800; color: var(--accent-amber); margin-top: 2px;" id="enf-kpi-rate">—</div>
              <div style="font-size: 11px; color: var(--accent-amber); margin-top: 2px;">不提供胜率</div>
            </div>
          </div>
        </div>

        <!-- 四大穿透探针卡片 -->
        <div style="margin-bottom: 16px;">
          <div style="font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 10px; display: flex; align-items: center; gap: 6px;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            <span>四大执行穿透算法探针诊断 (Execution Piercing Diagnostic Probes)</span>
          </div>
          <div id="enf-probes-container" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 12px;">
            <!-- 动态渲染探针卡片 -->
          </div>
        </div>

        <!-- 财产隐匿转移链路与混同穿透可视图 -->
        <div class="surface-card" style="margin-bottom: 16px; padding: 16px 20px;">
          <div style="font-size: 13px; font-weight: 700; color: var(--text-primary); margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 6px;">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="18" cy="5" r="3"></circle><circle cx="6" cy="12" r="3"></circle><circle cx="18" cy="19" r="3"></circle><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"></line><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"></line></svg>
              <span>穿透式财产转移拓扑与混同资金穿行图谱 (Asset Stripping & Commingling Topology)</span>
            </div>
            <span style="font-size: 11px; color: var(--text-muted);">基于公私银行流水、工商股权变更及民政离婚时序提取</span>
          </div>
          
          <div id="enf-topology-box" style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 16px; min-height: 180px; display: flex; align-items: center; justify-content: center; overflow-x: auto;">
            <!-- 拓扑图由JS动态渲染 -->
          </div>
        </div>

        <!-- 执行破局公文交付双视图工作台 -->
        <div class="surface-card" style="margin-bottom: 20px; padding: 16px 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <div style="font-size: 13px; font-weight: 700; color: var(--text-primary);">执行局法官审查标准公文工作台</div>
              <div style="display: inline-flex; border: 1px solid var(--border-color); border-radius: 6px; overflow: hidden;">
                <button id="btn-enfdoc-app" class="btn btn-sm" onclick="switchEnforcementDocView('addition_application')" style="background: var(--bg-card); font-weight: 700; color: var(--accent-amber);">
                  《追加被执行人申请书》
                </button>
                <button id="btn-enfdoc-lawsuit" class="btn btn-sm" onclick="switchEnforcementDocView('objection_lawsuit')" style="background: transparent; font-weight: 600; color: var(--text-secondary);">
                  《执行异议之诉起诉状》
                </button>
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button class="btn btn-secondary btn-sm" onclick="copyEnforcementDocument()">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                <span>复制当前公文</span>
              </button>
              <button class="btn btn-primary btn-sm" onclick="exportEnforcementDocxUI()">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                <span>导出 Word 原生公文 (.docx)</span>
              </button>
            </div>
          </div>

          <!-- 文书正文预览区 -->
          <div id="enf-doc-preview" style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 20px; font-family: '仿宋_GB2312', 'FangSong', 'SimSun', serif; font-size: 13.5px; line-height: 1.8; color: #1c1c1c; max-height: 400px; overflow-y: auto; white-space: pre-wrap;">
            点击上方【按已填事实审查追加要件】生成申请书草稿。缺事实时只提示事实不足，不估算胜率。
          </div>
        </div>
      </div><!-- /#pane-deep-enforcement -->

      <!-- 子面板 2: 原有审前要件事实与红队质证矩阵 (Classic) -->
      <div id="pane-deep-matrix-classic" style="display: none;">
      <!-- 顶部控制与全景指标栏 -->
      <div class="surface-card" style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <!-- 卷宗选择器 -->
          <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
            <div style="display: flex; flex-direction: column; gap: 3px;">
              <span style="font-size: 11px; font-weight: 600; color: var(--text-muted); letter-spacing: 0.5px;">本案事实，或手动打开演示卷宗</span>
              <select aria-label="deep case preset"  id="deep-case-preset" onchange="changeDeepPreset()" style="font-weight: 600; min-width: 200px; max-width: 100%; padding: 6px 10px;">
                <option value="custom" selected>当前案件（填写事实后再推演）</option>
                <option value="case_loan_intermingled">演示：张三诉李四民间借贷（不是在办案件）</option>
                <option value="case_tech_development">演示：智科云服诉华腾物流（不是在办案件）</option>
              </select>
            </div>
            
            <button class="btn" onclick="runDeepMatrixAnalyze()" style="margin-top: 15px; display: inline-flex; align-items: center; gap: 6px;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
              <span>执行七维深度要件推演</span>
            </button>
          </div>

          <!-- 红蓝视角切换器 (核心交互) -->
          <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
            <span style="font-size: 11px; font-weight: 600; color: var(--text-muted);">质证推演视角切换 (Perspective Switch)</span>
            <div class="perspective-switch">
              <button class="perspective-btn blue active" id="btn-view-blue" onclick="switchPerspective('plaintiff_blue_team')">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; display: inline-block;"></span>
                <span>己方主办律师 (Blue Team 闭环防御)</span>
              </button>
              <button class="perspective-btn red" id="btn-view-red" onclick="switchPerspective('adversarial_red_team')">
                <span style="width: 8px; height: 8px; border-radius: 50%; background: #ef4444; display: inline-block;"></span>
                <span>对方红队律师 (Red Team 极端攻击)</span>
              </button>
            </div>
          </div>
        </div>

        <!-- 真实卷宗动态喂入输入面板 (当选择自定义卷宗或点击流转时展开) -->
        <div id="deep-custom-dossier-panel" style="display: block; margin-top: 16px; border-top: 1px solid var(--border-hairline); padding-top: 14px; background: #FCFBF9; border-radius: var(--radius-sm); padding: 14px 16px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">在办真实卷宗深度推演输入面板 (Real Dossier Input)</span>
              <span class="badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 11px;">结合 statute_db 权威法典与大模型实时穿透</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="loadCaseContextToDeepPanel()">
              📥 从全局在办案件一键载入 (CaseContext)
            </button>
          </div>

          <div class="deep-matrix-top-grid">
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">案由类型</label>
              <select aria-label="deep custom cause"  id="deep-custom-cause" style="width: 100%; padding: 6px 8px; font-size: 12px; margin-top: 3px;">
                <option value="民间借贷纠纷">民间借贷纠纷</option>
                <option value="买卖合同纠纷">买卖合同纠纷</option>
                <option value="劳动人事争议">劳动人事争议</option>
                <option value="技术开发合同纠纷">技术开发合同纠纷</option>
                <option value="建设工程施工合同纠纷">建设工程施工合同纠纷</option>
                <option value="通用民商事纠纷">通用民商事纠纷</option>
              </select>
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">案件标题</label>
              <input aria-label="deep custom title"  type="text" id="deep-custom-title" class="quick-input" value="" style="margin-top: 3px;">
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">原告/权利人</label>
              <input aria-label="deep custom p"  type="text" id="deep-custom-p" class="quick-input" value="" placeholder="填写本案原告" style="margin-top: 3px;">
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">被告/义务人</label>
              <input aria-label="deep custom d"  type="text" id="deep-custom-d" class="quick-input" value="" placeholder="填写本案被告" style="margin-top: 3px;">
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">主张标的额 (元)</label>
              <input aria-label="deep custom amount"  type="number" id="deep-custom-amount" class="quick-input" value="" placeholder="主张金额" step="5000" style="margin-top: 3px;">
            </div>
          </div>

          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 10px;">
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">案件事实经过与争议要点 (Facts & Narrative)</label>
              <textarea aria-label="粘贴案件事实、借款或交易往来经过..."  id="deep-custom-facts" class="quick-input" rows="3" placeholder="粘贴本案事实、借款或交易往来经过。不要留示例故事。" style="margin-top: 3px; font-size: 12px; line-height: 1.5;"></textarea>
            </div>
            <div>
              <label style="font-size: 11px; font-weight: 600; color: var(--text-secondary);">原始在卷证据材料清单 (Evidence Notes)</label>
              <textarea aria-label="证据一：借条原件&#10;证据二：招行转账50万网银电子回单&#10;证据三：公证书提取微信催款记录"  id="deep-custom-evidence" class="quick-input" rows="3" placeholder="证据一：借条原件&#10;证据二：银行转账回单&#10;证据三：催款记录" style="margin-top: 3px; font-size: 12px; line-height: 1.5; font-family: var(--font-mono);"></textarea>
            </div>
          </div>

          <div style="margin-top: 10px; display: flex; justify-content: space-between; align-items: center;">
            <div style="font-size: 11.5px; color: var(--text-muted);" id="deep-custom-statutes-hint">
              已关联当前在办案件请求权实体法条: <span id="deep-custom-statutes-count" style="color:var(--accent-amber); font-weight:700;">0</span> 条
            </div>
            <button type="button" class="btn btn-primary btn-sm" onclick="submitCustomDeepMatrixAnalyze()" style="display: inline-flex; align-items: center; gap: 6px;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
              <span>执行真实卷宗七维深度推演</span>
            </button>
          </div>
        </div>

        <!-- 四大客观实证检验指标卡 -->
        <div class="metric-summary-box" style="margin-top: 16px; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));">
          <div class="metric-item">
            <span class="metric-label">构成要件完备率</span>
            <span class="metric-value highlight" id="deep-metric-score">—</span>
            <span class="metric-sub" id="deep-metric-status" style="color: var(--status-warn); font-weight: 600;">尚未推演，不能据此决定起诉</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">一手原始卷宗锚定</span>
            <span class="metric-value" id="deep-metric-raw">—</span>
            <span class="metric-sub" id="deep-metric-raw-sub">还没有录入材料，不能代替原件</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">侦测到的致命冲突</span>
            <span class="metric-value" id="deep-metric-conflicts" style="color: var(--status-warn);">—</span>
            <span class="metric-sub">推演后显示冲突项</span>
          </div>
          <div class="metric-item">
            <span class="metric-label">执业红线安全门禁</span>
            <span class="metric-value" id="deep-metric-guard" style="color: var(--text-muted);">未审查</span>
            <span class="metric-sub" id="deep-metric-guard-sub">不代表利率或时效已经处理</span>
          </div>
        </div>
      </div>

      <!-- 下方主体双栏 (左栏：一手卷宗库与时间轴冲突看板 46% ; 右栏：七维要件事实矩阵与外部实证账本 54%) -->
      <div class="split-grid-55-45 split-grid-46-54">
        
        <!-- 左栏：原始卷宗素材 + 多源多轨时间轴冲突看板 -->
        <div style="display: flex; flex-direction: column; gap: 16px;">
          
          <!-- 一手卷宗原件库 (带行号坐标高亮) -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
                一手原始卷宗库 (未消化原始底档)
              </div>
              <span class="card-tip">点击展开逐行摘录与哈希防伪验真</span>
            </div>

            <div id="deep-raw-dossier-list" style="display: flex; flex-direction: column; gap: 10px;">
              <!-- 动态填充一手卷宗卡片 -->
            </div>
          </div>

          <!-- 多源多轨时间轴与交叉质证冲突看板 -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
                多源时间轴交叉质证与冲突侦测
              </div>
              <span class="card-tip">自动侦测倒签、代付主体及反言冲突</span>
            </div>

            <!-- 严重冲突预警横幅区 -->
            <div id="deep-conflicts-area" style="display: flex; flex-direction: column; gap: 8px;">
              <!-- 动态填充冲突警报 -->
            </div>

            <!-- 时间轴事件流 -->
            <div style="margin-top: 12px; border-top: 1px solid var(--border-hairline); padding-top: 14px;">
              <div class="timeline-track" id="deep-timeline-track">
                <!-- 动态填充时间轴节点 -->
              </div>
            </div>
          </div>

        </div>

        <!-- 右栏：七维请求权基础与要件事实矩阵 + 外部实证账本 -->
        <div style="display: flex; flex-direction: column; gap: 16px;">
          
          <!-- 要件事实矩阵看板 -->
          <div class="surface-card">
            <div class="card-header">
              <div class="card-title" id="deep-matrix-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
                七维请求权基础与要件事实推演矩阵
              </div>
              <span class="badge" id="deep-perspective-label" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy);">己方主办律师视角</span>
            </div>

            <div id="deep-matrix-container" style="display: flex; flex-direction: column; gap: 12px;">
              <!-- 动态渲染要件卡片 -->
            </div>
          </div>

          <!-- 外部客观证明标准与可验证账本 -->
          <div class="surface-card" style="background: #FCFBF9;">
            <div class="card-header">
              <div class="card-title">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                外部客观实证验证账本 (External Verifiability Ledger)
              </div>
              <button class="btn btn-secondary btn-sm" onclick="exportDeepMatrixReport()">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                导出质证对抗报告
              </button>
            </div>

            <div id="deep-verifiability-box" style="font-size: 12px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 6px; line-height: 1.6;">
              <!-- 动态渲染可验证报告 -->
            </div>
          </div>

        </div>

      </div>
      </div><!-- /#pane-deep-matrix-classic -->
    </section>

    <!-- ======================================================================
         模块 06：权威法典与子母法图谱检索中枢 (SQLite FTS5 + 穿透图谱)
         ====================================================================== -->
`;

export function renderTabEnforcement() {
  const el = document.getElementById('tab-deep-matrix');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = ENFORCEMENT_TAB_HTML;
  }
}


    // =========================================================================
    // 6.0 模块 05 子标签切换：执行终本破局大屏 vs 审前要件事实矩阵
    // =========================================================================
    let currentEnforcementData = null;
    let currentEnforcementDocView = 'addition_application';

    function switchDeepMatrixSubTab(paneId) {
      const isEnforcement = paneId === 'pane-deep-enforcement';
      const btnEnf = document.getElementById('btn-subtab-enforcement');
      const btnCls = document.getElementById('btn-subtab-classic-matrix');
      const paneEnf = document.getElementById('pane-deep-enforcement');
      const paneCls = document.getElementById('pane-deep-matrix-classic');

      if (btnEnf && btnCls && paneEnf && paneCls) {
        if (isEnforcement) {
          btnEnf.className = 'tab-sub-btn active';
          btnEnf.style.background = 'var(--bg-card)';
          btnEnf.style.color = 'var(--accent-amber)';
          btnEnf.style.borderColor = 'var(--accent-amber-border)';
          btnCls.className = 'tab-sub-btn';
          btnCls.style.background = 'transparent';
          btnCls.style.color = 'var(--text-secondary)';
          btnCls.style.borderColor = 'var(--border-color)';
          paneEnf.style.display = 'block';
          paneCls.style.display = 'none';
        } else {
          btnCls.className = 'tab-sub-btn active';
          btnCls.style.background = 'var(--bg-card)';
          btnCls.style.color = 'var(--primary-navy)';
          btnCls.style.borderColor = 'var(--primary-navy)';
          btnEnf.className = 'tab-sub-btn';
          btnEnf.style.background = 'transparent';
          btnEnf.style.color = 'var(--text-secondary)';
          btnEnf.style.borderColor = 'var(--border-color)';
          paneEnf.style.display = 'none';
          paneCls.style.display = 'block';
        }
      }
    }

    function _enfNum(id) {
      const raw = document.getElementById(id)?.value;
      if (raw === undefined || raw === null || String(raw).trim() === '') return null;
      const n = parseFloat(raw);
      return Number.isNaN(n) ? null : n;
    }

    async function runEnforcementAuditUI() {
      try {
        showToast("正在按已填事实审查追加要件（缺事实时返回事实不足）...");
        const notes = (document.getElementById('enf-input-notes')?.value || '').trim();
        const payload = {
          use_demo: false,
          court_name: (document.getElementById('enf-input-court')?.value || '').trim() || null,
          execution_case_no: (document.getElementById('enf-input-case-no')?.value || '').trim() || null,
          applicant_name: (document.getElementById('enf-input-applicant')?.value || '').trim() || null,
          debtor_name: (document.getElementById('enf-input-debtor')?.value || '').trim() || null,
          claim_amount: _enfNum('enf-input-claim'),
          book_balance: _enfNum('enf-input-balance'),
          controller_name: (document.getElementById('enf-input-controller')?.value || '').trim() || null,
          transferee_name: (document.getElementById('enf-input-transferee')?.value || '').trim() || null,
          share_capital: _enfNum('enf-input-capital'),
          subscribed_share_ratio: _enfNum('enf-input-ratio'),
          is_one_person_company: !!document.getElementById('enf-input-one-person')?.checked,
          company_unable_to_pay: !!document.getElementById('enf-input-unable-pay')?.checked,
          related_company_note: notes || null,
        };
        if (notes) {
          payload.equity_transfers = [{ evidence_note: notes }];
          payload.capital_flows = [{ evidence_note: notes }];
        }
        const resp = await api.request(`${API_BASE}/api/v1/enforcement/penetration-audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentEnforcementData = data;
        showToast('执行穿透审查完成');

        // 1. 更新顶部指标条
        const elClaim = document.getElementById('enf-kpi-claim');
        const elBalance = document.getElementById('enf-kpi-balance');
        const elRecoverable = document.getElementById('enf-kpi-recoverable');
        const elRate = document.getElementById('enf-kpi-rate');
        const fmt = (v) => (v === null || v === undefined) ? '【待填写】' : `¥ ${Number(v).toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        if (elClaim) elClaim.innerText = fmt(data.claim_amount);
        if (elBalance) elBalance.innerText = fmt(data.book_balance);
        if (elRecoverable) {
          elRecoverable.innerText = (data.recoverable_potential === null || data.recoverable_potential === undefined)
            ? '另诉金额未计入'
            : fmt(data.recoverable_potential);
        }
        if (elRate) elRate.innerText = "—";

        // 2. 渲染四大穿透探针诊断卡片
        const probesContainer = document.getElementById('enf-probes-container');
        if (probesContainer && data.probes) {
          probesContainer.innerHTML = data.probes.map(p => { // safe-html: contains nested HTML fragment interpolations
            const insufficient = p.status === 'INSUFFICIENT_FACTS';
            const badge = insufficient ? '事实不足' : (p.severity || '已就绪');
            const badgeBg = insufficient ? 'rgba(202,138,4,0.12)' : 'rgba(180, 52, 52, 0.12)';
            const badgeColor = insufficient ? '#A16207' : '#B43434';
            const body = insufficient
              ? `<div style="font-size:12px;color:var(--text-secondary);">缺少事实：${escapeHtml((p.missing_facts||[]).join('、') || '未列明')}</div>`
              : `<div style="font-size: 11px; color: var(--accent-amber); font-weight: 600; margin-bottom: 6px;">法定依据：${escapeHtml(p.target_statute||'')}</div>
              <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 8px; background: #FAF9F6; padding: 8px 10px; border-radius: 4px;"><strong>【事实】</strong>${escapeHtml(p.factual_findings||'')}</div>
              <div style="font-size: 12px; color: #14233C; line-height: 1.5; background: rgba(20, 35, 60, 0.04); padding: 8px 10px; border-radius: 4px;"><strong>【路径】</strong>${escapeHtml(p.legal_breakthrough_logic||'')}</div>
              <div style="margin-top: 8px; font-size: 11px; color: #2E7D32; font-weight: 700;">救济：${escapeHtml(p.piercing_relief||'')}</div>
              ${p.related_company_note ? `<div style="margin-top:6px;font-size:11px;color:#92400E;">${escapeHtml(p.related_company_note)}</div>` : ''}`;
            return `
            <div style="background: #FFFFFF; border: 1px solid var(--border-color); border-radius: 8px; padding: 14px 16px; border-left: 4px solid ${escapeHtml(insufficient ? '#CA8A04' : '#B43434')};">
              <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 6px;">
                <div style="font-weight: 700; font-size: 13.5px; color: var(--text-primary);">
                  <span style="display: inline-block; padding: 1px 6px; font-size: 11px; background: ${escapeHtml(badgeBg)}; color: ${escapeHtml(badgeColor)}; border-radius: 4px; margin-right: 4px;">${escapeHtml(p.probe_id||'')}</span>
                  ${escapeHtml(p.probe_name||'')}
                </div>
                <span class="badge" style="background: ${escapeHtml(badgeBg)}; color: ${escapeHtml(badgeColor)}; font-size: 10px; font-weight: 700;">${escapeHtml(badge)}</span>
              </div>
              ${body}
            </div>`;
          }).join('');
        }

        // 3. 渲染探针状态拓扑（基于本次分析结果，无写死演示数字）
        const topologyBox = document.getElementById('enf-topology-box');
        if (topologyBox) {
          const probes = data.probes || [];
          const labelOf = (id, fallback) => {
            const p = probes.find(x => x.probe_id === id);
            if (!p) return fallback;
            if (p.status === 'INSUFFICIENT_FACTS') return id + ' 事实不足';
            return (p.probe_name || id) + (p.severity ? ' · ' + p.severity : '');
          };
          topologyBox.innerHTML = `
            <svg width="100%" height="210" viewBox="0 0 920 210" style="font-family: -apple-system, sans-serif;">
              <rect x="360" y="75" width="200" height="60" rx="8" fill="#14233C" stroke="#2B3A4F" stroke-width="2"/>
              <text x="460" y="100" fill="#FFFFFF" font-size="13" font-weight="bold" text-anchor="middle">被执行人（用户输入）</text>
              <text x="460" y="122" fill="#E2E8F0" font-size="11" text-anchor="middle">按探针事实生成</text>
              <rect x="20" y="15" width="250" height="60" rx="6" fill="#FFF5F5" stroke="#FEB2B2" stroke-width="1.5"/>
              <text x="145" y="48" fill="#9B2C2C" font-size="11" font-weight="bold" text-anchor="middle">${escapeHtml(labelOf('ENF-01','ENF-01'))}</text>
              <rect x="20" y="135" width="250" height="60" rx="6" fill="#FFF5F5" stroke="#FEB2B2" stroke-width="1.5"/>
              <text x="145" y="168" fill="#9B2C2C" font-size="11" font-weight="bold" text-anchor="middle">${escapeHtml(labelOf('ENF-02','ENF-02'))}</text>
              <rect x="650" y="15" width="250" height="60" rx="6" fill="#F0FDF4" stroke="#86EFAC" stroke-width="1.5"/>
              <text x="775" y="48" fill="#166534" font-size="11" font-weight="bold" text-anchor="middle">${escapeHtml(labelOf('ENF-03','ENF-03'))}</text>
              <rect x="650" y="135" width="250" height="60" rx="6" fill="#FEFCE8" stroke="#FDE047" stroke-width="1.5"/>
              <text x="775" y="168" fill="#854D0E" font-size="11" font-weight="bold" text-anchor="middle">${escapeHtml(labelOf('ENF-04','ENF-04'))}</text>
            </svg>
          `;
        }

        // 4. 渲染公文预览
        renderEnforcementDocPreview();
      } catch (e) {
        showToast("执行穿透审计失败: " + e);
      }
    }

    function switchEnforcementDocView(docType) {
      currentEnforcementDocView = docType;
      const btnApp = document.getElementById('btn-enfdoc-app');
      const btnLaw = document.getElementById('btn-enfdoc-lawsuit');

      if (btnApp && btnLaw) {
        if (docType === 'addition_application') {
          btnApp.style.background = 'var(--bg-card)';
          btnApp.style.color = 'var(--accent-amber)';
          btnApp.style.fontWeight = '700';
          btnLaw.style.background = 'transparent';
          btnLaw.style.color = 'var(--text-secondary)';
          btnLaw.style.fontWeight = '600';
        } else {
          btnLaw.style.background = 'var(--bg-card)';
          btnLaw.style.color = 'var(--accent-amber)';
          btnLaw.style.fontWeight = '700';
          btnApp.style.background = 'transparent';
          btnApp.style.color = 'var(--text-secondary)';
          btnApp.style.fontWeight = '600';
        }
      }
      renderEnforcementDocPreview();
    }

    function renderEnforcementDocPreview() {
      const box = document.getElementById('enf-doc-preview');
      if (!box || !currentEnforcementData) return;

      if (currentEnforcementDocView === 'addition_application') {
        box.innerText = currentEnforcementData.addition_application_text || "未生成申请书正文";
      } else {
        box.innerText = currentEnforcementData.objection_lawsuit_text || "未生成起诉状正文";
      }
    }

    function copyEnforcementDocument() {
      if (!currentEnforcementData) {
        showToast("暂无可复制的公文，请先启动分析");
        return;
      }
      const text = currentEnforcementDocView === 'addition_application' ? currentEnforcementData.addition_application_text : currentEnforcementData.objection_lawsuit_text;
      navigator.clipboard.writeText(text).then(() => {
        showToast("已成功复制公文全文至剪贴板！");
      }).catch(err => {
        showToast("复制失败: " + err);
      });
    }

    async function exportEnforcementDocxUI() {
      if (!currentEnforcementData) {
        showToast("请先执行穿透分析生成公文");
        return;
      }
      const title = currentEnforcementDocView === 'addition_application' ? "追加被执行人申请书（原出资股东及实控人）" : "民事起诉状（案外人虚假租赁执行异议之诉）";
      const text = currentEnforcementDocView === 'addition_application' ? currentEnforcementData.addition_application_text : currentEnforcementData.objection_lawsuit_text;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/enforcement/export-docx`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: title,
            content_text: text,
            doc_type: currentEnforcementDocView
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

        showToast(`已成功导出执行公文：${data.filename}`);
      } catch (e) {
        showToast("导出 Word 失败: " + e);
      }
    }

    // =========================================================================
    // 6. 模块 05：请求权基础与要件事实推演中枢 (Anspruchsgrundlage & Red Team Hub)
    // =========================================================================
    let currentDeepPerspective = 'plaintiff_blue_team';
    let currentDeepData = null;

    function changeDeepPreset() {
      const presetSelect = document.getElementById('deep-case-preset');
      const customPanel = document.getElementById('deep-custom-dossier-panel');
      if (presetSelect && presetSelect.value === 'custom') {
        if (customPanel) customPanel.style.display = 'block';
        loadCaseContextToDeepPanel();
      } else {
        if (customPanel) customPanel.style.display = 'none';
        runDeepMatrixAnalyze();
      }
    }

    function switchPerspective(perspective) {
      currentDeepPerspective = perspective;
      document.querySelectorAll('.perspective-btn').forEach(b => b.classList.remove('active'));
      if (perspective === 'plaintiff_blue_team') {
        const btnB = document.getElementById('btn-view-blue');
        if (btnB) btnB.classList.add('active');
        const lbl = document.getElementById('deep-perspective-label');
        if (lbl) {
          lbl.innerText = "己方主办律师视角 (Blue Team)";
          lbl.style.color = "var(--primary-navy)";
          lbl.style.background = "rgba(20, 35, 60, 0.08)";
        }
      } else {
        const btnR = document.getElementById('btn-view-red');
        if (btnR) btnR.classList.add('active');
        const lbl = document.getElementById('deep-perspective-label');
        if (lbl) {
          lbl.innerText = "对方红队律师质证视角 (Red Team)";
          lbl.style.color = "#B43434";
          lbl.style.background = "rgba(180, 52, 52, 0.12)";
        }
      }

      if (currentDeepData) {
        renderFactElements(currentDeepData.matrix_elements, perspective === 'adversarial_red_team');
      } else {
        runDeepMatrixAnalyze();
      }
    }

    async function runDeepMatrixAnalyze() {
      const presetSelect = document.getElementById('deep-case-preset');
      const preset = presetSelect ? presetSelect.value : "custom";
      if (preset === 'custom') {
        return submitCustomDeepMatrixAnalyze();
      }
      const perspective = currentDeepPerspective;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/deep-matrix/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ case_preset: preset, perspective: perspective })
        });
        const d = await resp.json();
        currentDeepData = d;

        // 渲染四大实证指标卡
        const scoreEl = document.getElementById('deep-metric-score');
        const readyScore = !!(d.scorecard && d.scorecard.is_litigation_ready);
        if (scoreEl) scoreEl.innerText = readyScore ? `${d.scorecard.completeness_score}%` : '未达起诉';
        const statusEl = document.getElementById('deep-metric-status');
        if (statusEl) {
          statusEl.innerText = d.scorecard.status_label;
          statusEl.style.color = d.scorecard.is_litigation_ready ? 'var(--status-valid)' : 'var(--status-warn)';
        }
        
        const rawEl = document.getElementById('deep-metric-raw');
        if (rawEl) rawEl.innerText = `${(d.raw_documents || []).length} 份录入材料`;
        const rawSub = document.getElementById('deep-metric-raw-sub');
        if (rawSub) rawSub.innerText = '坐标来自录入文本，没有和原件比对';
        const confEl = document.getElementById('deep-metric-conflicts');
        if (confEl) confEl.innerText = `${(d.detected_conflicts || []).length} 项需核对`;
        const ready = !!(d.scorecard && d.scorecard.is_litigation_ready);
        const guard = document.getElementById('deep-metric-guard');
        const guardSub = document.getElementById('deep-metric-guard-sub');
        if (guard) {
          guard.innerText = ready ? '可以对照要件' : '不能据此起诉';
          guard.style.color = ready ? 'var(--status-valid)' : 'var(--status-warn)';
        }
        if (guardSub) {
          guardSub.innerText = ready ? '仍须核对原件后再决定是否起诉' : '演示样例或证据未核对原件';
        }
        
        // 渲染一手卷宗库
        renderRawDossierList(d.raw_documents);

        // 渲染冲突横幅与时间轴
        renderTimelineAndConflicts(d.timeline_events, d.detected_conflicts);

        // 渲染要件事实矩阵
        renderFactElements(d.matrix_elements, perspective === 'adversarial_red_team');

        // 渲染可验证账本
        renderVerifiabilityLedger(d.verifiability_ledger, d.scorecard);

        showToast(`推演已完成。${(d.scorecard && d.scorecard.status_label) || '不能据此决定起诉'}`);
      } catch (e) {
        showToast("深度推演请求失败: " + e);
      }
    }

    function renderRawDossierList(docs) {
      const container = document.getElementById('deep-raw-dossier-list');
      if (!container) return;
      container.innerHTML = "";

      docs.forEach(doc => {
        const card = document.createElement('div');
        card.className = "raw-dossier-card";
        card.id = `raw-card-${doc.doc_id}`;
        
        let linesHtml = "";
        if (doc.content_lines && doc.content_lines.length > 0) {
          linesHtml = `<div style="margin-top:6px; background:#FFFFFF; border:1px solid #E2DFD7; padding:6px 8px; border-radius:3px; font-family:var(--font-mono); font-size:11px; max-height:120px; overflow-y:auto; line-height:1.6;">`;
          doc.content_lines.forEach(l => {
            linesHtml += `<div id="raw-line-${doc.doc_id}-${l.anchor}"><span style="color:var(--text-muted); user-select:none; margin-right:6px;">[${l.anchor}]</span><span>${l.text}</span></div>`;
          });
          linesHtml += `</div>`;
        }

        // safe-html: pre-escaped or nested HTML fragment
        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="badge" style="background:#14233C; color:#FFF; font-weight:700;">${escapeHtml(doc.doc_id)}</span>
              <strong style="color:var(--primary-navy);">${escapeHtml(doc.doc_name)}</strong>
            </div>
            <span style="font-size:10.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(doc.recorded_date)}</span>
          </div>
          <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary);">
            <span>类别：${escapeHtml(doc.doc_type)} · 来源：${escapeHtml(doc.source)}</span>
            <span style="color:var(--text-muted); font-size:10.5px;">${doc.hash_sha256 ? '文本哈希已记录，未与原件比对' : '未记录文本哈希'}</span>
          </div>
          <div style="font-size:10px; color:var(--text-muted); font-family:var(--font-mono); word-break:break-all;">
            哈希: ${escapeHtml(doc.hash_sha256)}
          </div>
          ${linesHtml}
        `;
        container.appendChild(card);
      });
    }

    function renderTimelineAndConflicts(events, conflicts) {
      // 1. 冲突预警
      const confArea = document.getElementById('deep-conflicts-area');
      if (confArea) {
        confArea.innerHTML = "";
        conflicts.forEach(c => {
          const div = document.createElement('div');
          div.className = `conflict-callout ${c.severity === 'CRITICAL' ? 'critical' : ''}`;
          div.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="color:${escapeHtml(c.severity === 'CRITICAL' ? 'var(--status-warn)' : 'var(--primary-navy)')}; font-size:12.5px;">
                ⚠️ ${escapeHtml(c.conflict_type)}
              </strong>
              <span class="badge" style="background:${escapeHtml(c.severity === 'CRITICAL' ? 'var(--status-warn-bg)' : 'rgba(197,133,50,0.1)')}; color:${escapeHtml(c.severity === 'CRITICAL' ? 'var(--status-warn)' : 'var(--accent-amber)')}; font-size:10px;">${escapeHtml(c.severity)}</span>
            </div>
            <div style="color:var(--text-secondary); line-height:1.4;">${escapeHtml(c.description)}</div>
            <div style="color:var(--status-valid); font-size:11.5px; margin-top:2px; font-weight:500;"><strong>【应对方案】</strong>${escapeHtml(c.remedy)}</div>
          `;
          confArea.appendChild(div);
        });
      }

      // 2. 时间轴事件
      const track = document.getElementById('deep-timeline-track');
      if (track) {
        track.innerHTML = "";
        events.forEach(ev => {
          const step = document.createElement('div');
          step.className = "timeline-step";
          // safe-html: pre-escaped or nested HTML fragment
          step.innerHTML = `
            <div class="timeline-dot ${escapeHtml(ev.risk_flag || '')}"></div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <strong style="font-size:12px; font-family:var(--font-mono); color:var(--primary-navy);">${escapeHtml(ev.date)}</strong>
              <span style="font-size:10.5px; color:var(--text-muted);">${escapeHtml(ev.source)}</span>
            </div>
            <div style="font-size:12px; color:var(--text-secondary); line-height:1.4;">${escapeHtml(ev.summary)}</div>
            ${ev.conflict_note ? `<div style="font-size:11px; color:var(--status-warn); font-weight:600; margin-top:2px;">${ev.conflict_note}</div>` : ''}
          `;
          track.appendChild(step);
        });
      }
    }

    function renderFactElements(elements, isRedTeam) {
      const container = document.getElementById('deep-matrix-container');
      if (!container) return;
      container.innerHTML = "";

      elements.forEach(el => {
        const card = document.createElement('div');
        const statusClass = el.proof_status === 'PROVEN' ? 'proven' : (el.proof_status === 'UNPROVEN' ? 'unproven' : 'isolated');
        card.className = `element-card ${statusClass}`;

        let pillsHtml = "";
        if (el.grounded_citations && el.grounded_citations.length > 0) {
          el.grounded_citations.forEach(c => {
            pillsHtml += `<span role="button" tabindex="0" class="citation-pill" onclick="locateRawDossierSnippet('${c.doc_id}', '${c.anchor}')" title="点击定位并高亮一手原始证据行">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>
              <span>[${c.anchor}]</span>
            </span> `;
          });
        }

        // 红队视角与蓝队视角卡片核心内容呈现
        let perspectiveSectionHtml = "";
        if (isRedTeam) {
          perspectiveSectionHtml = `
            <div class="attack-box-red">
              <div style="font-weight:700; display:flex; align-items:center; gap:5px; margin-bottom:4px;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
                <span>对方红队律师极端攻击视角 (Adversarial Vector)</span>
              </div>
              <div>${el.adversarial_attack}</div>
            </div>
            <div style="font-size:11.5px; color:var(--text-secondary); margin-top:4px;">
              <strong>【我方预置阻断方案】</strong> ${el.counter_strategy}
            </div>
          `;
        } else {
          perspectiveSectionHtml = `
            <div class="counter-box-blue">
              <div style="font-weight:700; display:flex; align-items:center; gap:5px; margin-bottom:4px;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                <span>己方主办律师证明与防御策略 (Proof Defense)</span>
              </div>
              <div>${el.counter_strategy}</div>
            </div>
            <div style="font-size:11.5px; color:#8C2222; background:rgba(180,52,52,0.05); padding:6px 8px; border-radius:3px; margin-top:4px;">
              <strong>【防范对方抗辩】</strong> ${el.opponent_defense}
            </div>
          `;
        }

        // safe-html: pre-escaped or nested HTML fragment
        card.innerHTML = `
          <div class="element-card-header">
            <div style="display:flex; align-items:center; gap:8px;">
              <span class="badge" style="background:var(--primary-navy); color:#FFF; font-weight:700;">${escapeHtml(el.element_id)}</span>
              <strong style="color:var(--primary-navy); font-size:13.5px;">${escapeHtml(el.element_name)}</strong>
            </div>
            <span class="element-badge ${escapeHtml(el.proof_status === 'PROVEN' ? 'valid' : 'warn')}">
              ${escapeHtml(el.proof_status === 'PROVEN' ? '✓ 摘录已对应' : '⚠ 待补强')}
            </span>
          </div>
          <div>
            <span class="element-basis-tag">${escapeHtml(el.claim_basis)}</span>
          </div>
          <div style="font-size:12.5px; color:var(--text-primary); line-height:1.5;">
            <strong>主张要件事实：</strong>${escapeHtml(el.asserted_fact)}
          </div>
          <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap; font-size:11.5px;">
            <span style="color:var(--text-muted);">一手卷宗锚点：</span>
            ${pillsHtml}
          </div>
          <div style="font-size:11px; color:var(--text-secondary); background:var(--bg-subtle); padding:6px 8px; border-radius:3px;">
            <strong>举证责任分配：</strong>${escapeHtml(el.burden_of_proof)}
          </div>
          ${perspectiveSectionHtml}
        `;
        container.appendChild(card);
      });
    }

    function renderVerifiabilityLedger(ledger, scorecard) {
      const box = document.getElementById('deep-verifiability-box');
      if (!box) return;
      box.innerHTML = `
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:8px;">
          <div style="background:#FFFFFF; border:1px solid #E2DFD7; padding:8px 10px; border-radius:4px;">
            <div style="color:var(--text-muted); font-size:11px;">判定引擎</div>
            <strong style="color:var(--primary-navy); font-size:12.5px;">${escapeHtml(ledger.verifier_name)}</strong>
          </div>
          <div style="background:#FFFFFF; border:1px solid #E2DFD7; padding:8px 10px; border-radius:4px;">
            <div style="color:var(--text-muted); font-size:11px;">能否据此起诉</div>
            <strong style="color:${escapeHtml(scorecard.is_litigation_ready ? 'var(--status-valid)' : 'var(--status-warn)')}; font-size:12.5px;">${escapeHtml(scorecard.status_label)}</strong>
          </div>
        </div>
        <div>• <strong>素材指纹：</strong>${escapeHtml(ledger.hash_verification)}</div>
        <div>• <strong>坐标说明：</strong>${escapeHtml(ledger.grounding_coverage)}</div>
        <div>• <strong>法条检索：</strong>${escapeHtml(ledger.statute_validity_check)}</div>
        <div>• <strong>利率与违约金：</strong>${escapeHtml(ledger.redline_risk_status)}</div>
      `;
    }

    function locateRawDossierSnippet(docId, anchor) {
      const card = document.getElementById(`raw-card-${docId}`);
      if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
        card.style.borderColor = "#C58532";
        card.style.boxShadow = "0 0 10px rgba(197, 133, 50, 0.4)";
        setTimeout(() => {
          card.style.borderColor = "";
          card.style.boxShadow = "";
        }, 2200);
      }
      showToast(`已快速锚定原始凭证 [${docId} : ${anchor}]`);
    }

    function exportDeepMatrixReport() {
      if (!currentDeepData) {
        showToast("请先执行深度要件推演");
        return;
      }
      const d = currentDeepData;
      let md = `# LawFlow 智律工作台 —— 请求权基础与要件事实质证对抗报告\n\n`;
      md += `**案件名称**：${d.case_title}\n`;
      md += `**案由**：${d.cause_of_action} | **涉案标的**：¥${d.claim_amount.toLocaleString()}\n`;
      md += `**完备率评分**：${d.scorecard.completeness_score}% (${d.scorecard.status_label})\n\n`;
      md += `## 一、七维要件事实推演矩阵\n\n`;
      d.matrix_elements.forEach(el => {
        md += `### 【${el.element_id}】${el.element_name} [${el.proof_status}]\n`;
        md += `- **请求权基础**：${el.claim_basis}\n`;
        md += `- **己方主张事实**：${el.asserted_fact}\n`;
        md += `- **一手卷宗锚点**：${el.grounded_citations.map(c=>`[${c.anchor} : ${c.doc_name}]`).join(', ')}\n`;
        md += `- **对方抗辩预测**：${el.opponent_defense}\n`;
        md += `- **红队攻击切入**：${el.adversarial_attack}\n`;
        md += `- **反制补强策略**：${el.counter_strategy}\n\n`;
      });
      md += `## 二、多源时间轴交叉质证侦测到的冲突\n\n`;
      d.detected_conflicts.forEach(c => {
        md += `- **[${c.severity}] ${c.conflict_type}**：${c.description}\n  *应对方案*：${c.remedy}\n`;
      });
      md += `\n## 三、外部客观实证验证账本\n\n`;
      md += `- 素材指纹：${d.verifiability_ledger.hash_verification}\n`;
      md += `- 坐标说明：${d.verifiability_ledger.grounding_coverage}\n`;
      md += `- 法条检索：${d.verifiability_ledger.statute_validity_check}\n`;
      md += `- 利率与违约金：${d.verifiability_ledger.redline_risk_status}\n`;

      copyToClipboard(md, "已成功导出《要件事实与出庭质证对抗报告》！");
    }


    async function runAdversarialAttackUI() {
      const evName = document.getElementById('ev-attack-name')?.value.trim() || "";
      const plaintiffPurpose = document.getElementById('ev-attack-purpose')?.value.trim() || "";
      const rawSnippet = document.getElementById('ev-attack-snippet')?.value.trim() || "";
      if (!evName || !plaintiffPurpose || !rawSnippet) {
        showToast("请填写我方证据名称、证明目的和可能被抓住的原文");
        return;
      }
      showToast("正在模拟对方资深争议解决律师发动红队质证攻击...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/deep-matrix/adversarial-attack`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            evidence_name: evName,
            plaintiff_purpose: plaintiffPurpose,
            raw_snippet: rawSnippet
          })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderAdversarialAttackResult(data);
        switchPhase2RightTab('tools');
        showToast("红队质证攻击预案已生成");
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function renderAdversarialAttackResult(data) {
      const container = document.getElementById('ev-tools-result-container');
      if (!container) return;
      const attacks = data.attacks || [];
      const attackCards = attacks.map((atk, idx) => {
        const qHtml = (atk.drill_questions || []).map(q => `<li style="margin-bottom:3px;">${escapeHtml(q)}</li>`).join('');
        return `
          <div style="border: 1px solid #FECACA; background: #FEF2F2; border-radius: 4px; padding: 10px 12px; margin-bottom: 8px;">
            <strong style="font-size: 12px; color: #991B1B;">${escapeHtml(String(idx + 1))}. ${escapeHtml(atk.dimension || '')}</strong>
            <div style="font-size: 11.5px; color: #7F1D1D; margin: 4px 0 6px 0; line-height: 1.4;">${escapeHtml(atk.attack_angle || '')}</div>
            <div style="font-size: 11px; color: #991B1B; font-weight: 600;">对方当庭可能发问提纲：</div>
            <ul style="padding-left: 18px; font-size: 11.5px; color: #7F1D1D; margin-top: 2px;">${qHtml}</ul>
          </div>
        `;
      }).join('');
      const remedies = (data.remedy_checklist || []).map(r => `<div style="font-size: 11.5px; color: #065F46; line-height: 1.5;">${escapeHtml(r)}</div>`).join('');
      // safe-html: adversarial attack cards and remedy checklist
      container.innerHTML = `
        <div style="padding: 12px 14px;">
          <div style="margin-bottom: 12px;">
            <strong style="font-size: 14px; color: #991B1B;">《对方代理律师红队攻击预警与防御预案》</strong>
            <div style="font-size: 11.5px; color: var(--text-muted); margin-top:2px;">提前识别我方核心证据潜在破绽与对方针对性发问要点</div>
          </div>
          <div>${attackCards}</div>
          <div style="border: 1px solid #A7F3D0; background: #ECFDF5; border-radius: 4px; padding: 10px 12px; margin-top: 8px;">
            <strong style="font-size: 12px; color: #065F46;">🛡️ 我方出庭前补强与防御清单：</strong>
            <div style="margin-top: 4px; display: flex; flex-direction: column; gap: 3px;">${remedies}</div>
          </div>
        </div>
      `;
    }

export {
  switchDeepMatrixSubTab,
  runEnforcementAuditUI,
  switchEnforcementDocView,
  renderEnforcementDocPreview,
  copyEnforcementDocument,
  exportEnforcementDocxUI,
  changeDeepPreset,
  switchPerspective,
  runDeepMatrixAnalyze,
  renderRawDossierList,
  renderTimelineAndConflicts,
  renderFactElements,
  renderVerifiabilityLedger,
  locateRawDossierSnippet,
  exportDeepMatrixReport,
  runAdversarialAttackUI,
  renderAdversarialAttackResult,
  currentDeepData,
};

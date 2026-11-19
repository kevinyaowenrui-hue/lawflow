/**
 * LawFlow Module: 07_matters.js
 */
import { api, ApiError, API_BASE, withDownloadToken, escapeHtml } from '../api.js';
import { showToast } from '../ui/toast.js';
import {
  EMPTY_CASE_FILL_HINT,
  CALC_SYNC_EMPTY_MESSAGE,
  buildCaseContextFromMatter,
  describeCaseOverwrites,
  planCalcSync,
} from './case_sync_rules.js';


// safe-html: static tab template
export const MATTERS_TAB_HTML = `      
      <!-- 1. 顶部当前案件空间元数据看板卡片 -->
      <div class="surface-card" style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
          <div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 15px; font-weight: 700; color: var(--primary-navy);" id="vault-matter-title">未选择案件</span>
              <span class="badge" id="vault-matter-cause-badge" style="background: rgba(20, 35, 60, 0.1); color: var(--primary-navy); font-weight: 700;"></span>
              <span class="badge" id="vault-matter-status-badge" style="background: #E8F5E9; color: #2E7D32;"></span>
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 5px; display: flex; gap: 14px; flex-wrap: wrap;">
              <span>案号：<strong id="vault-matter-caseno" style="font-family: var(--font-mono); color: var(--primary-navy);"></strong></span>
              <span>受诉法院：<strong id="vault-matter-court" style="color: var(--primary-navy);"></strong></span>
              <span>诉讼标的：<strong id="vault-matter-amount" style="font-family: var(--font-mono); color: var(--accent-amber);"></strong></span>
              <span>委托人地位：<strong id="vault-matter-role" style="color: var(--primary-navy);"></strong></span>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <button type="button" class="btn btn-primary btn-sm" id="btn-create-matter-empty" style="display:none;" onclick="openMatterVaultModal(); openNewMatterDrawer();">
              新建案件
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="openMatterVaultModal()">
              📁 切换/管理案件空间
            </button>
            <button type="button" class="btn btn-secondary btn-sm" onclick="openMountDocModal()">
              ＋ 挂载案卷材料
            </button>
            <button type="button" class="btn btn-amber btn-sm" onclick="runExtractMatterGraphs()" id="btn-extract-graphs">
              ⚡ 重新智能抽取三大图谱
            </button>
          </div>
        </div>
      </div>

      <!-- 2. 图谱视图 Tab 切换栏 -->
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid var(--border-hairline); padding-bottom: 8px; flex-wrap: wrap; gap: 8px;">
        <div style="display: flex; gap: 6px; flex-wrap: wrap;">
          <button type="button" class="tab-pill-btn active" id="btn-vault-tab-timeline" onclick="switchVaultGraphTab('timeline')">
            📅 案件事实发生时间线 (Timeline)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-entity" onclick="switchVaultGraphTab('entity')">
            🕸️ 人物主体与担保法律关系图 (Entity-Graph)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-cashflow" onclick="switchVaultGraphTab('cashflow')">
            💰 交易支付与资金穿透流水图 (Cashflow)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-docs" onclick="switchVaultGraphTab('docs')">
            📂 空间挂载案卷材料库 (<span id="vault-docs-count">0</span>)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-grid" onclick="switchVaultGraphTab('grid')">
            📊 矩阵式批量阅卷表 (Review Grid)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-deadlines" onclick="switchVaultGraphTab('deadlines')">
            📅 案件期限日历 (Deadlines)
          </button>
          <button type="button" class="tab-pill-btn" id="btn-vault-tab-filing" onclick="switchVaultGraphTab('filing')">
            立案清单与收费备忘
          </button>
        </div>
        <div style="font-size: 11.5px; color: var(--text-muted);">
          与 01精算、02立案、03审查、05要件推演实时上下文隔离与共享
        </div>
      </div>

      <!-- 3. 图谱面板容器 -->
      <!-- 面板 A: 事实时间线 -->
      <div id="pane-vault-timeline" class="vault-graph-pane">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">《案件事实发生时间线与法律效力节点》</span>
            <span style="font-size: 11px; color: var(--text-muted);">自动按发生时间升序编排 · 标注证据支撑与诉讼法律意义</span>
          </div>
          <div id="vault-timeline-list" class="vault-timeline">
            <!-- 动态渲染时间线节点 -->
          </div>
        </div>
      </div>

      <!-- 面板 B: 人物主体与担保法律关系拓扑图大屏 -->
      <div id="pane-vault-entity" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div>
              <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
                <span>《诉讼当事人、多方交叉担保与物保人保受偿拓扑大屏》</span>
                <span class="badge" style="background: rgba(197, 133, 50, 0.1); color: var(--accent-amber); font-size: 10.5px;">《民法典》第692/392条联动</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                智能监控保证期间除斥灭失线 · 债务人物保优先执行法定顺位 · 企业关联担保决议效力穿透
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="runGuaranteeAnalysisUI()">
                ⚡ 执行保证期间与物保顺位审计
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="copyGuaranteeTacticalMemo()">
                📋 复制合伙人风控备忘录
              </button>
            </div>
          </div>

          <!-- 保证期间与物保受偿状态指示看板 -->
          <div id="vault-guarantee-summary-bar" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin-bottom: 14px;">
            <!-- 动态注入保证期间与物保状态 -->
          </div>

          <!-- 交互式原生 SVG 担保拓扑图视窗 -->
          <div id="vault-topology-svg-container" style="background: #FDFDFD; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 12px; margin-bottom: 14px; min-height: 220px; overflow-x: auto; position: relative;">
            <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px; display: flex; justify-content: space-between;">
              <span>🕸️ 交互式担保关系与物保顺位网络图谱 (点击节点或连线查看权利义务及法条依据)：</span>
              <span style="font-family: var(--font-mono); font-size: 10.5px; color: var(--accent-amber);">SVG 原生向量渲染</span>
            </div>
            <div id="vault-topology-canvas-wrap" style="width: 100%; min-width: 600px; height: 260px;">
              <!-- 动态绘制 SVG 拓扑网络 -->
            </div>
          </div>

          <!-- 主体卡片列表与保证人详细审查明细 -->
          <div id="vault-entity-content">
            <!-- 动态渲染主体卡片与法律关系 -->
          </div>
        </div>
      </div>

      <!-- 面板 C: 交易支付与资金穿透流水大屏 (含民法典561条法定冲抵) -->
      <div id="pane-vault-cashflow" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div>
              <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
                <span>《涉案交易支付与资金穿透流水全链路大屏》</span>
                <span class="badge" style="background: #E0F2FE; color: #0369A1; font-size: 10.5px;">民法典第561条法定冲抵引擎</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                穿透转账凭证与第三方代收 · 自动按【费用 ➔ 利息 ➔ 本金】冲抵重算 · 侦测同日回流与砍头息
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <!-- 视图模式切换 -->
              <div class="segmented-control" style="font-size: 11.5px;">
                <button type="button" class="segmented-btn active" id="btn-cf-mode-art561" onclick="switchCashflowMode('art561')">
                  ⚖️ 民法典561条冲抵对账
                </button>
                <button type="button" class="segmented-btn" id="btn-cf-mode-nominal" onclick="switchCashflowMode('nominal')">
                  📄 原始银行名义流水
                </button>
              </div>
              <button type="button" class="btn btn-secondary btn-sm" onclick="copyCashflowStatement()">
                📋 复制法庭对账质证意见
              </button>
            </div>
          </div>

          <!-- 异常风险预警横幅 (若检测到同日回流、第三方代收无授权、附言冲突) -->
          <div id="vault-cashflow-redflags" style="display: none; margin-bottom: 12px;"></div>

          <!-- 核心资金指标卡 -->
          <div id="vault-cashflow-metrics" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin-bottom: 14px;">
            <!-- 动态渲染资金指标卡 -->
          </div>

          <!-- 资金流水表格容器 -->
          <div style="overflow-x: auto; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm);">
            <table class="data-table" style="width: 100%; font-size: 12px; margin: 0;">
              <thead id="vault-cashflow-table-head">
                <!-- 动态切换表头 -->
              </thead>
              <tbody id="vault-cashflow-table-body">
                <!-- 动态渲染资金行 -->
              </tbody>
            </table>
          </div>

          <!-- 质证意见与法言法语说明纸折叠盒 -->
          <div id="vault-cashflow-statement-box" style="margin-top: 14px; background: #FAF9F6; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 12px 14px;">
            <div style="font-size: 12px; font-weight: 700; color: var(--primary-navy); margin-bottom: 6px; display: flex; justify-content: space-between;">
              <span>📝 法庭质证专用·本息分段冲抵对账意见说明（可直接注入代理词）</span>
              <button type="button" class="btn btn-secondary btn-sm" onclick="copyCashflowStatement()" style="font-size: 10.5px; padding: 2px 6px;">一键复制</button>
            </div>
            <div id="vault-cashflow-statement-text" style="font-family: var(--font-serif); font-size: 11.5px; line-height: 1.6; color: var(--text-secondary); white-space: pre-wrap; max-height: 180px; overflow-y: auto;">
              暂无对账意见
            </div>
          </div>

        </div>
      </div>

      <!-- 面板 D: 空间案卷材料库 -->
      <div id="pane-vault-docs" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
            <span style="font-size: 13px; font-weight: 700; color: var(--primary-navy);">《案件空间挂载案卷材料与原始证据库》</span>
            <button type="button" class="btn btn-secondary btn-sm" onclick="openMountDocModal()">
              ＋ 挂载新材料
            </button>
          </div>

          <!-- 批量上传与拖拽区域 -->
          <div class="surface-card" style="margin-bottom: 14px; border: 2px dashed var(--border-hairline); border-radius: var(--radius-md); padding: 18px; text-align: center; background: #FAF9F6;" id="vault-dnd-upload-box">
            <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 5px;">
              📁 拖拽卷宗文件至此 或 点击选择文件上传
            </div>
            <div style="font-size: 11.5px; color: var(--text-secondary); margin-bottom: 10px;">
              支持多选批量上传 PDF / Word (.docx, .doc) / 图片 (PNG, JPG) / CSV 等卷宗材料，自动解析文本并挂载至本案
            </div>
            <input aria-label="vault batch file input"  type="file" id="vault-batch-file-input" multiple accept=".pdf,.docx,.doc,.png,.jpg,.jpeg,.heic,.csv,.xlsx,.txt" style="display: none;" onchange="handleVaultBatchFilesSelect(event)">
            <button type="button" class="btn btn-amber btn-sm" onclick="document.getElementById('vault-batch-file-input').click()">
              选择文件上传 (可多选)
            </button>
            <div id="vault-upload-progress-list" style="margin-top: 12px; text-align: left; display: flex; flex-direction: column; gap: 6px;"></div>
          </div>

          <div id="vault-docs-list" style="display: flex; flex-direction: column; gap: 10px;">
            <!-- 动态渲染案卷材料 -->
          </div>
        </div>
      </div>

      <!-- 面板 E: 矩阵式批量阅卷表 (Harvey Review Tables) -->
      <div id="pane-vault-grid" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div>
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy);" id="vault-grid-title">借贷纠纷与担保核心合同要素审查阅卷矩阵</span>
                <span class="badge" id="vault-grid-badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 11px;">Harvey 矩阵阅卷架构</span>
                <span class="badge" style="background: #E8F5E9; color: #2E7D32; font-size: 11px;">支持单格异步重刷</span>
              </div>
              <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 3px;" id="vault-grid-desc">
                行 = 案件挂载材料/合同证据 · 列 = 提取要素（支持单格异步重刷与列级指令重跑）
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="openAddReviewColumnModal()">
                ＋ 动态新增要素提取列
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="runAllReviewTableUI()" id="btn-run-all-grid">
                ⚡ 全表并发提取重跑
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="exportReviewTableXlsxUI()">
                📥 导出为 Excel (.xlsx)
              </button>
              <button type="button" class="btn btn-amber btn-sm" onclick="exportReviewTableCsvUI()">
                📥 导出阅卷表为 CSV
              </button>
            </div>
          </div>

          <!-- DataGrid 表格容器 -->
          <div class="review-grid-container" id="vault-review-datagrid">
            <!-- 动态渲染数据网格 -->
          </div>
        </div>
      </div>

      <!-- 面板 F: 案件期限日历 (Deadlines Calendar) -->
      <div id="pane-vault-deadlines" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
            <div>
              <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); display: flex; align-items: center; gap: 6px;">
                <span>《案件法定诉讼期限与执业红线监控日历》</span>
                <span class="badge" style="background: rgba(197, 133, 50, 0.1); color: var(--accent-amber); font-size: 10.5px;">≤7日到期警示</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                实时汇总诉讼时效、上诉期、续行保全、执行申请与开庭节点 · 支持自动高亮紧急期限
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 8px;">
              <button type="button" class="btn btn-secondary btn-sm" onclick="openAddDeadlineModal()">
                ＋ 手工录入期限
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="fetchAndRenderVaultDeadlines()">
                🔄 刷新期限
              </button>
            </div>
          </div>

          <div id="vault-deadlines-list" style="display: flex; flex-direction: column; gap: 8px;">
            <!-- 动态渲染期限条目 -->
          </div>
        </div>
      </div>

      <div id="pane-vault-filing" class="vault-graph-pane" style="display: none;">
        <div class="surface-card">
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy);">立案材料清单</div>
          <div style="font-size: 12px; color: #92400E; line-height: 1.55; margin: 6px 0 10px;">
            没有法院电子立案接口。下列状态只能由律师自己勾选：未准备、已准备、已线下提交、补正中。系统不推测法院已经受理或立案。
          </div>
          <div id="filing-checklist-rows" style="display: flex; flex-direction: column; gap: 8px;"></div>
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-top: 16px;">已开票金额</div>
          <div id="ledger-receivable-hint" style="font-size: 12px; color: var(--text-secondary); margin: 4px 0 8px;"></div>
          <input aria-label="已开票金额" type="number" id="ledger-fee-invoiced" class="quick-input" min="0" step="0.01" placeholder="不能大于应收，留空表示还没开票" style="max-width: 280px;">
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-top: 16px;">用印登记</div>
          <div style="font-size: 12px; color: var(--text-muted); margin: 4px 0 8px;">只记录文件名、份数和日期，不发起用印审批。</div>
          <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center;">
            <input aria-label="用印文件名" type="text" id="seal-filename" class="quick-input" placeholder="文件名，例如授权委托书" style="max-width: 240px;">
            <input aria-label="用印份数" type="number" id="seal-copies" class="quick-input" min="1" step="1" placeholder="份数" style="max-width: 100px;">
            <input aria-label="用印日期" type="date" id="seal-date" class="quick-input" style="max-width: 170px;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="addSealDraft()">加入</button>
          </div>
          <div id="seal-record-list" style="margin-top: 8px;"></div>
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-top: 16px;">委托确定后的律师费</div>
          <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:8px;">
            <input aria-label="约定收费" type="number" id="ledger-fee-amount" class="quick-input" min="0" step="0.01" placeholder="约定金额" style="max-width:160px;">
            <input aria-label="已到账" type="number" id="ledger-fee-received" class="quick-input" min="0" step="0.01" placeholder="已到账" style="max-width:160px;">
          </div>
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy); margin-top: 16px;">当地额外材料</div>
          <div id="local-filing-rows" style="display:flex; flex-direction:column; gap:8px; margin-top:8px;"></div>
          <div style="display:flex; gap:8px; margin-top:8px;">
            <input aria-label="额外材料名称" type="text" id="local-filing-label" class="quick-input" placeholder="例如：某中院要求的送达确认附表" style="max-width:320px;">
            <button type="button" class="btn btn-secondary btn-sm" onclick="addLocalFilingRow()">添加</button>
          </div>
          <div style="display: flex; justify-content: flex-end; margin-top: 12px;">
            <button type="button" class="btn btn-sm" onclick="saveMatterLedger()">保存清单、开票和用印</button>
          </div>
        </div>
        <div class="surface-card" style="margin-top: 12px;" id="practice-desk-card">
          <div style="font-size: 13.5px; font-weight: 700; color: var(--primary-navy);">并列请求、管辖和结案</div>
          <div id="practice-desk-body" style="font-size: 12px; color: var(--text-secondary); margin-top: 8px;">打开立案清单后显示。</div>
        </div>
      </div>

    </section>

    <!-- ========================================================================
         08 智律 AI 语音中枢与全模块联动工作台 (Phase 8 AI Copilot Workspace)
         ======================================================================== -->
`;

export function renderTabMatters() {
  const el = document.getElementById('tab-graphs');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = MATTERS_TAB_HTML;
  }
}


    // =========================================================================
    // 7. 全局在办案件上下文总线 (Global Case Context Bus)
    //    打通 01实务精算、02立案文书、03证据清洗、05要件推演、06法典检索孤岛
    // =========================================================================
    const CaseContextStore = {
      KEY: 'lawflow_case_context_v2',
      defaultState: {
        matter_id: "",
        title: "",
        cause: "",
        court: "",
        amount: 0,
        plaintiff: {
          name: "",
          id: "",
          phone: "",
          address: ""
        },
        defendant: {
          name: "",
          id: "",
          phone: "",
          address: ""
        },
        interest_calc: {
          principal: 0,
          start_date: "",
          end_date: "",
          interest_total: 0,
          formal_statement: "",
          court_fee: 0,
          preservation_fee: 0
        },
        statutes: [],
        facts: "",
        evidence_notes: ""
      },
      get() {
        try {
          const raw = localStorage.getItem(this.KEY);
          if (raw) return JSON.parse(raw);
        } catch (e) {
          console.warn("读取案件上下文失败:", e);
        }
        return JSON.parse(JSON.stringify(this.defaultState));
      },
      save(data) {
        try {
          localStorage.setItem(this.KEY, JSON.stringify(data));
          renderGlobalCaseBar();
          updateTabContextDisplays();
        } catch (e) {
          console.warn("保存案件上下文失败:", e);
        }
      },
      hasStatute(articleId) {
        const c = this.get();
        return (c.statutes || []).some(s => s.id === articleId);
      },
      resetDefault() {
        this.save(this.defaultState);
      },
      clearNew() {
        const blank = {
          matter_id: "",
          title: "新办案件",
          cause: "通用民商事纠纷",
          court: "",
          amount: 0,
          plaintiff: { name: "", id: "", phone: "", address: "" },
          defendant: { name: "", id: "", phone: "", address: "" },
          interest_calc: { principal: 0, start_date: "", end_date: "", interest_total: 0, formal_statement: "", court_fee: 0, preservation_fee: 0 },
          statutes: [],
          facts: "",
          evidence_notes: ""
        };
        this.save(blank);
      }
    };
    window.CaseContextStore = CaseContextStore;

    function renderGlobalCaseBar() {
      const c = CaseContextStore.get();
      const causeEl = document.getElementById('gcase-cause');
      if (causeEl) causeEl.innerText = c.cause || "在办案件";
      const titleEl = document.getElementById('gcase-title');
      if (titleEl) titleEl.innerText = c.title || "未选择案件";
      const pEl = document.getElementById('gcase-plaintiff');
      if (pEl) pEl.innerText = (c.plaintiff && c.plaintiff.name) ? c.plaintiff.name : "未指定";
      const dEl = document.getElementById('gcase-defendant');
      if (dEl) dEl.innerText = (c.defendant && c.defendant.name) ? c.defendant.name : "未指定";
      const amtEl = document.getElementById('gcase-amount');
      if (amtEl) amtEl.innerText = `¥${(c.amount || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

      const calcSumEl = document.getElementById('gcase-calc-summary');
      if (calcSumEl) {
        if (c.interest_calc && c.interest_calc.interest_total > 0) {
          const feePart = c.interest_calc.court_fee > 0
            ? ` · 诉讼费¥${Math.round(c.interest_calc.court_fee).toLocaleString()}`
            : "";
          calcSumEl.innerText = `精算: 利息¥${Math.round(c.interest_calc.interest_total).toLocaleString()}${feePart}`;
        } else if (c.interest_calc && c.interest_calc.court_fee > 0) {
          calcSumEl.innerText = `精算: 诉讼费¥${Math.round(c.interest_calc.court_fee).toLocaleString()}`;
        } else {
          calcSumEl.innerText = "精算: 尚未计算";
        }
      }

      const statSumEl = document.getElementById('gcase-statutes-summary');
      if (statSumEl) {
        const count = (c.statutes || []).length;
        statSumEl.innerText = `请求权依据: ${count} 条`;
      }

      const eviSumEl = document.getElementById('gcase-evidence-summary');
      if (eviSumEl) {
        const lines = (c.evidence_notes || '').split('\n').filter(l => l.trim().length > 0);
        eviSumEl.innerText = `证据材料: ${lines.length} 份`;
      }
      if (typeof window.refreshFilingStepLabel === 'function') window.refreshFilingStepLabel();
    }

    function updateTabContextDisplays() {
      const c = CaseContextStore.get();
      const tab02Summary = document.getElementById('litigation-context-summary');
      if (tab02Summary) {
        tab02Summary.innerText = `${c.cause} · ${c.plaintiff?.name || '原告'}诉${c.defendant?.name || '被告'} (标的 ¥${(c.amount || 0).toLocaleString()}) · ${(c.statutes || []).length}条请求权依据`;
      }
      const deepCount = document.getElementById('deep-custom-statutes-count');
      if (deepCount) {
        deepCount.innerText = (c.statutes || []).length;
      }
    }

    function readCalcSyncInput() {
      const principalEl = document.getElementById('lpr-p');
      const startEl = document.getElementById('lpr-start');
      const endEl = document.getElementById('lpr-end');
      const metricEl = document.getElementById('metric-v1');
      const statementEl = document.getElementById('legal-statement-text');
      return {
        principal: principalEl ? principalEl.value : '',
        start: startEl ? startEl.value : '',
        end: endEl ? endEl.value : '',
        interestText: metricEl ? (metricEl.innerText || metricEl.textContent || '') : '',
        statement: statementEl ? (statementEl.innerText || statementEl.textContent || '') : '',
        mode: (typeof window !== 'undefined' && window.currentCalcMode) || 'lpr',
        feeSnapshot: (typeof window !== 'undefined' && window.lastCourtFeeSnapshot) || null,
      };
    }

    function showCalcSyncEmptyNotice() {
      let el = document.getElementById('calc-sync-empty-notice');
      if (!el) {
        el = document.createElement('div');
        el.id = 'calc-sync-empty-notice';
        el.setAttribute('role', 'status');
        el.style.cssText = 'margin:8px 0;padding:8px 10px;background:#FEF3C7;color:#92400E;border:1px solid #FDE68A;border-radius:4px;font-size:12px;';
        const text = document.createElement('span');
        text.textContent = CALC_SYNC_EMPTY_MESSAGE;
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.textContent = '关闭';
        dismiss.style.marginLeft = '8px';
        dismiss.addEventListener('click', dismissCalcSyncEmptyNotice);
        el.appendChild(text);
        el.appendChild(dismiss);
        const syncBtn = document.querySelector('button[onclick="syncCurrentCalcToCaseContext()"]');
        const host = (syncBtn && syncBtn.closest && syncBtn.closest('.docket-receipt-paper'))
          || document.getElementById('metric-summary-box')
          || document.body;
        if (syncBtn && syncBtn.parentElement && host.contains(syncBtn)) {
          syncBtn.parentElement.insertAdjacentElement('afterend', el);
        } else if (host && host.prepend) {
          host.prepend(el);
        }
      }
      el.hidden = false;
      el.style.display = 'block';
    }

    function dismissCalcSyncEmptyNotice() {
      const el = document.getElementById('calc-sync-empty-notice');
      if (!el) return;
      el.hidden = true;
      el.style.display = 'none';
    }

    function hideCalcSyncEmptyNoticeIfFilled() {
      const principal = document.getElementById('lpr-p')?.value.trim();
      const start = document.getElementById('lpr-start')?.value.trim();
      const end = document.getElementById('lpr-end')?.value.trim();
      if (principal || start || end) dismissCalcSyncEmptyNotice();
    }

    function syncCurrentCalcToCaseContext() {
      let plan;
      try {
        plan = planCalcSync(readCalcSyncInput());
      } catch (e) {
        showCalcSyncEmptyNotice();
        return false;
      }
      if (!plan.ok || !plan.patch) {
        showCalcSyncEmptyNotice();
        return false;
      }
      dismissCalcSyncEmptyNotice();
      const c = CaseContextStore.get();
      const prev = c.interest_calc || {};
      const patch = plan.patch;
      if (Object.prototype.hasOwnProperty.call(patch, 'amount')) c.amount = patch.amount;
      c.interest_calc = {
        principal: Object.prototype.hasOwnProperty.call(patch, 'principal') ? patch.principal : (prev.principal || 0),
        start_date: Object.prototype.hasOwnProperty.call(patch, 'start_date') ? patch.start_date : (prev.start_date || ''),
        end_date: Object.prototype.hasOwnProperty.call(patch, 'end_date') ? patch.end_date : (prev.end_date || ''),
        interest_total: Object.prototype.hasOwnProperty.call(patch, 'interest_total') ? patch.interest_total : (prev.interest_total || 0),
        formal_statement: Object.prototype.hasOwnProperty.call(patch, 'formal_statement') ? patch.formal_statement : (prev.formal_statement || ''),
        court_fee: Object.prototype.hasOwnProperty.call(patch, 'court_fee') ? patch.court_fee : (prev.court_fee || 0),
        preservation_fee: Object.prototype.hasOwnProperty.call(patch, 'preservation_fee') ? patch.preservation_fee : (prev.preservation_fee || 0),
      };
      CaseContextStore.save(c);
      const bits = [];
      if (patch.principal != null) bits.push(`本金 ¥${Number(patch.principal).toLocaleString('zh-CN')}`);
      if (patch.start_date) bits.push(`起息日 ${patch.start_date}`);
      if (patch.end_date) bits.push(`截止日 ${patch.end_date}`);
      if (patch.interest_total != null) bits.push(`利息 ¥${Number(patch.interest_total).toLocaleString('zh-CN')}`);
      if (patch.court_fee != null) bits.push(`诉讼费 ¥${Number(patch.court_fee).toLocaleString('zh-CN')}`);
      showToast(bits.length ? `已同步${bits.join('、')}` : '已同步本次填写的计算结果');
      return true;
    }

    function readFieldValue(id) {
      const el = document.getElementById(id);
      return el ? el.value : '';
    }

    function assignFieldValue(id, value) {
      const el = document.getElementById(id);
      if (el) el.value = value || '';
    }

    function filingOverwriteFields(c) {
      const plaintiff = c.plaintiff || {};
      const defendant = c.defendant || {};
      return [
        { label: '原告', before: readFieldValue('pkg-p-name'), after: plaintiff.name || '' },
        { label: '被告', before: readFieldValue('pkg-d-name'), after: defendant.name || '' },
        { label: '标的', before: readFieldValue('pkg-amount'), after: c.amount, kind: 'amount' },
        { label: '法院', before: readFieldValue('pkg-court'), after: c.court || '' },
        factCompareField('事实', 'pkg-notes', c.facts || ''),
        { label: '原告证件', before: readFieldValue('pkg-p-id'), after: plaintiff.id || '' },
        { label: '原告电话', before: readFieldValue('pkg-p-phone'), after: plaintiff.phone || '' },
        { label: '原告地址', before: readFieldValue('pkg-p-addr'), after: plaintiff.address || '' },
        { label: '被告证件', before: readFieldValue('pkg-d-id'), after: defendant.id || '' },
        { label: '被告电话', before: readFieldValue('pkg-d-phone'), after: defendant.phone || '' },
        { label: '被告地址', before: readFieldValue('pkg-d-addr'), after: defendant.address || '' },
      ];
    }

    function matterSwitchOverwriteFields(c) {
      const plaintiff = c.plaintiff || {};
      const defendant = c.defendant || {};
      return filingOverwriteFields(c).concat([
        { label: '证据目录举证人', before: readFieldValue('ev-catalog-plaintiff'), after: plaintiff.name || '' },
        { label: '证据目录案由', before: readFieldValue('ev-catalog-cause'), after: c.cause || '' },
        { label: '要件推演原告', before: readFieldValue('deep-custom-p'), after: plaintiff.name || '' },
        { label: '要件推演被告', before: readFieldValue('deep-custom-d'), after: defendant.name || '' },
        { label: '要件推演标的', before: readFieldValue('deep-custom-amount'), after: c.amount, kind: 'amount' },
        factCompareField('要件推演事实', 'deep-custom-facts', c.facts || ''),
        factCompareField('工作流事实', 'wf-input-facts', c.facts || ''),
      ]);
    }

    function factCompareField(label, id, nextFacts) {
      const current = String(readFieldValue(id) || '');
      const next = String(nextFacts || '').trim();
      const alreadyShowsNext = next && current.trim().startsWith(next);
      return { label, before: alreadyShowsNext ? next : current, after: next };
    }

    function confirmCaseOverwrite(lines, lead) {
      if (!lines.length) return true;
      const message = `${lead}\n${lines.join('\n')}`;
      if (typeof window.confirm !== 'function') return false;
      return window.confirm(message);
    }

    function fillLitigationFormFromContext(c) {
      const causeSelect = document.getElementById('pkg-cause');
      if (causeSelect) {
        let matched = false;
        for (let i = 0; i < causeSelect.options.length; i++) {
          const value = causeSelect.options[i].value;
          if (!value || !c.cause) continue;
          if (value === c.cause || c.cause.includes(value) || value.includes(c.cause)) {
            causeSelect.selectedIndex = i;
            matched = true;
            break;
          }
        }
        if (!matched) causeSelect.selectedIndex = 0;
        if (typeof updateCausePreset === 'function') updateCausePreset();
      }
      if (c.plaintiff) {
        if (document.getElementById('pkg-p-name')) document.getElementById('pkg-p-name').value = c.plaintiff.name || '';
        if (document.getElementById('pkg-p-id')) document.getElementById('pkg-p-id').value = c.plaintiff.id || '';
        if (document.getElementById('pkg-p-phone')) document.getElementById('pkg-p-phone').value = c.plaintiff.phone || '';
        if (document.getElementById('pkg-p-addr')) document.getElementById('pkg-p-addr').value = c.plaintiff.address || '';
      }
      if (c.defendant) {
        if (document.getElementById('pkg-d-name')) document.getElementById('pkg-d-name').value = c.defendant.name || '';
        if (document.getElementById('pkg-d-id')) document.getElementById('pkg-d-id').value = c.defendant.id || '';
        if (document.getElementById('pkg-d-phone')) document.getElementById('pkg-d-phone').value = c.defendant.phone || '';
        if (document.getElementById('pkg-d-addr')) document.getElementById('pkg-d-addr').value = c.defendant.address || '';
      }
      assignFieldValue('pkg-court', c.court || '');
      const amountEl = document.getElementById('pkg-amount');
      if (amountEl) {
        const amount = Number(c.amount);
        amountEl.value = Number.isFinite(amount) && amount > 0 ? String(amount) : '';
      }
      const notesEl = document.getElementById('pkg-notes');
      if (notesEl) {
        let text = c.facts || '';
        if (c.interest_calc && c.interest_calc.formal_statement) {
          text += (text ? "\n\n" : "") + "【利息精算及诉讼请求依据说明】\n" + c.interest_calc.formal_statement;
        }
        if (c.statutes && c.statutes.length > 0) {
          text += (text ? "\n\n" : "") + "【适用实体法律规范与司法解释依据】\n" + c.statutes.map((s, idx) => `  ${idx + 1}. 《${s.law_name}》${s.article_no}`).join("\n");
        }
        notesEl.value = text;
      }
    }

    function applyCaseContextToLitigation(autoSwitch = true) {
      const c = CaseContextStore.get();
      const conflicts = describeCaseOverwrites(filingOverwriteFields(c));
      if (!confirmCaseOverwrite(conflicts, '立案表单里已经填了不同内容，确认后才会改成当前案件：')) {
        showToast('已保留立案表单里的内容');
        return;
      }
      fillLitigationFormFromContext(c);
      if (autoSwitch) {
        switchNavTab('tab-litigation', '02 立案文书流水线', document.getElementById('nav-litigation'));
      }
      showToast("已成功将全局在办案件要素灌入 02 立案文书流水线！");
    }

    function applyCaseContextToDeepMatrix() {
      const c = CaseContextStore.get();
      const conflicts = describeCaseOverwrites([
        { label: '原告', before: readFieldValue('deep-custom-p'), after: (c.plaintiff && c.plaintiff.name) || '' },
        { label: '被告', before: readFieldValue('deep-custom-d'), after: (c.defendant && c.defendant.name) || '' },
        { label: '标的', before: readFieldValue('deep-custom-amount'), after: c.amount, kind: 'amount' },
        factCompareField('事实', 'deep-custom-facts', c.facts || ''),
      ]);
      if (!confirmCaseOverwrite(conflicts, '要件推演里已经填了不同内容，确认后才会改成当前案件：')) {
        showToast('已保留要件推演里的内容');
        return;
      }
      switchNavTab('tab-deep-matrix', '05 深度要件与质证推演', document.getElementById('nav-deep-matrix'));
      const presetSelect = document.getElementById('deep-case-preset');
      if (presetSelect) presetSelect.value = 'custom';
      const customPanel = document.getElementById('deep-custom-dossier-panel');
      if (customPanel) customPanel.style.display = 'block';
      loadCaseContextToDeepPanel({ overwrite: true });
      submitCustomDeepMatrixAnalyze();
    }

    function setDeepField(id, value, overwrite) {
      const el = document.getElementById(id);
      if (!el) return;
      const next = value == null ? '' : String(value);
      if (overwrite) {
        el.value = next;
        return;
      }
      if (next) el.value = next;
    }

    function loadCaseContextToDeepPanel(options) {
      const opts = options || {};
      const c = CaseContextStore.get();
      const overwrite = !!opts.overwrite;
      setDeepField('deep-custom-cause', c.cause || '', overwrite);
      setDeepField('deep-custom-title', c.title || '', overwrite);
      setDeepField('deep-custom-p', (c.plaintiff && c.plaintiff.name) || '', overwrite);
      setDeepField('deep-custom-d', (c.defendant && c.defendant.name) || '', overwrite);
      const amount = Number(c.amount);
      setDeepField('deep-custom-amount', Number.isFinite(amount) && amount > 0 ? String(amount) : '', overwrite);
      setDeepField('deep-custom-facts', c.facts || '', overwrite);
      setDeepField('deep-custom-evidence', c.evidence_notes || '', overwrite);
      const cntEl = document.getElementById('deep-custom-statutes-count');
      if (cntEl) cntEl.innerText = (c.statutes || []).length;
      if (!opts.silent) showToast("已从全局在办案件同步案情、当事人与证据清单至推演面板");
    }

    function fillEmptyDeepFieldsFromContext() {
      const c = CaseContextStore.get();
      const fill = (id, value) => {
        const el = document.getElementById(id);
        if (!el || String(el.value || '').trim() || value == null || value === '') return;
        el.value = String(value);
      };
      fill('deep-custom-cause', c.cause);
      fill('deep-custom-title', c.title);
      fill('deep-custom-p', c.plaintiff && c.plaintiff.name);
      fill('deep-custom-d', c.defendant && c.defendant.name);
      if (Number(c.amount) > 0) fill('deep-custom-amount', c.amount);
      fill('deep-custom-facts', c.facts);
    }

    async function submitCustomDeepMatrixAnalyze() {
      fillEmptyDeepFieldsFromContext();
      const perspective = currentDeepPerspective;
      const cause = document.getElementById('deep-custom-cause').value;
      const title = document.getElementById('deep-custom-title').value.trim();
      const plaintiff = document.getElementById('deep-custom-p').value.trim();
      const defendant = document.getElementById('deep-custom-d').value.trim();
      const amount = parseFloat(document.getElementById('deep-custom-amount').value) || 0;
      const facts = document.getElementById('deep-custom-facts').value.trim();
      const evidence = document.getElementById('deep-custom-evidence').value.trim();
      if (!plaintiff || !defendant || !facts) {
        showToast("请先填写原告、被告和本案事实，不要用示例当事人推演");
        return;
      }

      const caseCtx = CaseContextStore.get();
      const statuteBasis = (caseCtx.statutes || []).map(s => `${s.law_name} ${s.article_no}`);

      showToast("正在执行真实在办卷宗七维深度推演与法典穿透...");

      try {
        const resp = await api.request(`${API_BASE}/api/v1/deep-matrix/analyze-custom`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            case_preset: "custom",
            perspective: perspective,
            custom_case_title: title,
            custom_cause_of_action: cause,
            custom_claim_amount: amount,
            custom_plaintiff: plaintiff,
            custom_defendant: defendant,
            custom_raw_text: facts,
            custom_evidence_notes: evidence,
            custom_statutes: statuteBasis
          })
        });

        if (!resp.ok) {
          const err = await resp.json();
          showToast("推演失败: " + (err.detail || "请求异常"));
          return;
        }

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

        showToast(`真实卷宗七维推演已完成 · ${d.scorecard.status_label}`);
      } catch (e) {
        showToast("自定义推演请求失败: " + e);
      }
    }

    function toggleSelectStatuteFromList(articleId, lawName, articleNo, content = "") {
      const c = CaseContextStore.get();
      if (!c.statutes) c.statutes = [];
      const idx = c.statutes.findIndex(s => s.id === articleId);
      let isAdded = false;
      if (idx >= 0) {
        c.statutes.splice(idx, 1);
        isAdded = false;
        showToast(`已从在办案件依据中移除《${lawName}》${articleNo}`);
      } else {
        c.statutes.push({
          id: articleId,
          law_name: lawName,
          article_no: articleNo,
          content: content || ""
        });
        isAdded = true;
        showToast(`已将《${lawName}》${articleNo} 选入在办案件请求权依据！`);
      }
      CaseContextStore.save(c);

      // 同步更新列表中按钮状态
      const btnList = document.getElementById(`btn-statute-list-${articleId.replace(/[:.]/g, '_')}`);
      if (btnList) {
        if (isAdded) {
          btnList.classList.add('selected');
          btnList.innerText = '✓ 已选入本案';
        } else {
          btnList.classList.remove('selected');
          btnList.innerText = '📌 选入本案依据';
        }
      }

      // 同步更新右侧详情按钮状态
      const btnDetail = document.getElementById('btn-pin-active-statute');
      if (btnDetail && currentActiveArticleId === articleId) {
        if (isAdded) {
          btnDetail.classList.add('selected');
          btnDetail.innerText = '✓ 已选入本案依据';
        } else {
          btnDetail.classList.remove('selected');
          btnDetail.innerText = '📌 选入本案请求权依据';
        }
      }
    }

    function openSelectedStatutesDrawer() {
      openCaseContextModal('statutes');
    }

    function openCaseContextModal(targetSection = 'all') {
      const c = CaseContextStore.get();
      document.getElementById('modal-case-cause').value = c.cause || "";
      document.getElementById('modal-case-badge').innerText = c.cause || "待填写案由";
      document.getElementById('modal-case-title').value = c.title || "";
      document.getElementById('modal-case-court').value = c.court || "";
      document.getElementById('modal-case-amount').value = c.amount || 0;

      if (c.plaintiff) {
        document.getElementById('modal-case-p-name').value = c.plaintiff.name || "";
        document.getElementById('modal-case-p-id').value = c.plaintiff.id || "";
        document.getElementById('modal-case-p-phone').value = c.plaintiff.phone || "";
        document.getElementById('modal-case-p-addr').value = c.plaintiff.address || "";
      }
      if (c.defendant) {
        document.getElementById('modal-case-d-name').value = c.defendant.name || "";
        document.getElementById('modal-case-d-id').value = c.defendant.id || "";
        document.getElementById('modal-case-d-phone').value = c.defendant.phone || "";
        document.getElementById('modal-case-d-addr').value = c.defendant.address || "";
      }

      if (c.interest_calc) {
        document.getElementById('modal-calc-p').innerText = `¥${(c.interest_calc.principal || c.amount || 0).toLocaleString()}`;
        document.getElementById('modal-calc-interest').innerText = `¥${(c.interest_calc.interest_total || 0).toLocaleString()}`;
        document.getElementById('modal-calc-courtfee').innerText = `¥${(c.interest_calc.court_fee || 0).toLocaleString()}`;
        document.getElementById('modal-calc-preservfee').innerText = `¥${(c.interest_calc.preservation_fee || 0).toLocaleString()}`;
        document.getElementById('modal-calc-statement').innerText = c.interest_calc.formal_statement || "尚未同步利息明细";
      }

      document.getElementById('modal-case-facts').value = c.facts || "";
      document.getElementById('modal-case-evidence').value = c.evidence_notes || "";

      renderModalStatutesList(c.statutes || []);

      const modal = document.getElementById('modal-case-context');
      if (modal) modal.classList.add('active');
    }

    function closeCaseContextModal() {
      const modal = document.getElementById('modal-case-context');
      if (modal) modal.classList.remove('active');
    }

    function handleCaseModalBackdropClick(event) {
      if (event.target && event.target.id === 'modal-case-context') {
        closeCaseContextModal();
      }
    }

    function syncModalCaseCauseBadge() {
      const cause = document.getElementById('modal-case-cause').value;
      const b = document.getElementById('modal-case-badge');
      if (b) b.innerText = cause || "自拟案由";
    }

    function renderModalStatutesList(statutes) {
      const container = document.getElementById('modal-statutes-list');
      const countEl = document.getElementById('modal-statutes-count');
      if (countEl) countEl.innerText = (statutes || []).length;
      if (!container) return;

      if (!statutes || statutes.length === 0) {
        container.innerHTML = `
          <div style="font-size:12px; color:var(--text-muted); padding:10px; text-align:center; background:#FAF9F6; border:1px dashed #D8D4C8; border-radius:var(--radius-sm);">
            暂未选入法条。可前往 <strong>06 法条库中枢</strong> 检索并点击【📌 选入本案依据】。
          </div>
        `;
        return;
      }

      container.innerHTML = statutes.map((s, idx) => `
        <div style="background:#FFFFFF; border:1px solid #E2DFD7; border-left:3px solid var(--accent-amber); padding:8px 12px; border-radius:var(--radius-sm); display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; flex-direction:column; gap:2px; max-width:85%;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="citation-pill" style="font-weight:700;">${escapeHtml(s.article_no)}</span>
              <strong style="color:var(--primary-navy); font-size:12px;">${escapeHtml(s.law_name)}</strong>
            </div>
            <div style="font-size:11px; color:var(--text-secondary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
              ${escapeHtml(s.content || '')}
            </div>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" onclick="removeStatuteFromCase('${escapeHtml(s.id)}')" style="padding:2px 6px; font-size:10px; color:var(--status-warn);">
            移除
          </button>
        </div>
      `).join('');
    }

    function removeStatuteFromCase(articleId) {
      const c = CaseContextStore.get();
      if (c.statutes) {
        c.statutes = c.statutes.filter(s => s.id !== articleId);
        CaseContextStore.save(c);
        renderModalStatutesList(c.statutes);
        showToast("已从在办案件依据中移除该法条");
      }
    }

    function saveCaseContextFromModal() {
      const c = CaseContextStore.get();
      c.cause = document.getElementById('modal-case-cause').value.trim() || c.cause;
      c.title = document.getElementById('modal-case-title').value.trim() || c.title;
      c.court = document.getElementById('modal-case-court').value.trim() || c.court;
      c.amount = parseFloat(document.getElementById('modal-case-amount').value) || 0;

      c.plaintiff = {
        name: document.getElementById('modal-case-p-name').value.trim(),
        id: document.getElementById('modal-case-p-id').value.trim(),
        phone: document.getElementById('modal-case-p-phone').value.trim(),
        address: document.getElementById('modal-case-p-addr').value.trim()
      };

      c.defendant = {
        name: document.getElementById('modal-case-d-name').value.trim(),
        id: document.getElementById('modal-case-d-id').value.trim(),
        phone: document.getElementById('modal-case-d-phone').value.trim(),
        address: document.getElementById('modal-case-d-addr').value.trim()
      };

      c.facts = document.getElementById('modal-case-facts').value.trim();
      c.evidence_notes = document.getElementById('modal-case-evidence').value.trim();

      CaseContextStore.save(c);
      closeCaseContextModal();
      showToast("在办案件全局信息已保存并即时生效！");
    }

    function resetCaseContextToDefault() {
      CaseContextStore.resetDefault();
      openCaseContextModal();
      showToast("已清空在办案件");
    }

    function clearCaseContextToNew() {
      CaseContextStore.clearNew();
      openCaseContextModal();
      showToast("已清空，可录入全新案件！");
    }

    function syncCalcFromTab01ToModal() {
      const wrote = syncCurrentCalcToCaseContext();
      if (!wrote) return;
      const c = CaseContextStore.get();
      if (c.interest_calc) {
        document.getElementById('modal-calc-p').innerText = `¥${(c.interest_calc.principal || c.amount || 0).toLocaleString()}`;
        document.getElementById('modal-calc-interest').innerText = `¥${(c.interest_calc.interest_total || 0).toLocaleString()}`;
        document.getElementById('modal-calc-courtfee').innerText = `¥${(c.interest_calc.court_fee || 0).toLocaleString()}`;
        document.getElementById('modal-calc-preservfee').innerText = `¥${(c.interest_calc.preservation_fee || 0).toLocaleString()}`;
        document.getElementById('modal-calc-statement').innerText = c.interest_calc.formal_statement || "尚未同步利息明细";
      }
    }


    // =========================================================================
    // 10. 案件独立空间管理与核心图谱中枢 (Matter Vault & Core Graphs)
    // =========================================================================
    let currentDeepData = null;
    let activeMatterId = null;
      if (typeof window !== 'undefined') window.activeMatterId = null;
    let activeMatterData = null;
      if (typeof window !== 'undefined') window.activeMatterData = null;
    let allVaultMatters = [];

    async function clearDemoDataUI() {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/demo-data`, { method: 'DELETE' });
        if (!resp.ok) {
          showToast('清空演示数据失败');
          return;
        }
        showToast('已清空演示数据');
        activeMatterId = '';
      if (typeof window !== 'undefined') window.activeMatterId = '';
        await fetchAndRenderMattersList(false);
        updateDemoDataBadge();
      } catch (e) {
        showToast('清空演示数据异常: ' + e);
      }
    }

    function updateDemoDataBadge() {
      const hasDemo = (allVaultMatters || []).some(m => (m.title || '').indexOf('【演示】') >= 0);
      const badge = document.getElementById('gcase-demo-badge');
      const btn = document.getElementById('gcase-clear-demo-btn');
      if (badge) badge.style.display = hasDemo ? 'inline-block' : 'none';
      if (btn) btn.style.display = hasDemo ? 'inline-block' : 'none';
    }

    const LAST_MATTER_KEY = 'lawflow_last_matter_id';

    function readLastMatterId() {
      try {
        return localStorage.getItem(LAST_MATTER_KEY) || '';
      } catch (e) {
        return '';
      }
    }

    function rememberLastMatter(matterId) {
      try {
        if (matterId) localStorage.setItem(LAST_MATTER_KEY, matterId);
      } catch (e) {
        console.warn('记住上次案件失败:', e);
      }
    }

    function forgetLastMatter(matterId) {
      try {
        if (!matterId || readLastMatterId() === matterId) localStorage.removeItem(LAST_MATTER_KEY);
      } catch (e) {
        console.warn('清除上次案件失败:', e);
      }
    }

    function syncEmptyMatterEntry() {
      const createBtn = document.getElementById('btn-create-matter-empty');
      if (!createBtn) return;
      createBtn.style.display = (allVaultMatters && allVaultMatters.length) ? 'none' : 'inline-flex';
    }

    function renderUnselectedMatterHeader() {
      const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
      };
      setText('vault-matter-title', '未选择案件');
      setText('vault-matter-cause-badge', '');
      setText('vault-matter-status-badge', '');
      setText('vault-matter-caseno', '');
      setText('vault-matter-court', '');
      setText('vault-matter-amount', '');
      setText('vault-matter-role', '');
      syncEmptyMatterEntry();
    }

    function matterStillListed(matterId) {
      return !!(matterId && (allVaultMatters || []).some((item) => item.matter_id === matterId));
    }

    // 初始化案件空间
    async function initMatterVault() {
      try {
        const loaded = await fetchAndRenderMattersList(false);
        updateDemoDataBadge();
        if (!loaded) {
          renderUnselectedMatterHeader();
          return;
        }
        const lastId = readLastMatterId();
        if (matterStillListed(lastId)) {
          await switchActiveMatter(lastId, false);
          return;
        }
        renderUnselectedMatterHeader();
      } catch (e) {
        console.warn("初始化案件空间失败:", e);
        renderUnselectedMatterHeader();
      }
    }

    function openMatterVaultModal() {
      const modal = document.getElementById('modal-matter-vault');
      if (modal) {
        modal.classList.add('active');
        fetchAndRenderMattersList(true);
      }
    }

    function closeMatterVaultModal() {
      const modal = document.getElementById('modal-matter-vault');
      if (modal) modal.classList.remove('active');
      closeNewMatterDrawer();
    }

    function handleMatterVaultBackdropClick(e) {
      if (e.target.id === 'modal-matter-vault') {
        closeMatterVaultModal();
      }
    }

    function updateDemoDataClearButton() {
      const btn = document.getElementById('btn-clear-demo-data');
      if (!btn) return;
      const hasDemo = (allVaultMatters || []).some(m => (m.title || '').includes('【演示】'));
      btn.style.display = hasDemo ? 'inline-flex' : 'none';
    }

    async function clearVaultDemoData() {
      if (!confirm('确认清空全部【演示】种子数据？此操作不可撤销。')) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/demo-data`, { method: 'DELETE' });
        const res = await resp.json();
        if (!resp.ok) {
          showToast(res.detail || '清空失败');
          return;
        }
        showToast('演示数据已清空');
        await fetchAndRenderMattersList(true);
        if (!matterStillListed(activeMatterId)) {
          if (activeMatterId) forgetLastMatter(activeMatterId);
          activeMatterId = null;
          if (typeof window !== 'undefined') window.activeMatterId = null;
          activeMatterData = null;
          if (typeof window !== 'undefined') window.activeMatterData = null;
        }
        const reopenId = matterStillListed(activeMatterId) ? activeMatterId : (matterStillListed(readLastMatterId()) ? readLastMatterId() : '');
        if (reopenId) {
          await switchActiveMatter(reopenId, false);
        } else {
          renderUnselectedMatterHeader();
          renderGlobalCaseBar();
        }
      } catch (e) {
        showToast('清空演示数据失败: ' + e);
      }
    }

    async function fetchAndRenderMattersList(renderGrid = true) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters`);
        if (!resp.ok) return false;
        const res = await resp.json();
        allVaultMatters = res.matters || [];
        updateDemoDataClearButton();
        updateDemoDataBadge();
        if (renderGrid) {
          renderMattersGrid(allVaultMatters);
        }
        syncEmptyMatterEntry();
        return true;
      } catch (e) {
        console.warn("读取案件列表失败:", e);
        return false;
      }
    }

    function filterMattersList() {
      const q = (document.getElementById('vault-search-input')?.value || '').trim().toLowerCase();
      const statusFilter = document.getElementById('vault-status-filter')?.value || 'all';
      let filtered = allVaultMatters;
      if (statusFilter !== 'all') {
        filtered = filtered.filter(m => (m.status || 'active') === statusFilter);
      }
      if (q) {
        filtered = filtered.filter(m => 
          (m.title && m.title.toLowerCase().includes(q)) ||
          (m.cause_of_action && m.cause_of_action.toLowerCase().includes(q)) ||
          (m.case_number && m.case_number.toLowerCase().includes(q)) ||
          (m.plaintiff_name && m.plaintiff_name.toLowerCase().includes(q)) ||
          (m.defendant_name && m.defendant_name.toLowerCase().includes(q))
        );
      }
      renderMattersGrid(filtered);
    }

    function ensureMatterDeleteHint() {
      const grid = document.getElementById('vault-matters-grid');
      if (!grid || !grid.parentElement || document.getElementById('vault-matter-delete-hint')) return;
      const hint = document.createElement('p');
      hint.id = 'vault-matter-delete-hint';
      hint.style.cssText = 'margin:0 0 10px;font-size:12px;line-height:1.55;color:var(--text-secondary);';
      hint.textContent = '删除：默认只删原件，案件索引和证件号仍保留。点「连同证件号从案件行抹去」之前：证件号和电话会从案件行清掉，姓名仍会留在利冲底档里。律师确认后才会执行。';
      grid.parentElement.insertBefore(hint, grid);
    }

    function renderMattersGrid(matters) {
      const grid = document.getElementById('vault-matters-grid');
      if (!grid) return;
      ensureMatterDeleteHint();
      if (!matters.length) {
        grid.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:12px;">未匹配到相关案件空间</div>`;
        return;
      }
      grid.innerHTML = matters.map(m => { // safe-html: demo/active/status badges are static HTML; user fields escaped
        const isActive = m.matter_id === activeMatterId;
        const isArchived = m.status === 'archived';
        const demoBadge = (m.title || '').includes('【演示】')
          ? '<span class="badge" style="background:#FFEBEE; color:#D32F2F; font-size:11px; font-weight:700;">演示数据</span>'
          : '';
        const statusBadge = isArchived
          ? '<span class="badge" style="background:#F3F4F6; color:#6B7280; font-size:11px;">已归档 (Archived)</span>'
          : '<span class="badge" style="background:#E8F5E9; color:#2E7D32; font-size:11px;">在办 (Active)</span>';
        const activeBadge = isActive
          ? '<span class="badge" style="background: #E8F5E9; color: #2E7D32; font-weight:700;">● 当前激活空间</span>'
          : '';
        const summaryHtml = m.summary
          ? `<div style="font-size: 11.5px; color: var(--text-muted); margin-top: 4px; line-height: 1.4;">${escapeHtml(m.summary.substring(0, 100))}${escapeHtml(m.summary.length > 100 ? '...' : '')}</div>`
          : '';
        const statusToggleBtn = isArchived
          ? `<button type="button" class="btn btn-secondary btn-sm" onclick="updateMatterStatusUI('${escapeHtml(m.matter_id)}', 'active')" title="恢复为在办">恢复在办</button>`
          : `<button type="button" class="btn btn-secondary btn-sm" onclick="updateMatterStatusUI('${escapeHtml(m.matter_id)}', 'archived')" title="归档该案件">归档</button>`;
        const deleteBtn = `<button type="button" class="btn btn-secondary btn-sm" style="color:#DC2626; border-color:#FECACA;" onclick="deleteMatterUI('${escapeHtml(m.matter_id)}', '${escapeHtml(m.title)}')" title="默认只删原件，案件索引和证件号仍保留">删除</button>`;
        const scrubBtn = `<button type="button" class="btn btn-secondary btn-sm" style="color:#DC2626; border-color:#FECACA;" onclick="deleteMatterUI('${escapeHtml(m.matter_id)}', '${escapeHtml(m.title)}', true)" title="证件号和电话会从案件行清掉，姓名仍会留在利冲底档里">连同证件号从案件行抹去</button>`;
        const actionHtml = isActive
          ? `<button type="button" class="btn btn-secondary btn-sm" disabled style="opacity: 0.7;">当前空间</button> ${statusToggleBtn} ${deleteBtn} ${scrubBtn}`
          : `<button type="button" class="btn btn-sm" onclick="switchActiveMatter('${escapeHtml(m.matter_id)}', true)" style="background: var(--primary-navy);">切换至此空间</button> ${statusToggleBtn} ${deleteBtn} ${scrubBtn}`;
        return `
          <div class="surface-card" style="padding: 12px 14px; border-left: 4px solid ${escapeHtml(isActive ? 'var(--accent-amber)' : 'var(--primary-navy)')}; background: ${escapeHtml(isActive ? 'rgba(197, 133, 50, 0.04)' : '#FFFFFF')};">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 8px;">
              <div>
                <div style="display: flex; align-items: center; gap: 8px;">
                  <strong style="font-size: 13.5px; color: var(--primary-navy);">${escapeHtml(m.title)}</strong>
                  ${demoBadge}
                  <span class="badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 11px;">${escapeHtml(m.cause_of_action)}</span>
                  ${statusBadge}
                  ${activeBadge}
                </div>
                <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 5px; display: flex; gap: 12px; flex-wrap: wrap;">
                  <span>案号：<span style="font-family: var(--font-mono);">${escapeHtml(m.case_number || '待立案')}</span></span>
                  <span>法院：${escapeHtml(m.court_name || '未指定')}</span>
                  <span>标的：<strong style="color: var(--accent-amber); font-family: var(--font-mono);">¥${escapeHtml((m.principal_amount || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}</strong></span>
                  <span>当事人：${escapeHtml(m.plaintiff_name || '原告未填')} VS ${escapeHtml(m.defendant_name || '被告未填')}</span>
                  <span>程序：${escapeHtml((m.practice && m.practice.procedure_label) || '未选择')}</span>
                  <span>收费：${escapeHtml(([m.practice && m.practice.fee_type_label, m.practice && m.practice.fee_status_label].filter(Boolean).join(' · ') || '未约定') + ledgerFeeSuffix(m.practice))}</span>
                </div>
                ${summaryHtml}
                ${(m.practice && m.practice.personnel_check) ? `<div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 4px; line-height: 1.45;">本所人员：${escapeHtml(m.practice.personnel_check)}</div>` : ''}
              </div>
              <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                ${actionHtml}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    function applySharedCaseToSurfaces(c) {
      fillLitigationFormFromContext(c);
      assignFieldValue('ev-catalog-cause', c.cause || '');
      assignFieldValue('ev-catalog-plaintiff', (c.plaintiff && c.plaintiff.name) || '');
      assignFieldValue('wf-input-facts', c.facts || '');
      loadCaseContextToDeepPanel({ overwrite: true, silent: true });
    }

    async function switchActiveMatter(matterId, triggerToast = true) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}`);
        if (!resp.ok) {
          showToast('没有读到这个案件空间，当前案件未改');
          return;
        }
        const res = await resp.json();
        const matter = res.matter;
        const nextContext = buildCaseContextFromMatter(matter, CaseContextStore.get());
        const conflicts = describeCaseOverwrites(matterSwitchOverwriteFields(nextContext));
        if (!confirmCaseOverwrite(conflicts, '下面这些已填内容会改成所选案件空间，确认后才覆盖：')) {
          showToast('未切换案件，表单仍是原来的内容');
          return;
        }
        activeMatterId = matterId;
        activeMatterData = matter;
        if (typeof window !== 'undefined') {
          window.activeMatterId = matterId;
          window.activeMatterData = matter;
        }
        rememberLastMatter(matterId);
        if (typeof window.loadCopilotTasksUI === 'function') {
          window.loadCopilotTasksUI();
        }
        CaseContextStore.save(nextContext);
        applySharedCaseToSurfaces(nextContext);

        // 1. 更新顶部空间标签与上下文条
        const tagEl = document.getElementById('current-matter-tag-name');
        if (tagEl) {
          tagEl.innerText = activeMatterData.title.length > 10 ? activeMatterData.title.substring(0, 10) + '...' : activeMatterData.title;
        }

        // 2. 更新 07 模块头部卡片
        const vTitle = document.getElementById('vault-matter-title');
        if (vTitle) vTitle.innerText = activeMatterData.title;
        const vCause = document.getElementById('vault-matter-cause-badge');
        if (vCause) vCause.innerText = activeMatterData.cause_of_action;
        const vCaseno = document.getElementById('vault-matter-caseno');
        if (vCaseno) vCaseno.innerText = activeMatterData.case_number || '待立案';
        const vCourt = document.getElementById('vault-matter-court');
        if (vCourt) vCourt.innerText = activeMatterData.court_name || '未指定';
        const vAmount = document.getElementById('vault-matter-amount');
        if (vAmount) vAmount.innerText = `¥${(activeMatterData.principal_amount || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        const vRole = document.getElementById('vault-matter-role');
        if (vRole) {
          const practice = activeMatterData.practice || {};
          const feeLine = [practice.fee_type_label || '收费未约定', practice.fee_status_label].filter(Boolean).join(' · ') + ledgerFeeSuffix(practice);
          vRole.innerText = `${activeMatterData.plaintiff_name || '原告未填'} 诉 ${activeMatterData.defendant_name || '被告未填'} · ${practice.procedure_label || '程序未选'} · ${feeLine}`;
        }
        syncEmptyMatterEntry();

        // 3. 同步至 02 断点工作流输入框
        const wfInput = document.getElementById('wf-input-facts');
        if (wfInput) {
          wfInput.value = activeMatterData.summary || '';
        }

        // 4. 加载当前案件图谱、材料与阅卷表
        await fetchAndRenderMatterGraphs(matterId);
        await fetchAndRenderMatterDocs(matterId);
        await fetchAndRenderReviewTables(matterId);

        // 5. 重新渲染案件列表以更新"当前激活空间"徽章
        renderMattersGrid(allVaultMatters);

        renderMatterLedger(activeMatterData);
        if (triggerToast) {
          closeMatterVaultModal();
          showToast(`已切换至案件空间：${activeMatterData.title}`);
        }
      } catch (e) {
        showToast("切换空间异常: " + e);
      }
    }

    function openNewMatterDrawer() {
      const drawer = document.getElementById('vault-new-matter-drawer');
      if (drawer) drawer.style.display = 'block';
      loadCauseCatalog();
    }

    function toggleCustomCause() {
      const select = document.getElementById('new-matter-cause');
      const custom = document.getElementById('new-matter-cause-custom');
      if (!select || !custom) return;
      custom.style.display = select.value === '__custom__' ? 'block' : 'none';
    }

    async function loadCauseCatalog() {
      const select = document.getElementById('new-matter-cause');
      if (!select || select.dataset.loaded === '1') return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/cause-catalog`);
        if (!resp.ok) return;
        const data = await resp.json();
        const groups = {};
        (data.catalog || []).forEach((item) => {
          if (!groups[item.group]) groups[item.group] = [];
          groups[item.group].push(item);
        });
        const current = select.value;
        select.innerHTML = '<option value="">请选择民事案由</option>';
        Object.keys(groups).forEach((group) => {
          const optgroup = document.createElement('optgroup');
          optgroup.label = group;
          groups[group].forEach((item) => {
            const option = document.createElement('option');
            option.value = item.cause;
            option.textContent = item.cause;
            optgroup.appendChild(option);
          });
          select.appendChild(optgroup);
        });
        const custom = document.createElement('option');
        custom.value = '__custom__';
        custom.textContent = '目录里没有，手写案由';
        select.appendChild(custom);
        if (current) select.value = current;
        select.dataset.loaded = '1';
      } catch (e) {
        console.warn('案由目录加载失败', e);
      }
    }

    function closeNewMatterDrawer() {
      const drawer = document.getElementById('vault-new-matter-drawer');
      if (drawer) drawer.style.display = 'none';
    }

    function readNewMatterParties() {
      return {
        client_role: document.getElementById('new-matter-role')?.value || '原告',
        plaintiff_name: document.getElementById('new-matter-pname')?.value.trim() || '',
        defendant_name: document.getElementById('new-matter-dname')?.value.trim() || '',
        plaintiff_id: document.getElementById('new-matter-pid')?.value.trim() || '',
        defendant_id: document.getElementById('new-matter-did')?.value.trim() || '',
      };
    }

    function renderPersonnelScreen(personnel) {
      const box = document.getElementById('new-matter-personnel-result');
      if (!box || !personnel) return;
      const status = personnel.status || '';
      const hits = personnel.hits || [];
      let title = '本所人员比对';
      let tone = { bg: '#F8FAFC', border: '#CBD5E1', color: '#334155' };
      if (status === 'NOT_RECORDED') {
        title = '本所人员未录入，此项未检查';
      } else if (status === 'SIMILAR') {
        title = '姓名相近，需人工核对';
        tone = { bg: '#FFFBEB', border: '#FCD34D', color: '#92400E' };
      } else if (status === 'HIT') {
        const byId = hits.some((hit) => hit.match_kind === 'credential');
        const byName = hits.some((hit) => hit.match_kind === 'name');
        if (byId && !byName) title = '证件号相同，按同一人处理，未书面确认不能建案';
        else if (byName && !byId) title = '姓名为同一人，未书面确认不能建案';
        else title = '按同一人处理，未书面确认不能建案';
        tone = { bg: '#FEF2F2', border: '#FCA5A5', color: '#991B1B' };
      } else if (status === 'CHECKED') {
        title = '已核对本所名册，未发现同一人或姓名相近';
        tone = { bg: '#F0FDF4', border: '#86EFAC', color: '#166534' };
      } else if (status === 'NOT_COMPARED') {
        title = '对方名称和证件号都空着，还不能比对';
      }
      const detail = personnel.personnel_and_relatives_check || personnel.block_message || '';
      box.style.display = 'block';
      box.style.background = tone.bg;
      box.style.border = `1px solid ${tone.border}`;
      box.style.color = tone.color;
      box.textContent = detail ? `${title}\n${detail}` : title;
    }

    function paintPersonnelError(text) {
      const raw = String(text || '');
      if (!raw) return;
      if (raw.includes('姓名相近')) {
        renderPersonnelScreen({ status: 'SIMILAR', personnel_and_relatives_check: raw, hits: [] });
      } else if (raw.includes('本所人员未录入')) {
        renderPersonnelScreen({ status: 'NOT_RECORDED', personnel_and_relatives_check: raw, hits: [] });
      } else if (raw.includes('证件号') || raw.includes('同名') || raw.includes('书面确认')) {
        const hits = [];
        if (raw.includes('同名')) hits.push({ match_kind: 'name' });
        if (raw.includes('证件号')) hits.push({ match_kind: 'credential' });
        renderPersonnelScreen({ status: 'HIT', personnel_and_relatives_check: raw, hits });
      }
    }

    async function previewNewMatterPersonnel() {
      const parties = readNewMatterParties();
      if (!parties.plaintiff_name && !parties.defendant_name && !parties.plaintiff_id && !parties.defendant_id) {
        showToast('请先填写对方名称或证件号，再查看本所人员比对');
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/personnel-screen`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(parties),
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        renderPersonnelScreen(data.personnel || data);
      } catch (e) {
        const raw = e instanceof ApiError ? (e.detail || e.userMessage) : String(e);
        paintPersonnelError(raw);
        showToast(e instanceof ApiError ? e.userMessage : ('本所人员比对失败: ' + e), 'error');
      }
    }

    async function submitCreateNewMatter() {
      const title = document.getElementById('new-matter-title')?.value.trim();
      const causePick = document.getElementById('new-matter-cause')?.value.trim();
      const cause = causePick === '__custom__'
        ? (document.getElementById('new-matter-cause-custom')?.value.trim() || '')
        : causePick;
      if (!title || !cause) {
        showToast("请填写案件全称与法定案由！");
        return;
      }
      const caseno = document.getElementById('new-matter-caseno')?.value.trim();
      const court = document.getElementById('new-matter-court')?.value.trim();
      const amountRaw = document.getElementById('new-matter-amount')?.value;
      const amount = amountRaw === '' || amountRaw == null ? 0 : parseFloat(amountRaw);
      const pname = document.getElementById('new-matter-pname')?.value.trim();
      const dname = document.getElementById('new-matter-dname')?.value.trim();
      const summary = document.getElementById('new-matter-summary')?.value.trim();
      const feeType = document.getElementById('new-matter-fee-type')?.value || 'unset';
      const riskDisclosed = !!document.getElementById('new-matter-risk')?.checked;
      if (!pname || !dname) {
        showToast("请填写原告和被告的真实名称，不要留空，也不要写成委托人、相对人。");
        return;
      }
      if (feeType === 'risk' && !riskDisclosed) {
        showToast("风险代理必须先勾选已向委托人说明风险。");
        return;
      }

      const payload = {
        title,
        cause_of_action: cause,
        case_number: caseno,
        court_name: court,
        principal_amount: Number.isNaN(amount) ? 0 : amount,
        client_role: document.getElementById('new-matter-role')?.value || '原告',
        plaintiff_name: pname,
        defendant_name: dname,
        plaintiff_phone: document.getElementById('new-matter-pphone')?.value.trim() || '',
        defendant_phone: document.getElementById('new-matter-dphone')?.value.trim() || '',
        plaintiff_id: document.getElementById('new-matter-pid')?.value.trim() || '',
        defendant_id: document.getElementById('new-matter-did')?.value.trim() || '',
        procedure: document.getElementById('new-matter-procedure')?.value || '',
        fee_type: feeType,
        risk_disclosed: riskDisclosed,
        acknowledge_personnel_conflict: !!document.getElementById('new-matter-personnel-ack')?.checked,
        is_same_matter: document.getElementById('new-matter-same')?.value || '不确定',
        summary
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        const createdId = res.matter.matter_id;
        closeNewMatterDrawer();
        await fetchAndRenderMattersList(false);
        await switchActiveMatter(createdId, true);
        if (res.personnel) renderPersonnelScreen(res.personnel);
        showToast(res.message || "新案件独立空间创建成功，已自动切换");
      } catch (e) {
        const raw = e instanceof ApiError ? (e.detail || e.userMessage) : String(e);
        paintPersonnelError(raw);
        showToast(e instanceof ApiError ? e.userMessage : ("创建案件空间失败: " + e), "error");
      }
    }

    function optionalMatterNumber(id) {
      const raw = document.getElementById(id)?.value;
      if (raw === '' || raw == null) return null;
      const num = parseFloat(raw);
      return Number.isNaN(num) ? null : num;
    }

    // =========================================================================
    // 挂载材料管理
    // =========================================================================
    function openMountDocModal() {
      const modal = document.getElementById('modal-mount-doc');
      if (modal) modal.classList.add('active');
    }

    function closeMountDocModal() {
      const modal = document.getElementById('modal-mount-doc');
      if (modal) modal.classList.remove('active');
    }

    function handleMountDocBackdropClick(e) {
      if (e.target.id === 'modal-mount-doc') {
        closeMountDocModal();
      }
    }

    async function submitMountDocument() {
      const title = document.getElementById('mount-doc-title')?.value.trim();
      const docType = document.getElementById('mount-doc-type')?.value || 'contract';
      const content = document.getElementById('mount-doc-content')?.value.trim();
      if (!title || !content) {
        showToast("请填写材料名称与材料文本内容！");
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/documents`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            doc_title: title,
            doc_type: docType,
            content_text: content
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        closeMountDocModal();
        document.getElementById('mount-doc-title').value = '';
        document.getElementById('mount-doc-content').value = '';
        await fetchAndRenderMatterDocs(activeMatterId);
        showToast("材料已成功挂载入空间");
      } catch (e) {
        showToast("挂载材料失败: " + e);
      }
    }

    async function fetchAndRenderMatterDocs(matterId) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}/documents`);
        if (!resp.ok) return;
        const res = await resp.json();
        const docs = res.documents || [];
        const countEl = document.getElementById('vault-docs-count');
        if (countEl) countEl.innerText = docs.length;

        const listEl = document.getElementById('vault-docs-list');
        if (!listEl) return;
        if (!docs.length) {
          listEl.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:12px;">空间暂未挂载案卷材料，点击上方【挂载新材料】导入证据或合同</div>`;
          return;
        }

        const typeLabels = {
          'contract': { label: '合同协议', color: '#1E40AF', bg: '#DBEAFE' },
          'evidence': { label: '证据流水', color: '#15803D', bg: '#DCFCE7' },
          'pleading': { label: '诉讼文书', color: '#B45309', bg: '#FEF3C7' },
          'transcript': { label: '询问笔录', color: '#6B21A8', bg: '#F3E8FF' },
          'precedent': { label: '类案判例', color: '#374151', bg: '#F3F4F6' }
        };

        listEl.innerHTML = docs.map((d, i) => {
          const tInfo = typeLabels[d.doc_type] || { label: d.doc_type, color: '#374151', bg: '#F3F4F6' };
          return `
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 12px 14px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-weight: 700; font-size: 13px; color: var(--primary-navy);">${escapeHtml(i + 1)}. ${escapeHtml(d.doc_title)}</span>
                  <span class="badge" style="background: ${escapeHtml(tInfo.bg)}; color: ${escapeHtml(tInfo.color)}; font-size: 11px;">${escapeHtml(tInfo.label)}</span>
                </div>
                <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(d.file_size_bytes || 0)} 字符 · ${escapeHtml(d.created_at || '')}</span>
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; max-height: 60px; overflow: hidden; text-overflow: ellipsis; background: #FFF; padding: 6px 10px; border-radius: 4px; border: 1px solid #F1EFE9;">
                ${escapeHtml(d.content_text || '')}
              </div>
            </div>
          `;
        }).join('');
      } catch (e) {
        console.warn("读取材料失败:", e);
      }
    }

    // =========================================================================
    // 核心图谱展示与抽取 (Timeline, Entity, Cashflow)
    // =========================================================================
    function switchVaultGraphTab(tabKey) {
      document.querySelectorAll('#tab-graphs .tab-pill-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById(`btn-vault-tab-${tabKey}`);
      if (activeBtn) activeBtn.classList.add('active');

      document.querySelectorAll('.vault-graph-pane').forEach(p => p.style.display = 'none');
      const pane = document.getElementById(`pane-vault-${tabKey}`);
      if (pane) pane.style.display = 'block';

      if (tabKey === 'grid') {
        fetchAndRenderReviewTables(activeMatterId);
      } else if (tabKey === 'deadlines') {
        fetchAndRenderVaultDeadlines();
      } else if (tabKey === 'filing') {
        renderMatterLedger(activeMatterData);
      } else if (tabKey === 'docs') {
        fetchAndRenderMatterDocs(activeMatterId);
      }
    }

    async function fetchAndRenderMatterGraphs(matterId) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}/graphs`);
        if (!resp.ok) return;
        const res = await resp.json();
        const g = res.graphs;
        if (!g || (!g.timeline && !g.entity_graph && !g.cashflow)) {
          await runExtractMatterGraphs(false);
          return;
        }
        renderTimelineGraph(g.timeline || []);
        renderEntityGraph(g.entity_graph || { nodes: [], edges: [] });
        renderCashflowGraph(g.cashflow || []);
      } catch (e) {
        console.warn("读取图谱失败:", e);
      }
    }

    async function runExtractMatterGraphs(showNotification = true) {
      if (!activeMatterId) {
        if (showNotification) showToast("请先选择或新建一个在办案件空间");
        return;
      }
      const btn = document.getElementById('btn-extract-graphs');
      let origHtml = '';
      if (btn) {
        origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-dark"></span> 正在穿透材料抽取核心图谱...`;
        btn.disabled = true;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/graphs/extract`, {
          method: 'POST'
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        const g = res.graphs;
        renderTimelineGraph(g.timeline || []);
        renderEntityGraph(g.entity_graph || { nodes: [], edges: [] });
        renderCashflowGraph(g.cashflow || []);
        if (showNotification) {
          showToast("三大核心图谱抽取更新成功！");
        }
      } catch (e) {
        if (showNotification) showToast("抽取图谱失败: " + e);
      } finally {
        if (btn) {
          btn.innerHTML = origHtml;
          btn.disabled = false;
        }
      }
    }

    function renderTimelineGraph(events) {
      const listEl = document.getElementById('vault-timeline-list');
      if (!listEl) return;
      if (!events || !events.length) {
        listEl.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:12px;">暂无事实时间线，请点击右上角【重新智能抽取三大图谱】</div>`;
        return;
      }
      listEl.innerHTML = events.map(ev => { // safe-html: contains nested HTML fragment interpolations
        const isKey = ev.significance && (ev.significance.includes('关键') || ev.significance.includes('起算') || ev.significance.includes('违约') || ev.significance.includes('成立') || ev.significance.includes('催要'));
        return `
          <div class="vault-timeline-item">
            <div class="vault-timeline-dot ${escapeHtml(isKey ? 'key-event' : '')}"></div>
            <div class="vault-timeline-date">${escapeHtml(ev.date || '未知日期')}</div>
            <div class="vault-timeline-card">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <strong style="font-size: 13px; color: var(--primary-navy);">${escapeHtml(ev.event)}</strong>
                ${isKey ? '<span class="badge" style="background: #FEF3C7; color: #B45309; font-size: 10px;">关键法律事实</span>' : ''}
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 6px;">
                法律效力意义：${escapeHtml(ev.significance || '案件履约与事实链条环节')}
              </div>
              <div style="font-size: 10.5px; color: var(--text-muted); display: flex; align-items: center; gap: 4px;">
                <span>证据支撑：</span>
                <span class="badge" style="background: #F1F5F9; color: var(--primary-navy); font-size: 10.5px; padding: 1px 6px;">${escapeHtml(ev.source_doc || '案卷主材')}</span>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    // =========================================================================
    // P2: 复杂多方交叉担保拓扑与资金穿透大屏联动引擎状态
    // =========================================================================
    let currentGuaranteeAnalysis = null;
    let currentCashflowAudit = null;
    let currentCashflowMode = 'art561';
    let currentRawCashflows = [];
    let currentEntityGraph = null;

    // A. 交叉担保拓扑与保证期间审查
    async function runGuaranteeAnalysisUI(triggerToast = true) {
      if (!activeMatterId) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/guarantee-analysis`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentGuaranteeAnalysis = data;
        renderGuaranteeSummaryBar(data);
        renderTopologySVG(data);
        renderEntityCardsWithGuarantee(data);
        if (triggerToast) {
          showToast("保证期间生死线与物保受偿顺位审计完成！");
        }
      } catch (e) {
        console.warn("担保审计执行失败:", e);
        if (triggerToast) showToast("担保审计失败: " + e);
      }
    }

    function renderGuaranteeSummaryBar(data) {
      const bar = document.getElementById('vault-guarantee-summary-bar');
      if (!bar) return;

      const gAudits = data.guarantee_audits || [];
      const cAudits = data.collateral_audits || [];

      // 生死线状态判定
      let statusHtml = '<span class="badge" style="background:#DCFCE7; color:#15803D;">合法存续锁定</span>';
      let statusDesc = '全案在保证期间内主张权利或在法定除斥期内';
      const hasCritical = gAudits.some(g => g.status === 'CRITICAL_EXPIRED');
      const hasWarning = gAudits.some(g => g.status === 'WARNING_EXPIRING_SOON');

      if (hasCritical) {
        statusHtml = '<span class="badge" style="background:#FEE2E2; color:#B91C1C; font-weight:700;">🚨 保证责任灭失险情</span>';
        statusDesc = '存在超过6个月除斥期间未主张权利之保证人！';
      } else if (hasWarning) {
        statusHtml = '<span class="badge" style="background:#FEF3C7; color:#B45309; font-weight:700;">⚠️ 临近届满紧急预警</span>';
        statusDesc = '保证期间即将届满，须立即发函或提起诉讼！';
      }

      // 物保顺位
      const debtorCollateralCount = cAudits.filter(c => c.is_debtor_own_property).length;
      const thirdCollateralCount = cAudits.filter(c => !c.is_debtor_own_property).length;

      // safe-html: pre-escaped or nested HTML fragment
      bar.innerHTML = `
        <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
          <div style="font-size: 11px; color: var(--text-muted);">主债务到期与法定除斥日</div>
          <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-top: 3px; font-family: var(--font-mono);">
            ${escapeHtml(data.principal_due_date || '未查明')} ➔ ${escapeHtml(data.statutory_guarantee_expiry || '法定6个月')}
          </div>
          <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 3px;">依据《民法典》第692条第2款推算</div>
        </div>
        <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span style="font-size: 11px; color: var(--text-muted);">《民法典》692条保证生死线</span>
            ${statusHtml}
          </div>
          <div style="font-size: 12px; font-weight: 600; color: var(--primary-navy); margin-top: 3px;">
            ${escapeHtml(statusDesc)}
          </div>
          <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 3px;">涉及 ${escapeHtml(gAudits.length)} 位连带责任保证人</div>
        </div>
        <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
          <div style="font-size: 11px; color: var(--text-muted);">《民法典》392条人保物保受偿顺位</div>
          <div style="font-size: 12.5px; font-weight: 700; color: ${escapeHtml(debtorCollateralCount > 0 ? '#1E40AF' : 'var(--primary-navy)')}; margin-top: 3px;">
            ${escapeHtml(debtorCollateralCount > 0 ? `主债务人物保 (${debtorCollateralCount}处) 法定优先执行` : '均为第三人物保/保证人并列')}
          </div>
          <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 3px;">未经优先处置物保，不可绕行全额执行保证人</div>
        </div>
        <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
          <div style="font-size: 11px; color: var(--text-muted);">新《公司法》15条关联担保穿透</div>
          <div style="font-size: 12px; font-weight: 600; color: var(--accent-amber); margin-top: 3px;">
            企业对外关联担保决议合规核验
          </div>
          <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 3px;">九民纪要17-22条越权代表缔约过失责任防线</div>
        </div>
      `;
    }

    function renderTopologySVG(data) {
      const wrap = document.getElementById('vault-topology-canvas-wrap');
      if (!wrap) return;

      const nodes = (data.topology && data.topology.nodes) || [];
      const edges = (data.topology && data.topology.edges) || [];

      if (!nodes.length) {
        wrap.innerHTML = `<div style="text-align:center; padding:50px; color:var(--text-muted); font-size:12px;">暂无担保拓扑节点数据</div>`;
        return;
      }

      // 分列布局算法 (Zero-Jank, 纯SVG计算)
      // Col 0: 原告/债权人; Col 1: 被告/债务人/物保; Col 2: 保证人/第三方
      const col0 = [];
      const col1 = [];
      const col2 = [];

      nodes.forEach(n => {
        const r = (n.role || '').toLowerCase();
        if (r.includes('原告') || r.includes('债权') || r.includes('出借')) {
          col0.push(n);
        } else if (r.includes('被告') || r.includes('债务') || r.includes('借款')) {
          col1.push(n);
        } else {
          col2.push(n);
        }
      });

      if (!col0.length && nodes.length > 0) col0.push(nodes[0]);
      if (!col1.length && nodes.length > 1) col1.push(nodes[1]);
      const assignedIds = new Set([...col0, ...col1].map(x => x.id));
      nodes.forEach(n => {
        if (!assignedIds.has(n.id) && !col2.some(x => x.id === n.id)) {
          col2.push(n);
        }
      });

      const posMap = {};
      const cols = [
        { nodes: col0, x: 110 },
        { nodes: col1, x: 370 },
        { nodes: col2, x: 630 }
      ];

      cols.forEach(col => {
        const k = col.nodes.length;
        col.nodes.forEach((n, idx) => {
          const y = Math.round((240 / (k + 1)) * (idx + 1));
          posMap[n.id] = { x: col.x, y };
          posMap[n.name] = { x: col.x, y };
        });
      });

      // 绘制连线
      const edgesSvg = edges.map(e => {
        const p1 = posMap[e.source_id] || posMap[e.source_name] || { x: 110, y: 120 };
        const p2 = posMap[e.target_id] || posMap[e.target_name] || { x: 370, y: 120 };
        
        let strokeColor = '#94A3B8';
        let markerId = 'arrow-gray';
        let dash = 'none';

        if (e.is_collateral) {
          strokeColor = '#2563EB';
          markerId = 'arrow-blue';
          dash = '4,4';
        } else if (e.is_guarantee) {
          strokeColor = '#C58532';
          markerId = 'arrow-amber';
        } else if (e.relation_type && (e.relation_type.includes('借款') || e.relation_type.includes('债务'))) {
          strokeColor = '#B91C1C';
          markerId = 'arrow-red';
        }

        const mx = Math.round((p1.x + p2.x) / 2);
        const my = Math.round((p1.y + p2.y) / 2);

        return `
          <g class="topo-edge" style="cursor:pointer;" onclick="showToast('关系明细: ${escapeHtml(e.relation_type)} - ${escapeHtml(e.detail || '')}')">
            <line x1="${p1.x}" y1="${p1.y}" x2="${p2.x}" y2="${p2.y}" stroke="${strokeColor}" stroke-width="2" stroke-dasharray="${dash}" marker-end="url(#${markerId})" opacity="0.85" />
            <rect x="${mx - 45}" y="${my - 10}" width="90" height="20" rx="4" fill="#FFFFFF" stroke="${strokeColor}" stroke-width="1" opacity="0.95" />
            <text x="${mx}" y="${my + 4}" font-size="10" font-weight="600" fill="${strokeColor}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
              ${escapeHtml(e.relation_type)}
            </text>
          </g>
        `;
      }).join('');

      // 绘制节点
      const nodesSvg = nodes.map(n => {
        const pos = posMap[n.id] || { x: 200, y: 100 };
        const isExpired = n.guarantee_status === 'CRITICAL_EXPIRED';
        const isExpiring = n.guarantee_status === 'WARNING_EXPIRING_SOON';
        const isSafe = n.guarantee_status === 'SAFE';

        let boxFill = '#FFFFFF';
        let strokeColor = '#CBD5E1';
        let badgeColor = '#64748B';
        let badgeBg = '#F1F5F9';

        if (isExpired) {
          boxFill = '#FEF2F2';
          strokeColor = '#EF4444';
          badgeColor = '#B91C1C';
          badgeBg = '#FEE2E2';
        } else if (isExpiring) {
          boxFill = '#FFFBEB';
          strokeColor = '#F59E0B';
          badgeColor = '#B45309';
          badgeBg = '#FEF3C7';
        } else if (isSafe) {
          boxFill = '#F0FDF4';
          strokeColor = '#10B981';
          badgeColor = '#15803D';
          badgeBg = '#DCFCE7';
        } else if (n.collateral_priority && n.collateral_priority.includes('第一顺位')) {
          boxFill = '#EFF6FF';
          strokeColor = '#3B82F6';
          badgeColor = '#1D4ED8';
          badgeBg = '#DBEAFE';
        }

        const shortName = n.name.length > 11 ? n.name.substring(0, 10) + '..' : n.name;
        const roleLabel = n.role || (n.type === 'company' ? '企业法人' : '自然人');
        const statusLabel = n.guarantee_badge || n.collateral_priority || (n.is_debtor_own_collateral ? '债务人物保' : null);

        return `
          <g class="topo-node" style="cursor:pointer;" onclick="showToast('主体档案: ${escapeHtml(n.name)} (${escapeHtml(roleLabel)})')">
            <rect x="${pos.x - 85}" y="${pos.y - 24}" width="170" height="48" rx="6" fill="${boxFill}" stroke="${strokeColor}" stroke-width="1.8" filter="drop-shadow(0px 2px 4px rgba(0,0,0,0.04))" />
            <rect x="${pos.x - 80}" y="${pos.y - 20}" width="54" height="15" rx="3" fill="${badgeBg}" />
            <text x="${pos.x - 53}" y="${pos.y - 9}" font-size="9" font-weight="700" fill="${badgeColor}" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
              ${escapeHtml(roleLabel.substring(0, 5))}
            </text>
            <text x="${pos.x}" y="${pos.y + 13}" font-size="11.5" font-weight="700" fill="#14233C" text-anchor="middle" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
              ${escapeHtml(shortName)}
            </text>
            ${statusLabel ? `
              <text x="${pos.x + 80}" y="${pos.y - 9}" font-size="8.5" font-weight="700" fill="${badgeColor}" text-anchor="end" font-family="-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif">
                ${escapeHtml(statusLabel.substring(0, 6))}
              </text>
            ` : ''}
          </g>
        `;
      }).join('');

      // safe-html: topology svg graph
      wrap.innerHTML = `
        <svg width="100%" height="260" viewBox="0 0 760 260" style="display:block; overflow:visible;">
          <defs>
            <marker id="arrow-gray" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#94A3B8"/>
            </marker>
            <marker id="arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#2563EB"/>
            </marker>
            <marker id="arrow-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#C58532"/>
            </marker>
            <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 1 L 9 5 L 0 9 z" fill="#B91C1C"/>
            </marker>
          </defs>
          ${edgesSvg}
          ${nodesSvg}
        </svg>
      `;
    }

    function renderEntityCardsWithGuarantee(data) {
      const cont = document.getElementById('vault-entity-content');
      if (!cont) return;

      const gAudits = data.guarantee_audits || [];
      const cAudits = data.collateral_audits || [];
      const nodes = (data.topology && data.topology.nodes) || [];

      // A. 保证人期间与责任卡片
      const gHtml = gAudits.map(g => {
        const isCrit = g.status === 'CRITICAL_EXPIRED';
        const isWarn = g.status === 'WARNING_EXPIRING_SOON';
        const cardBorder = isCrit ? '#EF4444' : (isWarn ? '#F59E0B' : '#10B981');
        const cardBg = isCrit ? '#FEF2F2' : (isWarn ? '#FFFBEB' : '#FFFFFF');

        return `
          <div class="surface-card" style="padding: 12px 14px; border-left: 4px solid ${cardBorder}; background: ${cardBg}; margin-bottom: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight: 700; font-size: 13.5px; color: var(--primary-navy);">${escapeHtml(g.guarantor_name)}</span>
                <span class="badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 10.5px;">${escapeHtml(g.guarantor_type)}</span>
              </div>
              <span class="badge" style="background: ${isCrit ? '#FEE2E2' : (isWarn ? '#FEF3C7' : '#DCFCE7')}; color: ${isCrit ? '#B91C1C' : (isWarn ? '#B45309' : '#15803D')}; font-weight: 700; font-size: 11px;">
                ${escapeHtml(g.status_label)}
              </span>
            </div>
            <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px;">
              <div>⏰ 主债务届满日：<span style="font-family: var(--font-mono); font-weight:600;">${g.principal_due_date}</span> ➔ 法定保证除斥截止日：<span style="font-family: var(--font-mono); font-weight:700; color: #B91C1C;">${g.guarantee_expiry_date}</span> (民法典692条第2款)</div>
              <div>📮 权利主张记录：${g.has_demanded_in_time ? `<strong style="color:#15803D;">已于 ${g.demand_date} 主张权利（时效已锁定）</strong>` : '<strong style="color:#B91C1C;">卷宗未见有效发函或起诉记录</strong>'}</div>
            </div>
            <div style="font-size: 11.5px; line-height: 1.5; color: ${isCrit ? '#991B1B' : (isWarn ? '#92400E' : '#166534')}; background: rgba(255,255,255,0.7); padding: 8px 10px; border-radius: 4px; border: 1px solid rgba(0,0,0,0.05);">
              ${escapeHtml(g.warning_message)}
            </div>
            ${g.corporate_resolution_check ? `
              <div style="margin-top: 8px; font-size: 11px; background: #FAF9F6; border: 1px dashed #D1D5DB; border-radius: 4px; padding: 6px 10px; color: var(--text-secondary);">
                <div style="font-weight: 700; color: var(--primary-navy); margin-bottom: 2px;">
                  🏢 公司对外担保决议合规核验 (${escapeHtml(g.corporate_resolution_check.statute_basis)})：
                </div>
                <div>${escapeHtml(g.corporate_resolution_check.audit_note)}</div>
              </div>
            ` : ''}
          </div>
        `;
      }).join('');

      // B. 物保人保顺位审查卡片
      const cHtml = cAudits.map(c => `
        <div class="surface-card" style="padding: 12px 14px; border-left: 4px solid ${c.is_debtor_own_property ? '#1D4ED8' : '#C58532'}; background: #FFFFFF; margin-bottom: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-weight: 700; font-size: 13.5px; color: var(--primary-navy);">${escapeHtml(c.collateral_provider)}</span>
              <span class="badge" style="background: ${c.is_debtor_own_property ? '#DBEAFE' : '#FEF3C7'}; color: ${c.is_debtor_own_property ? '#1E40AF' : '#B45309'}; font-weight: 700; font-size: 11px;">
                ${escapeHtml(c.priority_rank)}
              </span>
            </div>
            <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">${escapeHtml(c.detail || '不动产抵押/物保')}</span>
          </div>
          <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; margin-bottom: 6px;">
            ${escapeHtml(c.statutory_rule)}
          </div>
          <div style="font-size: 11.5px; color: ${c.is_debtor_own_property ? '#1E40AF' : '#B45309'}; background: #FAF9F6; padding: 8px 10px; border-radius: 4px; border: 1px solid #E5E7EB;">
            ${escapeHtml(c.action_warning)}
          </div>
        </div>
      `).join('');

      // safe-html: pre-escaped or nested HTML fragment
      cont.innerHTML = `
        <div style="margin-bottom: 14px;">
          <div style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
            🛡️ 连带责任保证人审查明细与期间监控 (${escapeHtml(gAudits.length)} 位保证主体)
          </div>
          ${gHtml || '<div style="color:var(--text-muted); font-size:12px; padding:10px 0;">未识别到保证人主体</div>'}
        </div>

        ${cAudits.length > 0 ? `
          <div style="margin-bottom: 14px;">
            <div style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
              ⚖️ 《民法典》第392条物保受偿顺位与财产实现排挤分析 (${cAudits.length} 处物权担保)
            </div>
            ${cHtml}
          </div>
        ` : ''}

        <div style="margin-top: 14px;">
          <div style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px;">
            📌 涉案关键主体名录与法律地位 (${escapeHtml(nodes.length)} 个主体)
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 10px;">
            ${nodes.map(n => `
              <div class="surface-card" style="padding: 10px 12px; background: #FFFFFF; border: 1px solid var(--border-hairline);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="font-weight: 700; font-size: 12.5px; color: var(--primary-navy);">${escapeHtml(n.name)}</span>
                  <span class="badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 10px;">${escapeHtml(n.role || '主体')}</span>
                </div>
                <div style="font-size: 11px; color: var(--text-secondary);">
                  ${escapeHtml(n.type === 'company' ? '企业法人' : '自然人')} · ${escapeHtml(n.guarantee_badge || '普通法律关系')}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    function copyGuaranteeTacticalMemo() {
      const memo = currentGuaranteeAnalysis ? currentGuaranteeAnalysis.partner_tactical_memo : null;
      if (!memo) {
        showToast("暂无可复制的风控备忘录，请先点击【执行保证期间与物保顺位审计】");
        return;
      }
      navigator.clipboard.writeText(memo).then(() => {
        showToast("已成功复制合伙人交叉担保风控备忘录！");
      }).catch(err => {
        showToast("复制失败: " + err);
      });
    }

    function renderEntityGraph(graph) {
      currentEntityGraph = graph;
      // 触发高维担保期间与物保顺位审计
      runGuaranteeAnalysisUI(false);
    }

    // =========================================================================
    // B. 交易支付与资金穿透大屏 (含民法典561条法定冲抵对账引擎)
    // =========================================================================
    async function runCashflowAudit(triggerToast = false) {
      if (!activeMatterId) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/cashflow-audit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentCashflowAudit = data;
        renderCashflowWithMode();
        if (triggerToast) {
          showToast("民法典第561条分段冲抵对账与资金穿透已刷新！");
        }
      } catch (e) {
        console.warn("资金审计执行失败:", e);
        if (triggerToast) showToast("资金审计失败: " + e);
      }
    }

    function switchCashflowMode(mode) {
      currentCashflowMode = mode;
      const btn561 = document.getElementById('btn-cf-mode-art561');
      const btnNominal = document.getElementById('btn-cf-mode-nominal');
      if (mode === 'art561') {
        if (btn561) btn561.classList.add('active');
        if (btnNominal) btnNominal.classList.remove('active');
      } else {
        if (btnNominal) btnNominal.classList.add('active');
        if (btn561) btn561.classList.remove('active');
      }
      renderCashflowWithMode();
    }

    function renderCashflowWithMode() {
      const metricsEl = document.getElementById('vault-cashflow-metrics');
      const tableHead = document.getElementById('vault-cashflow-table-head');
      const tableBody = document.getElementById('vault-cashflow-table-body');
      const redflagsEl = document.getElementById('vault-cashflow-redflags');
      const statementEl = document.getElementById('vault-cashflow-statement-text');

      if (!tableBody) return;

      const audit = currentCashflowAudit;
      const flows = currentRawCashflows || [];

      // 1. 风险横幅
      if (redflagsEl) {
        if (audit && audit.red_flags && audit.red_flags.length > 0) {
          redflagsEl.style.display = 'block';
          redflagsEl.innerHTML = `
            <div style="background: #FEF2F2; border: 1px solid #FCA5A5; border-radius: var(--radius-sm); padding: 10px 14px;">
              <div style="font-weight: 700; color: #B91C1C; font-size: 12.5px; margin-bottom: 4px; display: flex; align-items: center; gap: 6px;">
                <span>流水里有 ${escapeHtml(audit.red_flags.length)} 项需要核对。核对的是代付、附言或同日回流，不能直接写成犯罪，也不能写成对方抗辩已经不成立。</span>
              </div>
              <ul style="margin: 0; padding-left: 18px; font-size: 11.5px; color: #991B1B; line-height: 1.6;">
                ${audit.red_flags.map(rf => `
                  <li><strong>【${escapeHtml(rf.risk_type)}】</strong> (${escapeHtml(rf.severity)}) ${escapeHtml(rf.risk_tip)}</li>
                `).join('')}
              </ul>
            </div>
          `;
        } else {
          redflagsEl.style.display = 'none';
        }
      }

      // 2. 指标卡片
      if (metricsEl) {
        if (currentCashflowMode === 'art561' && audit) {
          metricsEl.innerHTML = `
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">诉争借款本金基数</div>
              <div style="font-size: 17px; font-weight: 700; color: var(--primary-navy); font-family: var(--font-mono);">
                ¥${escapeHtml((audit.principal_claim_initial || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </div>
              <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 2px;">交付起息日: ${escapeHtml(audit.initial_lending_date || '-')}</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">被告名义清偿总额</div>
              <div style="font-size: 17px; font-weight: 700; color: var(--accent-amber); font-family: var(--font-mono);">
                ¥${escapeHtml((audit.total_nominal_repayments || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </div>
              <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 2px;">被告常抗辩全额抵扣本金</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">已冲抵的实现债权费用和利息</div>
              <div style="font-size: 17px; font-weight: 700; color: #1E40AF; font-family: var(--font-mono);">
                ¥${escapeHtml((((audit.total_fees_offset || 0) + (audit.total_interest_offset || 0))).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </div>
              <div style="font-size: 10.5px; color: #1E40AF; margin-top: 2px;">没有另有约定时，先费用，再利息，再本金（《民法典》第五百六十一条）</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">冲抵后剩余本金余额</div>
              <div style="font-size: 17px; font-weight: 700; color: #B91C1C; font-family: var(--font-mono);">
                ¥${escapeHtml((audit.current_principal_unpaid || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </div>
              <div style="font-size: 10.5px; color: #B91C1C; margin-top: 2px;">${escapeHtml((audit.total_principal_offset || 0) > 0 ? '已按顺序冲减本金。双方另有约定的，按约定。' : '这笔还款还没有冲到本金。双方另有约定的，按约定。')}</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">当前滚存未付利息</div>
              <div style="font-size: 17px; font-weight: 700; color: #9A3412; font-family: var(--font-mono);">
                ¥${escapeHtml((audit.unpaid_accrued_interest || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </div>
              <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 2px;">年化 ${escapeHtml((audit.annual_interest_rate*100).toFixed(2))}%</div>
            </div>
          `;
        } else {
          let totalAmount = 0;
          flows.forEach(f => { totalAmount += (f.amount || 0); });
          const unverified = flows.filter(f => !f.status || f.status === 'UNVERIFIED').length;
          metricsEl.innerHTML = `
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">涉案流水总笔数</div>
              <div style="font-size: 18px; font-weight: 700; color: var(--primary-navy); font-family: var(--font-mono);">${escapeHtml(flows.length)} 笔</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">已录入流水金额合计</div>
              <div style="font-size: 18px; font-weight: 700; color: var(--accent-amber); font-family: var(--font-mono);">¥${escapeHtml(totalAmount.toLocaleString('zh-CN', {minimumFractionDigits: 2}))}</div>
            </div>
            <div style="background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: 4px; padding: 10px 14px;">
              <div style="font-size: 11px; color: var(--text-muted);">凭证核对</div>
              <div style="font-size: 18px; font-weight: 700; color: #92400E; font-family: var(--font-mono);">${escapeHtml(flows.length - unverified)} 笔已核对</div>
              <div style="font-size: 10.5px; color: var(--text-muted); margin-top: 2px;">${escapeHtml(unverified)} 笔还没有核对原件，不能写成凭证已经吻合</div>
            </div>
          `;
        }
      }

      // 3. 表头与表格内容
      if (currentCashflowMode === 'art561') {
        if (tableHead) {
          tableHead.innerHTML = `
            <tr>
              <th style="width: 45px;">序号</th>
              <th style="width: 95px;">还款日期</th>
              <th style="width: 75px;">计息天数</th>
              <th style="width: 115px; text-align: right;">名义还款额</th>
              <th style="width: 120px; text-align: right; color: #1E40AF;">冲抵利息 (561条)</th>
              <th style="width: 110px; text-align: right; color: #B45309;">冲抵本金</th>
              <th style="width: 130px; text-align: right; color: #B91C1C;">冲抵后剩余本金</th>
              <th style="width: 110px;">核算对应凭证</th>
              <th>法定分段冲抵理据与法律意见</th>
            </tr>
          `;
        }

        const ledger = (audit && audit.reconciliation_ledger) || [];
        if (!ledger.length) {
          tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:30px; color:var(--text-muted);">暂无清偿还款记录，正在等待计算...</td></tr>`;
        } else {
          tableBody.innerHTML = ledger.map(item => `
            <tr>
              <td style="font-family: var(--font-mono); font-size: 11px;">#${escapeHtml(item.step_num)}</td>
              <td style="font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(item.repayment_date)}</td>
              <td style="font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(item.days_accrued)} 天</td>
              <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: var(--accent-amber);">
                ¥${escapeHtml((item.repay_amount || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </td>
              <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #1E40AF;">
                ¥${escapeHtml((item.offset_to_interest || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </td>
              <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #B45309;">
                ¥${escapeHtml((item.offset_to_principal || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </td>
              <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: #B91C1C;">
                ¥${escapeHtml((item.remaining_principal || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </td>
              <td>
                <button type="button" class="cell-action-btn" onclick="openSourceGroundingViewer('银行流水与转账凭证', 1, '${escapeHtml(item.voucher || '')}')" style="color: var(--accent-amber); font-weight: 600; text-decoration: underline;">
                  🔍 ${escapeHtml(item.voucher || '银行回单')}
                </button>
              </td>
              <td style="font-size: 11px; color: var(--text-secondary); line-height: 1.4;">
                ${escapeHtml(item.legal_comment)}
              </td>
            </tr>
          `).join('');
        }
      } else {
        if (tableHead) {
          tableHead.innerHTML = `
            <tr>
              <th style="width: 95px;">交易日期</th>
              <th style="width: 170px;">付款方</th>
              <th style="width: 170px;">收款方</th>
              <th style="width: 120px; text-align: right;">交易金额</th>
              <th style="width: 140px;">业务附言/用途</th>
              <th style="width: 120px;">凭证回单号</th>
              <th style="width: 80px; text-align: center;">验真状态</th>
            </tr>
          `;
        }

        if (!flows.length) {
          tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:30px; color:var(--text-muted);">暂无交易支付流水记录</td></tr>`;
        } else {
          tableBody.innerHTML = flows.map(f => `
            <tr>
              <td style="font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(f.date || '-')}</td>
              <td><strong style="color: var(--primary-navy);">${escapeHtml(f.payer || f.from_party || '-')}</strong></td>
              <td><strong style="color: var(--primary-navy);">${escapeHtml(f.payee || f.to_party || '-')}</strong></td>
              <td style="text-align: right; font-family: var(--font-mono); font-weight: 700; color: var(--accent-amber);">
                ¥${escapeHtml((f.amount || 0).toLocaleString('zh-CN', {minimumFractionDigits: 2}))}
              </td>
              <td>${escapeHtml(f.purpose || f.channel || f.note || '用途未填写')}</td>
              <td>
                <button type="button" class="cell-action-btn" onclick="openSourceGroundingViewer('银行流水与转账凭证', 1, '${escapeHtml(f.voucher || '')}')" style="color: var(--accent-amber); font-weight: 600; text-decoration: underline;">
                  🔍 ${escapeHtml(f.voucher || '回单号未填写')}
                </button>
              </td>
              <td style="text-align: center;">
                <span class="badge" style="background: #FEF3C7; color: #92400E; font-size: 10.5px;">未核对原件</span>
              </td>
            </tr>
          `).join('');
        }
      }

      // 4. 对账质证代理词
      if (statementEl && audit) {
        statementEl.innerText = audit.court_cross_exam_statement || '暂无对账意见';
      }
    }

    function copyCashflowStatement() {
      const stmt = currentCashflowAudit ? currentCashflowAudit.court_cross_exam_statement : null;
      if (!stmt) {
        showToast("暂无可复制的对账质证意见");
        return;
      }
      navigator.clipboard.writeText(stmt).then(() => {
        showToast("已复制本页对账说明。这不是法庭意见，也不能直接当代理词提交。");
      }).catch(err => {
        showToast("复制失败: " + err);
      });
    }

    function renderCashflowGraph(flows) {
      currentRawCashflows = flows || [];
      runCashflowAudit(false);
    }

    // =========================================================================
    // 人机协同断点工作流 (Human-in-the-Loop 5-Step State Machine)
    // =========================================================================
    let currentWorkflowId = null;
    let currentWorkflowData = null;

    function switchLitigationMode(mode) {
      const btnStd = document.getElementById('btn-lit-mode-std');
      const btnWf = document.getElementById('btn-lit-mode-wf');
      const paneStd = document.getElementById('lit-pane-standard');
      const paneWf = document.getElementById('lit-pane-workflow');

      if (mode === 'workflow') {
        btnWf.classList.add('active');
        btnStd.classList.remove('active');
        paneWf.style.display = 'block';
        paneStd.style.display = 'none';

        const wfInput = document.getElementById('wf-input-facts');
        if (wfInput && !wfInput.value.trim()) {
          if (activeMatterData && activeMatterData.summary) {
            wfInput.value = activeMatterData.summary;
          } else {
            const pkgNotes = document.getElementById('pkg-notes')?.value;
            if (pkgNotes) wfInput.value = pkgNotes;
          }
        }
      } else {
        btnStd.classList.add('active');
        btnWf.classList.remove('active');
        paneStd.style.display = 'block';
        paneWf.style.display = 'none';
      }
    }

    function updateWorkflowStepperUI(step, isBreakpoint = false, isCompleted = false) {
      for (let i = 1; i <= 5; i++) {
        const node = document.getElementById(`wf-step-${i}`);
        if (!node) continue;
        node.classList.remove('active', 'completed', 'breakpoint');

        if (i < step || isCompleted) {
          node.classList.add('completed');
        } else if (i === step) {
          node.classList.add('active');
          if (isBreakpoint) node.classList.add('breakpoint');
        }
      }

      for (let i = 1; i <= 4; i++) {
        const line = document.getElementById(`wf-line-${i}`);
        if (!line) continue;
        if (i < step || isCompleted) {
          line.classList.add('completed');
        } else {
          line.classList.remove('completed');
        }
      }
    }

    async function startLitigationWorkflowUI() {
      const facts = document.getElementById('wf-input-facts')?.value.trim();
      if (!facts) {
        showToast("请先填入或导入案情事实！");
        return;
      }
      if (!activeMatterId) {
        showToast("请先选择本案。工作流不会另用民间借贷作为案由。");
        return;
      }
      const btn = document.getElementById('btn-start-workflow');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-dark"></span> 正在提炼事实并匹配请求权基础规范...`;
      btn.disabled = true;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/workflows/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            matter_id: activeMatterId,
            initial_facts: facts,
            cause_of_action: activeMatterData?.cause_of_action || ''
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        currentWorkflowId = res.workflow.workflow_id;
        currentWorkflowData = res.workflow;
        renderWorkflowStepUI(res.workflow);
        showToast("已抵达断点 1：请主办律师核准诉讼请求项与实体法条文");
      } catch (e) {
        showToast("启动工作流失败: " + e);
      } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
      }
    }

    function renderWorkflowStepUI(wf) {
      currentWorkflowData = wf;
      const step = wf.current_step;
      const status = wf.status;

      // 隐藏所有状态容器
      const initState = document.getElementById('wf-initial-state');
      const step2Box = document.getElementById('wf-step2-box');
      const step4Box = document.getElementById('wf-step4-box');
      const step5Box = document.getElementById('wf-step5-box');

      if (initState) initState.style.display = 'none';
      if (step2Box) step2Box.style.display = 'none';
      if (step4Box) step4Box.style.display = 'none';
      if (step5Box) step5Box.style.display = 'none';

      if (status === 'WAITING_HUMAN_CONFIRMATION' && step === 2) {
        updateWorkflowStepperUI(2, true, false);
        if (step2Box) step2Box.style.display = 'block';

        const causeInput = document.getElementById('wf-step2-cause');
        if (causeInput) causeInput.value = wf.step1_facts?.cause_of_action || activeMatterData?.cause_of_action || '';

        // 渲染候选诉讼请求清单
        const claimsList = document.getElementById('wf-step2-claims-list');
        const claims = (wf.step2_claims?.candidate_claims || []).map(c => String(c || '').trim()).filter(Boolean);
        if (claimsList) {
          claimsList.innerHTML = claims.length ? claims.map((c, i) => `
            <label style="display: flex; align-items: flex-start; gap: 8px; background: #FFF; border: 1px solid #E2E8F0; padding: 8px 10px; border-radius: 4px; cursor: pointer; font-size: 12px;">
              <input type="checkbox" aria-label="诉讼请求项" name="wf-claim-item" value="${escapeHtml(c)}" style="margin-top: 3px; accent-color: #B45309;">
              <span style="color: var(--primary-navy); line-height: 1.4;">${escapeHtml(i + 1)}. ${escapeHtml(c)}</span>
            </label>
          `).join('') : `<div style="font-size:12px; color:var(--text-secondary); padding:8px 10px; background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:4px;">${EMPTY_CASE_FILL_HINT}</div>`;
        }

        // 渲染适用的民商事实体法规范依据
        const basisList = document.getElementById('wf-step2-basis-list');
        const statutes = (wf.step2_claims?.applicable_statutes || []).map(s => String(s || '').trim()).filter(Boolean);
        if (basisList) {
          basisList.innerHTML = statutes.length ? statutes.map(s => `
            <label style="display: flex; align-items: center; gap: 8px; background: #FFF; border: 1px solid #E2E8F0; padding: 6px 10px; border-radius: 4px; cursor: pointer; font-size: 11.5px;">
              <input type="checkbox" aria-label="法条依据项" name="wf-statute-item" value="${escapeHtml(s)}" style="accent-color: #B45309;">
              <span style="color: #1E40AF; font-weight: 600;">${escapeHtml(s)}</span>
            </label>
          `).join('') : `<div style="font-size:12px; color:var(--text-secondary); padding:8px 10px; background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:4px;">${EMPTY_CASE_FILL_HINT}</div>`;
        }

      } else if (status === 'WAITING_HUMAN_CONFIRMATION' && step === 4) {
        updateWorkflowStepperUI(4, true, false);
        if (step4Box) step4Box.style.display = 'block';

        const defCont = document.getElementById('wf-step4-defenses-list');
        const predictions = (wf.step3_statutes?.opponent_defense_predictions || []).filter(p => p && String(p.defense_point || '').trim());

        if (defCont) {
          defCont.innerHTML = predictions.length ? predictions.map((p, i) => {
            const strategy = String(p.counter_strategy || '').trim();
            const strategyHtml = strategy
              ? `<label style="display: flex; align-items: flex-start; gap: 6px; font-size: 11.5px; color: #15803D; font-weight: 600; cursor: pointer; background: #F0FDF4; padding: 6px 8px; border-radius: 4px;">
                <input type="checkbox" aria-label="反制策略项" name="wf-counter-item" value="${escapeHtml(strategy)}" style="margin-top: 2px; accent-color: #15803D;">
                <span>我方反制策略：${escapeHtml(strategy)}</span>
              </label>`
              : `<div style="font-size:12px; color:var(--text-secondary); padding:6px 8px;">${EMPTY_CASE_FILL_HINT}</div>`;
            return `
            <div style="background: #FFF; border: 1px solid #FDE68A; border-left: 3px solid #D97706; padding: 10px 12px; border-radius: 4px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                <span style="font-weight: 700; font-size: 12.5px; color: #92400E;">预测抗辩 ${escapeHtml(i + 1)}：${escapeHtml(p.defense_point)}</span>
                <span class="badge" style="background: #FEF3C7; color: #B45309; font-size: 10.5px;">待律师勾选</span>
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); margin-bottom: 6px; line-height: 1.5;">
                对方可能依据：${escapeHtml(p.basis || '请按本案核对')}
              </div>
              ${strategyHtml}
            </div>
          `;
          }).join('') : `<div style="font-size:12px; color:var(--text-secondary); padding:8px 10px; background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:4px;">${EMPTY_CASE_FILL_HINT}</div>`;
        }

      } else if (status === 'COMPLETED' || step === 5) {
        updateWorkflowStepperUI(5, false, true);
        if (step5Box) step5Box.style.display = 'block';

        // 将 Step 5 终稿同步到右侧公文纸
        const step5 = wf.step5_final_draft || {};
        const tipEl = document.getElementById('pkg-status-tip');
        if (tipEl) tipEl.innerText = "断点核准终稿已就绪";

        const factsBox = document.getElementById('pkg-facts-box');
        if (factsBox) {
          factsBox.innerText = step5.final_pleading_text || '起诉状正文已生成';
        }

        const citArea = document.getElementById('pkg-citations-area');
        if (citArea && step5.statute_citations) {
          citArea.innerHTML = `断点核准实体法依据：<span style="color: var(--primary-navy); font-weight:700;">${escapeHtml(step5.statute_citations.join('、'))}</span>`;
        }

        if (step5.citation_audit) {
          window._lastCitationAudit = step5.citation_audit;
          const badgeWrap = document.getElementById('pkg-citation-guard-badge-wrap');
          const badge = document.getElementById('pkg-citation-guard-badge');
          if (badgeWrap && badge) {
            badgeWrap.style.display = 'inline-block';
            const badgeInfo = step5.citation_audit.badge || {};
            badge.style.background = badgeInfo.is_safe ? '#2E7D32' : '#C58532';
            badge.innerText = badgeInfo.label || '引用待核验';
          }
        }
      } else {
        // 初始状态
        updateWorkflowStepperUI(1, false, false);
        if (initState) initState.style.display = 'block';
      }
    }

    async function advanceWorkflowStep2UI() {
      if (!currentWorkflowId) return;
      const checkedClaims = [];
      document.querySelectorAll('input[name="wf-claim-item"]:checked').forEach(c => checkedClaims.push(c.value));
      const checkedStatutes = [];
      document.querySelectorAll('input[name="wf-statute-item"]:checked').forEach(s => checkedStatutes.push(s.value));
      const cause = document.getElementById('wf-step2-cause')?.value.trim() || '';
      if (!cause) {
        showToast("请填写本案案由。不要用民间借贷作为默认案由。");
        return;
      }
      const notes = document.getElementById('wf-step2-notes')?.value.trim() || '';

      const btn = document.getElementById('btn-advance-step2');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-dark"></span> 正在穿透检索法规库并推演对方抗辩策略...`;
      btn.disabled = true;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/workflows/${currentWorkflowId}/advance`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            step: 2,
            human_decisions: {
              confirmed_claims: checkedClaims,
              confirmed_statutes: checkedStatutes,
              cause_of_action: cause,
              lawyer_notes: notes
            }
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        renderWorkflowStepUI(res.workflow);
        showToast("已抵达断点 2：对方抗辩焦点预测已就绪，请核准反击预案");
      } catch (e) {
        showToast("推进至 Step 3/4 失败: " + e);
      } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
      }
    }

    async function advanceWorkflowStep4UI() {
      if (!currentWorkflowId) return;
      const acceptedCounters = [];
      document.querySelectorAll('input[name="wf-counter-item"]:checked').forEach(c => acceptedCounters.push(c.value));
      const notes = document.getElementById('wf-step4-notes')?.value.trim() || '';

      const btn = document.getElementById('btn-advance-step4');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-dark"></span> 正在结合全部核准断点生成民事起诉状终稿...`;
      btn.disabled = true;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/workflows/${currentWorkflowId}/advance`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            step: 4,
            human_decisions: {
              accepted_counter_strategies: acceptedCounters,
              lawyer_defense_notes: notes
            }
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        renderWorkflowStepUI(res.workflow);
        showToast("人机协同断点起诉状终稿生成完毕，已通过引注认证！");
      } catch (e) {
        showToast("生成起诉状终稿失败: " + e);
      } finally {
        btn.innerHTML = origHtml;
        btn.disabled = false;
      }
    }

    async function rollbackWorkflowUI(targetStep) {
      if (!currentWorkflowId) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/workflows/${currentWorkflowId}/rollback`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_step: targetStep })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        renderWorkflowStepUI(res.workflow);
        showToast(`已成功回退至 Step ${targetStep}，请重新修改决策`);
      } catch (e) {
        showToast("回退失败: " + e);
      }
    }

    function resetWorkflowUI() {
      currentWorkflowId = null;
      currentWorkflowData = null;
      renderWorkflowStepUI({ current_step: 1, status: 'READY' });
      showToast("已重置断点工作流");
    }

    // =========================================================================
    // 12. 矩阵式批量阅卷表 (Harvey Review Tables) 与双栏穿透溯源
    // =========================================================================
    let activeReviewTableId = 'TABLE-2026-SEED-01';
    let activeReviewTableData = null;
    let currentGroundingData = null;

    async function fetchAndRenderReviewTables(matterId) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}/review-tables`);
        if (!resp.ok) return;
        const res = await resp.json();
        const tables = res.tables || [];
        if (tables.length > 0) {
          const tableToLoad = tables.find(t => t.table_id === activeReviewTableId) || tables[0];
          activeReviewTableId = tableToLoad.table_id;
          await loadReviewTableData(activeReviewTableId);
        } else {
          const grid = document.getElementById('vault-review-datagrid');
          if (grid) {
            grid.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:12px;">当前案件暂无阅卷表，请切换至示范空间或点击上方【＋ 动态新增要素提取列】创建</div>`;
          }
        }
      } catch (e) {
        console.warn("读取阅卷表失败:", e);
      }
    }

    async function loadReviewTableData(tableId) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${tableId}`);
        if (!resp.ok) return;
        const res = await resp.json();
        activeReviewTableData = res.table;
        renderReviewGrid(activeReviewTableData);
      } catch (e) {
        console.warn("加载阅卷表详情失败:", e);
      }
    }

    function renderReviewGrid(table) {
      const container = document.getElementById('vault-review-datagrid');
      if (!container || !table) return;

      const titleEl = document.getElementById('vault-grid-title');
      if (titleEl) titleEl.innerText = table.title || "批量审查矩阵表";
      const descEl = document.getElementById('vault-grid-desc');
      if (descEl) descEl.innerText = `${table.description || '矩阵式批量阅卷抽取'} · 包含 ${table.rows ? table.rows.length : 0} 份材料 · ${table.columns ? table.columns.length : 0} 个审查要素列`;

      const columns = table.columns || [];
      const rows = table.rows || [];

      let html = `
        <table class="review-grid-table">
          <thead>
            <tr>
              <th style="min-width: 220px; width: 240px; position: sticky; left: 0; z-index: 20; background: #F1F5F9;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>案卷与证据材料 (${rows.length})</span>
                  <span style="font-size: 10px; color: var(--text-muted);">行 = 文档</span>
                </div>
              </th>
      `;

      columns.forEach(col => {
        html += `
          <th style="min-width: 180px; max-width: 260px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 4px;">
              <div>
                <div style="color: var(--primary-navy); font-weight: 700; font-size: 12.5px;">${escapeHtml(col.name)}</div>
                <div style="font-size: 10.5px; color: var(--text-muted); font-weight: normal; margin-top: 2px;" title="${escapeHtml(col.instruction)}">
                  ${escapeHtml(col.instruction.length > 20 ? col.instruction.substring(0, 20) + '...' : col.instruction)}
                </div>
              </div>
              <div style="display: flex; gap: 2px;">
                <button type="button" class="cell-action-btn" title="整列批量重跑" onclick="runColumnRefreshUI('${col.id}')">
                  ⚡
                </button>
                <button type="button" class="cell-action-btn" style="color: #DC2626;" title="删除此列" onclick="deleteReviewColumnUI('${col.id}')">
                  ✕
                </button>
              </div>
            </div>
          </th>
        `;
      });

      html += `
            </tr>
          </thead>
          <tbody>
      `;

      if (!rows.length) {
        html += `<tr><td colspan="${columns.length + 1}" style="text-align:center; padding:30px; color:var(--text-muted);">暂无材料行</td></tr>`;
      } else {
        rows.forEach(r => {
          html += `
            <tr>
              <td style="position: sticky; left: 0; background: #FAF9F6; z-index: 10; border-right: 2px solid var(--border-hairline);">
                <div style="font-weight: 700; color: var(--primary-navy); font-size: 12.5px; margin-bottom: 4px;">
                  ${escapeHtml(r.doc_title)}
                </div>
                <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
                  <span class="badge" style="background: rgba(20, 35, 60, 0.08); color: var(--primary-navy); font-size: 10px;">${r.doc_type || '证据'}</span>
                  <button type="button" class="cell-action-btn" onclick="openSourceGroundingViewer('${escapeHtml(r.doc_title)}', 1, '')" style="color: var(--accent-amber); font-weight: 600;">
                    🔍 穿透溯源
                  </button>
                </div>
              </td>
          `;

          columns.forEach(col => {
            const cell = (r.cells || {})[col.id] || { value: "-", status: "ready" };
            const cellId = `cell-${r.id}-${col.id}`;
            const conf = cell.confidence ? Math.round(cell.confidence * 100) + '%' : '规则兜底';
            const hasQuote = Boolean(cell.grounding_quote);

            html += `
              <td id="${cellId}">
                <div class="review-cell-content">
                  <div style="font-size: 12px; color: var(--text-primary); line-height: 1.5; margin-bottom: 4px; word-break: break-all;">
                    ${cell.status === 'extracting' ? '<span class="spinner-dark"></span> 正在抽取...' : escapeHtml(cell.value || '-')}
                  </div>
                  <div class="review-cell-actions">
                    <span class="badge" style="background: #E8F5E9; color: #166534; font-size: 9.5px; padding: 1px 4px;">
                      ${conf}
                    </span>
                    ${hasQuote ? `
                      <button type="button" class="cell-action-btn" title="查看卷宗引述切片" onclick="openSourceGroundingViewer('${escapeHtml(r.doc_title)}', 1, '${escapeHtml(cell.grounding_quote)}')">
                        § 原文溯源
                      </button>
                    ` : ''}
                    <button type="button" class="cell-action-btn" title="单格异步重刷" onclick="runCellRefreshUI('${r.id}', '${col.id}')">
                      ↻ 重刷
                    </button>
                  </div>
                </div>
              </td>
            `;
          });

          html += `</tr>`;
        });
      }

      html += `
          </tbody>
        </table>
      `;

      container.innerHTML = html;
    }

    async function runCellRefreshUI(rowId, colId) {
      const cellEl = document.getElementById(`cell-${rowId}-${colId}`);
      if (cellEl) {
        cellEl.classList.add('cell-refreshing');
        cellEl.innerHTML = `<div style="padding:10px; color:var(--accent-amber); font-size:11px;"><span class="spinner-dark"></span> 正在局部重算...</div>`;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/cells/${rowId}/${colId}/refresh`, {
          method: 'POST'
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        const cell = res.cell;
        if (activeReviewTableData) {
          const row = (activeReviewTableData.rows || []).find(r => r.id === rowId);
          if (row) {
            if (!row.cells) row.cells = {};
            row.cells[colId] = cell;
          }
        }
        showToast("单元格局部重算完成");
        if (cellEl) {
          cellEl.classList.remove('cell-refreshing');
          const conf = cell.confidence ? Math.round(cell.confidence * 100) + '%' : '规则兜底';
          const hasQuote = Boolean(cell.grounding_quote);
          const rObj = (activeReviewTableData.rows || []).find(r => r.id === rowId) || { doc_title: '案卷材料' };
          cellEl.innerHTML = `
            <div class="review-cell-content">
              <div style="font-size: 12px; color: var(--text-primary); line-height: 1.5; margin-bottom: 4px; word-break: break-all;">
                ${escapeHtml(cell.value || '-')}
              </div>
              <div class="review-cell-actions">
                <span class="badge" style="background: #E8F5E9; color: #166534; font-size: 9.5px; padding: 1px 4px;">
                  ${escapeHtml(conf)}
                </span>
                ${hasQuote ? `
                  <button type="button" class="cell-action-btn" title="查看卷宗引述切片" onclick="openSourceGroundingViewer('${escapeHtml(rObj.doc_title)}', 1, '${escapeHtml(cell.grounding_quote)}')">
                    § 原文溯源
                  </button>
                ` : ''}
                <button type="button" class="cell-action-btn" title="单格异步重刷" onclick="runCellRefreshUI('${escapeHtml(rowId)}', '${escapeHtml(colId)}')">
                  ↻ 重刷
                </button>
              </div>
            </div>
          `;
        }
      } catch (e) {
        if (cellEl) cellEl.classList.remove('cell-refreshing');
        showToast("单格重刷失败: " + e);
      }
    }

    async function runColumnRefreshUI(colId) {
      showToast("正在重跑全列要素提取指令...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/columns/${colId}/refresh`, {
          method: 'POST'
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        activeReviewTableData = res.table;
        renderReviewGrid(activeReviewTableData);
        showToast("全列要素刷新成功！");
      } catch (e) {
        showToast("列级刷新失败: " + e);
      }
    }

    async function runAllReviewTableUI() {
      const btn = document.getElementById('btn-run-all-grid');
      let origHtml = '';
      if (btn) {
        origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-dark"></span> 正在全表并发提取...`;
        btn.disabled = true;
      }
      showToast("开始全表并发批量提取...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/run-all`, {
          method: 'POST'
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        activeReviewTableData = res.table;
        renderReviewGrid(activeReviewTableData);
        showToast("全表批量并发抽取完毕！");
      } catch (e) {
        showToast("全表抽取失败: " + e);
      } finally {
        if (btn) {
          btn.innerHTML = origHtml;
          btn.disabled = false;
        }
      }
    }

    async function exportReviewTableCsvUI() {
      showToast("正在导出阅卷表 CSV...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/export/csv`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const blob = await resp.blob();
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `review_table_${activeReviewTableId}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        showToast("CSV 已触发下载");
      } catch (e) {
        showToast("CSV 导出失败: " + e);
      }
    }

    function openAddReviewColumnModal() {
      const modal = document.getElementById('modal-add-review-column');
      if (modal) modal.classList.add('active');
    }

    function closeAddReviewColumnModal() {
      const modal = document.getElementById('modal-add-review-column');
      if (modal) modal.classList.remove('active');
    }

    function handleAddColumnBackdropClick(e) {
      if (e.target.id === 'modal-add-review-column') {
        closeAddReviewColumnModal();
      }
    }

    async function submitAddReviewColumn() {
      const name = document.getElementById('new-col-name')?.value.trim();
      const colType = document.getElementById('new-col-type')?.value || 'text';
      const instruction = document.getElementById('new-col-instruction')?.value.trim();

      if (!name || !instruction) {
        showToast("请填写要素列名称与大模型提取指令！");
        return;
      }

      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/columns`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name,
            type: colType,
            instruction
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        activeReviewTableData = res.table;
        closeAddReviewColumnModal();
        document.getElementById('new-col-name').value = '';
        document.getElementById('new-col-instruction').value = '';
        renderReviewGrid(activeReviewTableData);
        showToast(`成功追加要素列【${name}】并完成各文档提取！`);
      } catch (e) {
        showToast("追加要素列失败: " + e);
      }
    }

    async function deleteReviewColumnUI(colId) {
      if (!confirm("确定要删除此提取要素列吗？")) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/columns/${colId}`, {
          method: 'DELETE'
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        activeReviewTableData = res.table;
        renderReviewGrid(activeReviewTableData);
        showToast("要素列删除成功");
      } catch (e) {
        showToast("删除要素列失败: " + e);
      }
    }

    // =========================================================================
    // 13. 双栏穿透式原文定位抽屉与案卷原件视觉切片 (Split-Screen Source Grounding & Visual Crop)
    // =========================================================================
    function switchGroundingTab(mode) {
      const btnVis = document.getElementById('btn-grounding-tab-visual');
      const btnTxt = document.getElementById('btn-grounding-tab-text');
      const viewVis = document.getElementById('grounding-view-visual');
      const viewTxt = document.getElementById('grounding-view-text');
      if (mode === 'visual') {
        if (btnVis) btnVis.classList.add('active');
        if (btnTxt) btnTxt.classList.remove('active');
        if (viewVis) viewVis.style.display = 'flex';
        if (viewTxt) viewTxt.style.display = 'none';
      } else {
        if (btnTxt) btnTxt.classList.add('active');
        if (btnVis) btnVis.classList.remove('active');
        if (viewTxt) viewTxt.style.display = 'flex';
        if (viewVis) viewVis.style.display = 'none';
      }
    }

    async function openSourceGroundingViewer(docTitle, pageNo = 1, querySnippet = '') {
      const drawer = document.getElementById('drawer-source-grounding');
      if (!drawer) return;
      drawer.classList.add('active');

      const titleEl = document.getElementById('grounding-doc-title');
      const pageEl = document.getElementById('grounding-doc-page');
      const coordsEl = document.getElementById('grounding-coords-badge');
      const contentEl = document.getElementById('grounding-doc-content');
      const visualImg = document.getElementById('grounding-visual-img');
      const visualLoading = document.getElementById('grounding-visual-loading');

      if (titleEl) titleEl.innerText = docTitle || "案卷材料";
      if (pageEl) pageEl.innerText = `第 ${pageNo} 页`;
      if (coordsEl) coordsEl.innerText = querySnippet ? `匹配关键词切片: [${querySnippet.substring(0, 15)}...]` : "全文预览";
      if (contentEl) contentEl.innerHTML = `<span class="spinner-dark"></span> 正在穿透检索定位原文段落与坐标...`;

      if (visualImg) visualImg.style.display = 'none';
      if (visualLoading) {
        visualLoading.style.display = 'block';
        visualLoading.innerHTML = `<span class="spinner-dark"></span> 正在渲染案卷原件高清视觉切片与坐标定位...`;
      }
      switchGroundingTab('visual');

      try {
        const url = `${API_BASE}/api/v1/vault/matters/${activeMatterId}/grounding/excerpt?doc_title=${encodeURIComponent(docTitle || '')}&page_no=${pageNo}&query_text=${encodeURIComponent(querySnippet || '')}`;
        const resp = await api.request(url);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        currentGroundingData = data;

        const fullText = data.full_content || "暂无文档原件正文";
        const snippet = data.highlight_snippet;

        // 渲染视觉切片图像
        if (data.visual_crop_base64 && visualImg) {
          visualImg.src = data.visual_crop_base64;
          visualImg.style.display = 'inline-block';
          if (visualLoading) visualLoading.style.display = 'none';
          const tagEl = document.getElementById('grounding-visual-source-tag');
          if (tagEl) {
            tagEl.innerText = data.is_synthesized ? "标准司法公文存证切片 · 180 DPI" : "案卷原件高清扫描切片 · 180 DPI";
          }
        } else if (visualImg) {
          visualImg.style.display = 'none';
          if (visualLoading) {
            visualLoading.innerHTML = `<div style="color:var(--text-muted); font-size:12px;">暂无原件图像切片，请切换至【结构化文本对齐】查看。</div>`;
            visualLoading.style.display = 'block';
          }
        }

        // 渲染文本段落与高亮
        if (snippet && fullText.includes(snippet)) {
          const parts = fullText.split(snippet);
          contentEl.innerHTML = parts.map(p => escapeHtml(p)).join(`<mark class="grounding-mark">${escapeHtml(snippet)}</mark>`);
          setTimeout(() => {
            const markEl = contentEl.querySelector('.grounding-mark');
            if (markEl) markEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }, 100);
        } else {
          contentEl.innerHTML = escapeHtml(fullText);
        }

        if (coordsEl) {
          if (data.bounding_boxes && data.bounding_boxes.length > 0) {
            const b = data.bounding_boxes[0];
            coordsEl.innerText = `原件边界框: [X:${b.x0}, Y:${b.y0}, W:${b.width}, H:${b.height}] · P${pageNo}`;
          } else if (data.char_start >= 0) {
            coordsEl.innerText = `定位坐标: [字符偏移 ${data.char_start} - ${data.char_end}] · P${pageNo}`;
          }
        }
      } catch (e) {
        if (contentEl) contentEl.innerHTML = `<div style="color:#DC2626; padding:15px;">原文穿透定位失败: ${escapeHtml(e)}</div>`;
        if (visualLoading) visualLoading.innerHTML = `<div style="color:#DC2626; padding:15px;">原件切片加载失败: ${escapeHtml(e)}</div>`;
      }
    }

    function closeSourceGroundingViewer() {
      const drawer = document.getElementById('drawer-source-grounding');
      if (drawer) drawer.classList.remove('active');
    }

    function copyGroundingSnippet() {
      if (currentGroundingData && currentGroundingData.highlight_snippet) {
        navigator.clipboard.writeText(currentGroundingData.highlight_snippet).then(() => {
          showToast("已复制证据原文引述片段");
        });
      } else if (currentGroundingData && currentGroundingData.full_content) {
        navigator.clipboard.writeText(currentGroundingData.full_content).then(() => {
          showToast("已复制当前文档正文");
        });
      } else {
        showToast("暂无可复制原文");
      }
    }

    function copyGroundingAnchor() {
      const doc = currentGroundingData ? (currentGroundingData.doc_title || "证据材料") : "卷宗";
      const page = currentGroundingData ? (currentGroundingData.page_no || 1) : 1;
      const anchor = `[卷宗: ${doc} P${page}]`;
      navigator.clipboard.writeText(anchor).then(() => {
        showToast(`已复制溯源角标：${anchor}`);
      });
    }

    // =========================================================================
    // 8. 08 智律 AI 语音中枢与全模块联动引擎 (Phase 8 AI Voice Copilot Engine)

    // =========================================================================
    async function updateMatterStatusUI(matterId, newStatus, closeout) {
      try {
        const body = { status: newStatus };
        if (closeout) body.closeout = closeout;
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}/status`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const res = await resp.json();
        showToast(res.message || `案件已切换为 ${newStatus}`);
        await fetchAndRenderMattersList(true);
        if (activeMatterId === matterId) {
          await switchActiveMatter(matterId, false);
        }
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function showMatterDeleteNotice(message) {
      const text = String(message || '').trim();
      if (!text) return;
      const grid = document.getElementById('vault-matters-grid');
      let box = document.getElementById('vault-matter-delete-notice');
      if (!box) {
        box = document.createElement('div');
        box.id = 'vault-matter-delete-notice';
        box.setAttribute('role', 'status');
        box.style.cssText = 'margin:0 0 10px;padding:10px 12px;background:#FFFBEB;color:#92400E;border:1px solid #FDE68A;border-radius:6px;font-size:12.5px;line-height:1.55;';
        const body = document.createElement('div');
        body.dataset.role = 'delete-notice-text';
        body.style.whiteSpace = 'pre-wrap';
        const dismiss = document.createElement('button');
        dismiss.type = 'button';
        dismiss.textContent = '关闭';
        dismiss.style.cssText = 'margin-top:8px;background:#fff;border:1px solid #FDE68A;color:#92400E;border-radius:4px;padding:2px 8px;cursor:pointer;font-size:12px;';
        dismiss.addEventListener('click', () => box.remove());
        box.appendChild(body);
        box.appendChild(dismiss);
        if (grid && grid.parentElement) {
          grid.parentElement.insertBefore(box, grid);
        } else {
          document.body.appendChild(box);
        }
      }
      const body = box.querySelector('[data-role="delete-notice-text"]');
      if (body) body.textContent = text;
    }

    async function deleteMatterUI(matterId, matterTitle, scrubIdentifiers) {
      const title = matterTitle || '';
      const scrub = scrubIdentifiers === true;
      const prompt = scrub
        ? `确认连同证件号从案件【${title}】的案件行抹去？证件号和电话会从案件行清掉，姓名仍会留在利冲底档里。原件也会删除。`
        : `确认删除案件【${title}】？默认只删原件，案件索引和证件号仍保留。`;
      if (!confirm(prompt)) return;
      const query = scrub ? 'confirm=true&scrub_identifiers=true' : 'confirm=true';
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}?${query}`, {
          method: 'DELETE'
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const res = await resp.json();
        const returned = [res.message, res.conflict_registry_note]
          .map((item) => String(item || '').trim())
          .filter(Boolean)
          .filter((item, index, list) => !list.slice(0, index).some((earlier) => earlier.includes(item)));
        showMatterDeleteNotice(returned.join('') || (scrub
          ? '原件已删，已连同证件号从案件行抹去。'
          : '原件已删，案件索引和证件号仍保留。'));
        if (activeMatterId === matterId) {
          forgetLastMatter(matterId);
          activeMatterId = null;
          if (typeof window !== 'undefined') window.activeMatterId = null;
          activeMatterData = null;
          if (typeof window !== 'undefined') window.activeMatterData = null;
        }
        await fetchAndRenderMattersList(true);
        if (!activeMatterId) {
          const lastId = readLastMatterId();
          if (matterStillListed(lastId)) {
            await switchActiveMatter(lastId, false);
          } else {
            renderUnselectedMatterHeader();
          }
        }
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    async function exportReviewTableXlsxUI() {
      if (!activeReviewTableId) {
        showToast("当前无激活阅卷表，无法导出！");
        return;
      }
      showToast("正在导出阅卷表 Excel (.xlsx)...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/review-tables/${activeReviewTableId}/export/xlsx`);
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => null);
          throw new Error(errJson?.detail || ('HTTP ' + resp.status));
        }
        const blob = await resp.blob();
        const link = document.createElement('a');
        link.href = URL.createObjectURL(blob);
        link.download = `review_table_${activeReviewTableId}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(link.href);
        showToast("Excel (.xlsx) 文件已下载");
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    async function uploadVaultDocumentFile(file, matterId) {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('doc_type', 'evidence');
      formData.append('redact_on_ingest', 'true');
      const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${matterId}/upload-document`, {
        method: 'POST',
        body: formData
      });
      if (!resp.ok) {
        const errJson = await resp.json().catch(() => null);
        throw new Error(errJson?.detail || ('HTTP ' + resp.status));
      }
      return await resp.json();
    }

    function handleVaultBatchFilesSelect(event) {
      const files = event.target.files;
      if (files && files.length) {
        handleVaultBatchFiles(files);
      }
    }

    async function handleVaultBatchFiles(files) {
      if (!activeMatterId) {
        showToast("请先在上方切换或选择一个在办案件空间！");
        return;
      }
      if (!files || !files.length) return;
      const progressList = document.getElementById('vault-upload-progress-list');
      if (progressList) progressList.innerHTML = '';

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const rowId = `v-up-row-${i}`;
        if (progressList) {
          const rowDiv = document.createElement('div');
          rowDiv.id = rowId;
          rowDiv.style.cssText = "padding: 8px 12px; border-radius: 4px; font-size: 12px; border: 1px solid var(--border-hairline); background: #FFF;";
          // safe-html: escaped file name and status
          rowDiv.innerHTML = `
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:600; color:var(--primary-navy);">${escapeHtml(file.name)}</span>
              <span class="status-msg" style="color:var(--text-muted);">正在上传并解析文本...</span>
            </div>
          `;
          progressList.appendChild(rowDiv);
        }

        try {
          const res = await uploadVaultDocumentFile(file, activeMatterId);
          const rowEl = document.getElementById(rowId);
          if (rowEl) {
            if (res.status === 'ocr_unavailable') {
              rowEl.style.borderColor = '#F59E0B';
              rowEl.style.backgroundColor = '#FFFBEB';
              // safe-html: yellow warning for ocr_unavailable, user filename escaped
              rowEl.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-weight:600; color:#B45309;">${escapeHtml(file.name)}</span>
                  <span class="badge" style="background:#FEF3C7; color:#B45309; font-weight:700;">⚠️ OCR 不可用</span>
                </div>
                <div style="font-size:11px; color:#B45309; margin-top:4px;">
                  ${escapeHtml(res.message || '未安装 OCR 组件（easyocr），图片未识别文字，请安装 requirements-optional.txt 或手工录入')}
                </div>
              `;
            } else {
              rowEl.style.borderColor = '#10B981';
              rowEl.style.backgroundColor = '#ECFDF5';
              // safe-html: success info, all fields escaped
              rowEl.innerHTML = `
                <div style="display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-weight:600; color:#065F46;">${escapeHtml(file.name)}</span>
                  <span class="badge" style="background:#D1FAE5; color:#065F46; font-weight:700;">✓ 解析成功</span>
                </div>
                <div style="font-size:11px; color:#047857; margin-top:4px;">
                  抽取字符: ${escapeHtml(String(res.extracted_chars || 0))} · 页数: ${escapeHtml(String(res.page_count || 1))} · OCR: ${escapeHtml(res.ocr_used ? '是' : '否')} · 脱敏实体: ${escapeHtml(String(res.redacted_count || 0))}
                </div>
              `;
            }
          }
        } catch (err) {
          const rowEl = document.getElementById(rowId);
          if (rowEl) {
            rowEl.style.borderColor = '#EF4444';
            rowEl.style.backgroundColor = '#FEF2F2';
            // safe-html: failure info, error escaped
            rowEl.innerHTML = `
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:600; color:#991B1B;">${escapeHtml(file.name)}</span>
                <span class="badge" style="background:#FEE2E2; color:#991B1B; font-weight:700;">❌ 解析失败</span>
              </div>
              <div style="font-size:11px; color:#DC2626; margin-top:4px;">
                失败原因：${escapeHtml(err.message || '未知错误')}
              </div>
            `;
          }
        }
      }
      await fetchAndRenderMatterDocs(activeMatterId);
    }

    function setupVaultDnD() {
      const box = document.getElementById('vault-dnd-upload-box');
      if (!box) return;
      ['dragenter', 'dragover'].forEach(name => {
        box.addEventListener(name, (e) => {
          e.preventDefault();
          e.stopPropagation();
          box.style.borderColor = 'var(--accent-amber)';
          box.style.backgroundColor = 'rgba(197, 133, 50, 0.05)';
        });
      });
      ['dragleave', 'drop'].forEach(name => {
        box.addEventListener(name, (e) => {
          e.preventDefault();
          e.stopPropagation();
          box.style.borderColor = 'var(--border-hairline)';
          box.style.backgroundColor = '#FAF9F6';
        });
      });
      box.addEventListener('drop', (e) => {
        const files = e.dataTransfer && e.dataTransfer.files;
        if (files && files.length) {
          handleVaultBatchFiles(files);
        }
      });
    }


    const FILING_ITEMS = [
      { key: 'complaint', label: '起诉状' },
      { key: 'engagement', label: '委托手续' },
      { key: 'evidence_catalog', label: '证据目录' },
      { key: 'service_address', label: '送达地址确认书' },
      { key: 'identity', label: '身份证明材料' },
      { key: 'evidence', label: '证据材料' },
    ];
    const FILING_STATUSES = ['未准备', '已准备', '已线下提交', '补正中'];
    let ledgerSealDraft = [];

    function ledgerFeeSuffix(practice) {
      if (!practice) return '';
      const parts = [];
      if (practice.fee_invoiced != null && practice.fee_invoiced !== '') {
        parts.push(`已开票 ${Number(practice.fee_invoiced).toFixed(2)} 元`);
      }
      const seals = practice.seal_records || [];
      if (seals.length) parts.push(`用印 ${seals.length} 次`);
      return parts.length ? ` · ${parts.join(' · ')}` : '';
    }

    function renderSealDraft() {
      const list = document.getElementById('seal-record-list');
      if (!list) return;
      if (!ledgerSealDraft.length) {
        list.innerHTML = '<div style="font-size:12px; color:var(--text-muted);">还没有用印登记。</div>';
        return;
      }
      list.innerHTML = ledgerSealDraft.map((record, index) => `
        <div style="display:flex; justify-content:space-between; gap:8px; align-items:center; font-size:12px; padding:6px 0; border-bottom:1px dashed var(--border-hairline);">
          <span>${escapeHtml(record.filename)} · ${escapeHtml(String(record.copies))} 份 · ${escapeHtml(record.date)}</span>
          <button type="button" class="btn btn-secondary btn-sm" onclick="removeSealDraft(${escapeHtml(String(index))})">删除</button>
        </div>
      `).join('');
    }

    function renderMatterLedger(matter) {
      const box = document.getElementById('filing-checklist-rows');
      if (!box) return;
      if (!matter) {
        box.innerHTML = '<div style="font-size:12px; color:var(--text-muted);">请先选择或新建案件，再登记立案材料和收费。</div>';
        return;
      }
      const practice = matter.practice || {};
      const saved = practice.filing_checklist || [];
      box.innerHTML = FILING_ITEMS.map((item) => {
        const hit = saved.find((row) => row.key === item.key) || {};
        const status = FILING_STATUSES.includes(hit.status) ? hit.status : '未准备';
        const options = FILING_STATUSES.map((name) => {
          const selected = name === status ? ' selected' : '';
          return `<option value="${escapeHtml(name)}"${escapeHtml(selected)}>${escapeHtml(name)}</option>`;
        }).join('');
        return `
          <label style="display:flex; justify-content:space-between; gap:12px; align-items:center; font-size:13px;">
            <span>${escapeHtml(item.label)}</span>
            <select aria-label="${escapeHtml(item.label)}状态" id="filing-status-${escapeHtml(item.key)}" class="quick-input" style="max-width:160px;">${options}</select> // safe-html: 选项文本已逐项 escapeHtml
          </label>
        `;
      }).join('');
      const hint = document.getElementById('ledger-receivable-hint');
      if (hint) {
        const receivable = Number(practice.fee_receivable || 0).toFixed(2);
        hint.textContent = `当前应收 ${receivable} 元。${practice.fee_status_label || ''}已开票不能大于应收。`;
      }
      const invoiced = document.getElementById('ledger-fee-invoiced');
      if (invoiced) invoiced.value = practice.fee_invoiced == null ? '' : practice.fee_invoiced;
      ledgerSealDraft = (practice.seal_records || []).map((record) => ({
        filename: record.filename,
        copies: record.copies,
        date: record.date,
      }));
      renderSealDraft();
      const feeAmount = document.getElementById('ledger-fee-amount');
      const feeReceived = document.getElementById('ledger-fee-received');
      if (feeAmount) feeAmount.value = practice.fee_amount == null ? '' : practice.fee_amount;
      if (feeReceived) feeReceived.value = practice.fee_received == null ? '' : practice.fee_received;
      localFilingDraft = (practice.local_filing_items || []).map((item) => ({
        label: item.label,
        status: item.status || '未准备',
        note: item.note || '',
      }));
      renderLocalFilingRows();
      renderPracticeDesk(matter);
    }

    let localFilingDraft = [];

    function renderLocalFilingRows() {
      const box = document.getElementById('local-filing-rows');
      if (!box) return;
      if (!localFilingDraft.length) {
        box.innerHTML = '<div style="font-size:12px; color:var(--text-muted);">还没有当地额外材料。仲裁程序会预置仲裁材料清单。</div>';
        return;
      }
      box.innerHTML = localFilingDraft.map((item, index) => `
        <div style="display:flex; gap:8px; align-items:center;">
          <span style="flex:1;">${escapeHtml(item.label)}</span>
          <select aria-label="${escapeHtml(item.label)}状态" class="quick-input" style="max-width:140px;" onchange="setLocalFilingStatus(${index}, this.value)">
            ${FILING_STATUSES.map((name) => `<option value="${escapeHtml(name)}"${name === item.status ? ' selected' : ''}>${escapeHtml(name)}</option>`).join('')}
          </select>
          <button type="button" class="btn btn-secondary btn-sm" onclick="removeLocalFilingRow(${index})">删除</button>
        </div>
      `).join('');
    }

    function setLocalFilingStatus(index, value) {
      if (localFilingDraft[index]) localFilingDraft[index].status = value;
    }

    function addLocalFilingRow() {
      const label = (document.getElementById('local-filing-label')?.value || '').trim();
      if (!label) {
        showToast('请填写额外材料名称。');
        return;
      }
      localFilingDraft.push({ label, status: '未准备', note: '' });
      document.getElementById('local-filing-label').value = '';
      renderLocalFilingRows();
    }

    function removeLocalFilingRow(index) {
      localFilingDraft.splice(index, 1);
      renderLocalFilingRows();
    }

    function renderPracticeDesk(matter) {
      const box = document.getElementById('practice-desk-body');
      if (!box || !matter) return;
      const practice = matter.practice || {};
      const claims = practice.claims || [];
      const parties = practice.extra_parties || [];
      const jurisdiction = practice.jurisdiction || {};
      const posture = practice.defendant_posture || {};
      const objection = posture.jurisdiction_objection || {};
      const counter = posture.counterclaim || {};
      const closeout = practice.closeout || {};
      const conclusion = practice.conflict_conclusion || {};
      const conflict = practice.conflict || {};
      box.innerHTML = `
        <div style="margin-bottom:8px;">利冲：${escapeHtml(conflict.status_label || conflict.conflict_level || '未检查')}</div>
        <textarea id="desk-conflict-text" class="quick-input" rows="2" placeholder="需人工判断或须书面同意时，写明核查结论">${escapeHtml(conclusion.text || '')}</textarea>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;">
          <select id="desk-conflict-decision" class="quick-input" style="max-width:160px;">
            <option value="">利冲结论未写</option>
            <option value="可以代理"${conclusion.decision === '可以代理' ? ' selected' : ''}>可以代理</option>
            <option value="不代理"${conclusion.decision === '不代理' ? ' selected' : ''}>不代理</option>
          </select>
          <label style="display:flex; align-items:center; gap:4px;"><input id="desk-conflict-consent" type="checkbox"${conclusion.written_consent ? ' checked' : ''}>已取得各方书面同意</label>
        </div>
        <div style="font-weight:700; margin:10px 0 6px;">并列请求</div>
        <div id="desk-claims">${claims.map((item) => `<div style="padding:4px 0;">${escapeHtml(item.cause)} · ${escapeHtml(item.track || '')} · ${escapeHtml(item.forum || '受理机关未填')}</div>`).join('') || '<div>还没有拆开的请求。</div>'}</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">
          <input id="desk-claim-cause" class="quick-input" placeholder="新增请求的案由" style="max-width:180px;">
          <select id="desk-claim-track" class="quick-input" style="max-width:160px;">
            <option value="civil_court">法院</option>
            <option value="labor_arbitration">劳动仲裁</option>
            <option value="commercial_arbitration">商事仲裁</option>
          </select>
          <input id="desk-claim-forum" class="quick-input" placeholder="受理机关" style="max-width:220px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="addDeskClaim()">加上这条请求</button>
        </div>
        <div style="font-weight:700; margin:10px 0 6px;">管辖路径</div>
        <div>${(jurisdiction.tracks || []).map((item) => `<div style="padding:4px 0;">${escapeHtml(item.cause)}：${escapeHtml(item.reason || '')}</div>`).join('') || '<div>还没有判断。</div>'}</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="runJurisdictionDesk()">按案情判断管辖</button>
          <input id="desk-forum" class="quick-input" placeholder="确认的仲裁委员会或法院" value="${escapeHtml(jurisdiction.confirmed_forum || '')}" style="max-width:280px;">
          <input id="desk-override" class="quick-input" placeholder="仍向法院起诉的理由，可空" value="${escapeHtml(jurisdiction.override_reason || '')}" style="max-width:280px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="confirmJurisdictionDesk()">确认受理机关</button>
        </div>
        <div style="font-weight:700; margin:10px 0 6px;">共同被告、第三人和反诉</div>
        <div>${parties.map((item) => `<div>${escapeHtml(item.role)}：${escapeHtml(item.name)}</div>`).join('') || '<div>还没有追加当事人。</div>'}</div>
        <div style="display:flex; gap:8px; flex-wrap:wrap; margin-top:6px;">
          <select id="desk-party-role" class="quick-input" style="max-width:140px;">
            <option>共同被告</option><option>第三人</option><option>共同原告</option><option>反诉原告</option><option>反诉被告</option>
          </select>
          <input id="desk-party-name" class="quick-input" placeholder="姓名或名称" style="max-width:180px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="addDeskParty()">添加当事人</button>
        </div>
        <label style="display:flex; gap:6px; margin-top:8px;"><input id="desk-objection" type="checkbox"${objection.prepared ? ' checked' : ''}>准备管辖异议</label>
        <input id="desk-objection-basis" class="quick-input" placeholder="管辖异议依据" value="${escapeHtml(objection.basis || '')}" style="margin-top:6px;">
        <label style="display:flex; gap:6px; margin-top:8px;"><input id="desk-counter" type="checkbox"${counter.prepared ? ' checked' : ''}>准备反诉</label>
        <input id="desk-counter-claims" class="quick-input" placeholder="反诉请求" value="${escapeHtml(counter.claims || '')}" style="margin-top:6px;">
        <div style="font-weight:700; margin:10px 0 6px;">结案确认</div>
        <input id="desk-judgment" class="quick-input" placeholder="裁判或处理结果" value="${escapeHtml(closeout.judgment_result || '')}">
        <input id="desk-conflict-closed" type="date" class="quick-input" value="${escapeHtml(closeout.conflict_closed_on || '')}" style="margin-top:6px; max-width:180px;">
        <input id="desk-fees-note" class="quick-input" placeholder="未收律师费的处理说明" value="${escapeHtml(closeout.fees_note || '')}" style="margin-top:6px;">
        <label style="display:flex; gap:6px; margin-top:6px;"><input id="desk-appeal-cleared" type="checkbox"${closeout.appeal_window_cleared ? ' checked' : ''}>上诉、起诉或撤销期限已届满或已处理</label>
        <label style="display:flex; gap:6px; margin-top:6px;"><input id="desk-originals" type="checkbox"${closeout.originals_returned ? ' checked' : ''}>原件已退还</label>
        <label style="display:flex; gap:6px; margin-top:6px;"><input id="desk-fees-settled" type="checkbox"${closeout.fees_settled ? ' checked' : ''}>律师费已结清或没有应收</label>
        <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:10px;">
          <button type="button" class="btn btn-secondary btn-sm" onclick="savePracticeDesk()">保存请求和管辖</button>
          <button type="button" class="btn btn-sm" onclick="archiveMatterWithCloseout()">确认后归档</button>
        </div>
      `;
    }

    function addSealDraft() {
      const filename = (document.getElementById('seal-filename')?.value || '').trim();
      const copiesRaw = document.getElementById('seal-copies')?.value;
      const date = document.getElementById('seal-date')?.value || '';
      if (!filename) {
        showToast('请填写用印文件名。');
        return;
      }
      const copies = Number(copiesRaw);
      if (!Number.isInteger(copies) || copies < 1 || copies > 99) {
        showToast('用印份数必须是 1 到 99 的整数。');
        return;
      }
      if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) {
        showToast('请选择用印日期。');
        return;
      }
      ledgerSealDraft.push({ filename, copies, date });
      document.getElementById('seal-filename').value = '';
      document.getElementById('seal-copies').value = '';
      document.getElementById('seal-date').value = '';
      renderSealDraft();
    }

    function removeSealDraft(index) {
      ledgerSealDraft.splice(index, 1);
      renderSealDraft();
    }

    async function saveMatterLedger() {
      if (!activeMatterId) {
        showToast('请先选择或新建案件。');
        return;
      }
      const practice = (activeMatterData && activeMatterData.practice) || {};
      const rawInvoiced = document.getElementById('ledger-fee-invoiced')?.value;
      const feeInvoiced = rawInvoiced === '' || rawInvoiced == null ? null : Number(rawInvoiced);
      if (feeInvoiced != null && Number.isNaN(feeInvoiced)) {
        showToast('已开票金额必须是数字。');
        return;
      }
      if (feeInvoiced != null && feeInvoiced < 0) {
        showToast('已开票金额不能为负数。');
        return;
      }
      const receivable = Number(practice.fee_receivable || 0);
      if (feeInvoiced != null && Math.round(feeInvoiced * 100) > Math.round(receivable * 100)) {
        showToast(`已开票金额不能大于应收。当前应收 ${receivable.toFixed(2)} 元，填写的已开票 ${feeInvoiced.toFixed(2)} 元。`);
        return;
      }
      const filing = FILING_ITEMS.map((item) => ({
        key: item.key,
        status: document.getElementById(`filing-status-${item.key}`)?.value || '未准备',
      }));
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/ledger`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            fee_invoiced: feeInvoiced,
            fee_amount: optionalLedgerNumber('ledger-fee-amount'),
            fee_received: optionalLedgerNumber('ledger-fee-received'),
            seal_records: ledgerSealDraft,
            filing_checklist: filing,
            local_filing_items: localFilingDraft,
          }),
        });
        const data = await resp.json();
        activeMatterData = data.matter || activeMatterData;
        const found = allVaultMatters.find((item) => item.matter_id === activeMatterId);
        if (found && activeMatterData) found.practice = activeMatterData.practice;
        renderMatterLedger(activeMatterData);
        renderMattersGrid(allVaultMatters);
        const vRole = document.getElementById('vault-matter-role');
        if (vRole && activeMatterData) {
          const practice = activeMatterData.practice || {};
          const feeLine = [practice.fee_type_label || '收费未约定', practice.fee_status_label].filter(Boolean).join(' · ') + ledgerFeeSuffix(practice);
          vRole.innerText = `${activeMatterData.plaintiff_name || '原告未填'} 诉 ${activeMatterData.defendant_name || '被告未填'} · ${practice.procedure_label || '程序未选'} · ${feeLine}`;
        }
        showToast(data.message || '已保存。状态由律师录入，不代表法院已经受理。');
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('保存失败：' + e), 'error');
      }
    }

    function optionalLedgerNumber(id) {
      const raw = document.getElementById(id)?.value;
      if (raw === '' || raw == null) return null;
      const num = Number(raw);
      return Number.isNaN(num) ? null : num;
    }

    function readCloseoutFromDesk() {
      return {
        judgment_result: (document.getElementById('desk-judgment')?.value || '').trim(),
        appeal_window_cleared: !!document.getElementById('desk-appeal-cleared')?.checked,
        originals_returned: !!document.getElementById('desk-originals')?.checked,
        fees_settled: !!document.getElementById('desk-fees-settled')?.checked,
        fees_note: (document.getElementById('desk-fees-note')?.value || '').trim(),
        conflict_closed_on: document.getElementById('desk-conflict-closed')?.value || '',
      };
    }

    async function savePracticeDesk(extra) {
      if (!activeMatterId) {
        showToast('请先选择案件。');
        return null;
      }
      const practice = (activeMatterData && activeMatterData.practice) || {};
      const payload = Object.assign({
        conflict_conclusion: {
          decision: document.getElementById('desk-conflict-decision')?.value || '',
          text: (document.getElementById('desk-conflict-text')?.value || '').trim(),
          written_consent: !!document.getElementById('desk-conflict-consent')?.checked,
        },
        defendant_posture: {
          jurisdiction_objection: {
            prepared: !!document.getElementById('desk-objection')?.checked,
            basis: (document.getElementById('desk-objection-basis')?.value || '').trim(),
          },
          counterclaim: {
            prepared: !!document.getElementById('desk-counter')?.checked,
            claims: (document.getElementById('desk-counter-claims')?.value || '').trim(),
          },
        },
        claims: practice.claims || [],
        extra_parties: practice.extra_parties || [],
      }, extra || {});
      const resp = await api.request(`${API_BASE}/api/v1/vault/matters/${activeMatterId}/practice-desk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      activeMatterData = data.matter || activeMatterData;
      renderPracticeDesk(activeMatterData);
      return data;
    }

    async function addDeskClaim() {
      const cause = (document.getElementById('desk-claim-cause')?.value || '').trim();
      if (!cause) {
        showToast('请填写这条请求的案由。');
        return;
      }
      const practice = (activeMatterData && activeMatterData.practice) || {};
      const claims = (practice.claims || []).concat([{
        cause,
        track: document.getElementById('desk-claim-track')?.value || 'civil_court',
        forum: (document.getElementById('desk-claim-forum')?.value || '').trim(),
        pleading: '',
      }]);
      try {
        await savePracticeDesk({ claims });
        showToast('已加上这条请求。');
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('保存请求失败：' + e), 'error');
      }
    }

    async function addDeskParty() {
      const name = (document.getElementById('desk-party-name')?.value || '').trim();
      if (!name) {
        showToast('请填写当事人名称。');
        return;
      }
      const practice = (activeMatterData && activeMatterData.practice) || {};
      const extra = (practice.extra_parties || []).concat([{
        role: document.getElementById('desk-party-role')?.value || '共同被告',
        name,
      }]);
      try {
        await savePracticeDesk({ extra_parties: extra });
        showToast('已添加当事人。');
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('添加失败：' + e), 'error');
      }
    }

    async function runJurisdictionDesk() {
      const facts = [
        (activeMatterData && activeMatterData.cause_of_action) || '',
        (activeMatterData && activeMatterData.case_summary) || '',
        (document.getElementById('new-matter-summary')?.value || ''),
      ].join('\n');
      try {
        await savePracticeDesk({ jurisdiction_facts: facts });
        showToast('管辖路径已列出。确认受理机关后才能生成文书。');
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('管辖判断失败：' + e), 'error');
      }
    }

    async function confirmJurisdictionDesk() {
      const forum = (document.getElementById('desk-forum')?.value || '').trim();
      if (!forum) {
        showToast('请写明确认的仲裁委员会或法院。');
        return;
      }
      try {
        await savePracticeDesk({
          jurisdiction_confirm: {
            confirmed_forum: forum,
            override_reason: (document.getElementById('desk-override')?.value || '').trim(),
          },
        });
        showToast('受理机关已确认。');
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('确认失败：' + e), 'error');
      }
    }

    async function archiveMatterWithCloseout() {
      if (!activeMatterId) return;
      try {
        await updateMatterStatusUI(activeMatterId, 'archived', readCloseoutFromDesk());
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('归档失败：' + e), 'error');
      }
    }

    function openDeadlineMatter(matterId) {
      const id = String(matterId || '').trim();
      if (!id) return;
      const nav = document.getElementById('nav-graphs');
      if (nav && typeof switchNavTab === 'function') {
        switchNavTab('tab-graphs', '07 案件空间与核心图谱中枢', nav);
      }
      switchActiveMatter(id, true);
    }

    async function loadTodayDeadlineBoard() {
      const box = document.getElementById('today-deadlines-list');
      if (!box) return;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/deadlines/board`);
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        const data = await resp.json();
        const groups = data.groups || [];
        if (!groups.length) {
          box.textContent = '还没有期限。计算器里算出日子后，点「加入案件期限」，这里才会提醒。';
          return;
        }
        box.innerHTML = groups.map((group) => {
          const matterId = escapeHtml(group.matter_id || '');
          const title = escapeHtml(group.matter_title || '未命名案件');
          const urgent = group.urgent ? ' · 临期' : '';
          const head = matterId
            ? `<button type="button" class="today-deadline-open" data-matter-id="${matterId}" title="打开该案" style="display:block;width:100%;text-align:left;background:transparent;border:0;padding:0;margin:0;cursor:pointer;color:inherit;font:inherit;font-weight:700;">${title}${urgent}</button>`
            : `<div style="font-weight:700;">${title}${urgent}</div>`;
          const items = (group.items || []).map((item) => {
            const days = item.days_left < 0 ? `已逾期 ${Math.abs(item.days_left)} 天` : `剩余 ${item.days_left} 天`;
            const line = escapeHtml(`${item.due_date || ''} · ${days} · ${item.kind || ''} ${item.note || ''}`.replace(/\s+/g, ' ').trim());
            if (!matterId) return `<div>${line}</div>`;
            return `<button type="button" class="today-deadline-open" data-matter-id="${matterId}" title="打开该案" style="display:block;width:100%;text-align:left;background:transparent;border:0;padding:4px 0;margin:0;cursor:pointer;color:inherit;font:inherit;">${line}</button>`;
          }).join('');
          return `<div style="margin-bottom:8px; padding:8px; border-radius:6px; background:${group.urgent ? '#FEF2F2' : '#FFF'};">${head}${items}</div>`;
        }).join('');
        box.querySelectorAll('.today-deadline-open').forEach((el) => {
          el.addEventListener('click', () => openDeadlineMatter(el.getAttribute('data-matter-id')));
        });
      } catch (e) {
        box.textContent = '期限清单暂时没有读到。';
        showToast('期限清单暂时没有读到。', 'error');
      }
    }

    async function fetchAndRenderVaultDeadlines() {
      const container = document.getElementById('vault-deadlines-list');
      if (!container) return;
      container.innerHTML = `<div style="text-align:center; padding:20px; color:var(--text-muted); font-size:12px;">正在加载案件期限日历...</div>`;
      try {
        const url = activeMatterId
          ? `${API_BASE}/api/v1/vault/deadlines?matter_id=${activeMatterId}`
          : `${API_BASE}/api/v1/vault/deadlines`;
        const resp = await api.request(url);
        if (!resp.ok) {
          throw new Error('HTTP ' + resp.status);
        }
        const res = await resp.json();
        const list = res.deadlines || [];
        renderVaultDeadlinesList(list);
      } catch (e) {
        // safe-html: error display
        container.innerHTML = `
          <div style="text-align:center; padding:20px; color:var(--status-warn); font-size:12px;">加载期限日历失败: ${escapeHtml(e.message)}</div>
        `;
        showToast('期限日历没有读到。', 'error');
      }
    }

    function renderVaultDeadlinesList(list) {
      const container = document.getElementById('vault-deadlines-list');
      if (!container) return;
      if (!list.length) {
        container.innerHTML = `<div style="text-align:center; padding:30px; color:var(--text-muted); font-size:12px;">当前案件空间暂无期限记录。可在实务精算各计算器中点击【加入案件期限】或点击右上角【手工录入期限】。</div>`;
        return;
      }
      const today = new Date().toISOString().substring(0, 10);
      const kindMap = {
        'statute_limitation': { label: '诉讼时效', bg: '#FEF3C7', color: '#B45309' },
        'appeal': { label: '上诉期', bg: '#DBEAFE', color: '#1E40AF' },
        'defense_answer': { label: '答辩期', bg: '#FFEDD5', color: '#9A3412' },
        'evidence_production': { label: '举证期限', bg: '#ECFDF5', color: '#047857' },
        'preservation_renewal': { label: '续行保全', bg: '#FEE2E2', color: '#991B1B' },
        'enforcement_application': { label: '执行申请', bg: '#E0E7FF', color: '#3730A3' },
        'hearing': { label: '开庭审理', bg: '#F3E8FF', color: '#6B21A8' },
        'service_received': { label: '送达日', bg: '#E0F2FE', color: '#075985' },
        'labor_arbitration': { label: '劳动仲裁时效', bg: '#FEF3C7', color: '#B45309' },
        'labor_award_sue': { label: '裁决后起诉', bg: '#DBEAFE', color: '#1E40AF' },
        'labor_award_revoke': { label: '撤销终局裁决', bg: '#FEE2E2', color: '#991B1B' },
        'arbitration_set_aside': { label: '撤销商事裁决', bg: '#E0E7FF', color: '#3730A3' },
        'custom': { label: '其他期限', bg: '#F3F4F6', color: '#374151' }
      };
      container.innerHTML = list.map(item => { // safe-html: deadline card with escaped properties
        const kInfo = kindMap[item.kind] || { label: item.kind, bg: '#F3F4F6', color: '#374151' };
        const due = (item.due_date || '').substring(0, 10);
        let daysLeft = null;
        let isUrgent = false;
        if (due && item.kind !== 'service_received') {
          const diffMs = new Date(due).getTime() - new Date(today).getTime();
          daysLeft = Math.ceil(diffMs / (1000 * 60 * 60 * 24));
          if (daysLeft <= 7) isUrgent = true;
        }
        const daysLabel = daysLeft !== null
          ? (daysLeft < 0 ? `已逾期 ${Math.abs(daysLeft)} 天` : `剩余 ${daysLeft} 天`)
          : (item.kind === 'service_received' ? '已录入' : '');
        const borderStyle = isUrgent
          ? 'border-left: 4px solid #EF4444; background: #FEF2F2;'
          : 'border-left: 4px solid var(--primary-navy); background: #FAF9F6;';
        const countdownBadge = isUrgent
          ? `<span class="badge" style="background: #FEE2E2; color: #DC2626; font-weight: 700; border: 1px solid #FCA5A5;">⚠️ ${escapeHtml(daysLabel)}</span>`
          : `<span class="badge" style="background: #E0E7FF; color: #3730A3; font-weight: 600;">${escapeHtml(daysLabel)}</span>`;
        return `
          <div style="border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 10px 14px; ${borderStyle}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span class="badge" style="background: ${escapeHtml(kInfo.bg)}; color: ${escapeHtml(kInfo.color)}; font-weight: 600; font-size: 11px;">${escapeHtml(kInfo.label)}</span>
                ${item.origin_label ? `<span class="badge" style="background:#F8FAFC; color:#334155; border:1px solid #CBD5E1; font-size:11px;">${escapeHtml(item.origin_label)}</span>` : ''}
                <strong style="font-size: 13px; color: var(--primary-navy); font-family: var(--font-mono);">${escapeHtml(item.due_date)}</strong>
                ${countdownBadge}
              </div>
              <span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(item.created_at ? item.created_at.substring(0, 10) : '')}</span>
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); line-height: 1.5;">
              ${escapeHtml(item.source ? '来源：' + item.source : '')}
              ${escapeHtml(item.note ? ' · 备忘：' + item.note : '')}
            </div>
          </div>
        `;
      }).join('');
    }

    function parseRosterRelatives(text) {
      return String(text || '').split(/\n+/).map((line) => line.trim()).filter(Boolean).map((line) => {
        const parts = line.split(/[,，\s]+/).filter(Boolean);
        const name = parts[0] || '';
        let relation = '近亲属';
        let idNo = '';
        const tail = parts[parts.length - 1] || '';
        const tailDigits = tail.replace(/[^\d]/g, '');
        const tailLooksLikeId = parts.length >= 3 && tailDigits.length >= 6 && tailDigits.length >= tail.length - 2;
        if (tailLooksLikeId) {
          idNo = tail;
          relation = parts.slice(1, -1).join('') || '近亲属';
        } else if (parts.length >= 2) {
          relation = parts.slice(1).join('') || '近亲属';
        }
        return { name, relation, id_no: idNo };
      }).filter((item) => item.name);
    }

    async function loadFirmRoster() {
      const box = document.getElementById('firm-roster-list');
      if (!box) return;
      box.textContent = '正在读取本所名册…';
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/firm-roster`);
        const data = await resp.json();
        const lawyers = data.lawyers || [];
        if (!lawyers.length) {
          box.innerHTML = '<div>名册还是空的。空名册时接案会写明「本所人员未录入，此项未检查」。</div>';
          return;
        }
        box.innerHTML = lawyers.map((item) => {
          const relatives = (item.relatives || []).map((rel) => {
            const idText = rel.id_no ? ('，证件' + rel.id_no) : '';
            return (rel.name || '') + '（' + (rel.relation || '') + idText + '）';
          }).join('、') || '未登记近亲属';
          return `<div style="border:1px solid var(--border-hairline); border-radius:6px; padding:8px 10px; margin-bottom:8px;">
            <div style="display:flex; justify-content:space-between; gap:8px;">
              <strong>${escapeHtml(item.lawyer_name)}</strong>
              <button type="button" class="btn btn-secondary btn-sm" onclick="deleteFirmRosterLawyer(${escapeHtml(String(Number(item.id) || ''))})">删除</button>
            </div>
            <div>${escapeHtml(item.law_firm || '事务所未填')} · 执业证 ${escapeHtml(item.license_no || '未填')} · 身份证 ${escapeHtml(item.id_no || '未填')}${escapeHtml(item.is_default ? ' · 文书默认' : '')}</div>
            <div>近亲属：${escapeHtml(relatives)}</div>
          </div>`;
        }).join('');
      } catch (e) {
        box.textContent = e instanceof ApiError ? e.userMessage : '名册读取失败';
      }
    }

    async function saveFirmRosterLawyer() {
      const lawyerName = (document.getElementById('roster-lawyer-name')?.value || '').trim();
      if (!lawyerName) {
        showToast('请填写律师姓名');
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/firm-roster`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            lawyer_name: lawyerName,
            license_no: (document.getElementById('roster-license')?.value || '').trim(),
            id_no: (document.getElementById('roster-id-no')?.value || '').trim(),
            law_firm: (document.getElementById('roster-firm')?.value || '').trim(),
            phone: (document.getElementById('roster-phone')?.value || '').trim(),
            relatives: parseRosterRelatives(document.getElementById('roster-relatives')?.value || ''),
            is_default: !!document.getElementById('roster-is-default')?.checked,
          }),
        });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        showToast('本所名册已保存');
        await loadFirmRoster();
        if (typeof window.fillLawyerProfileFields === 'function') window.fillLawyerProfileFields();
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('名册保存失败: ' + e), 'error');
      }
    }

    async function deleteFirmRosterLawyer(lawyerId) {
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/firm-roster/${lawyerId}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error('HTTP ' + resp.status);
        showToast('已从本所名册删除');
        await loadFirmRoster();
      } catch (e) {
        showToast(e instanceof ApiError ? e.userMessage : ('删除失败: ' + e), 'error');
      }
    }

export {
  CaseContextStore,
  activeMatterId,
  activeMatterData,
  allVaultMatters,
  renderGlobalCaseBar,
  updateTabContextDisplays,
  syncCurrentCalcToCaseContext,
  dismissCalcSyncEmptyNotice,
  hideCalcSyncEmptyNoticeIfFilled,
  applyCaseContextToLitigation,
  applyCaseContextToDeepMatrix,
  loadCaseContextToDeepPanel,
  submitCustomDeepMatrixAnalyze,
  toggleSelectStatuteFromList,
  openSelectedStatutesDrawer,
  openCaseContextModal,
  closeCaseContextModal,
  handleCaseModalBackdropClick,
  syncModalCaseCauseBadge,
  renderModalStatutesList,
  removeStatuteFromCase,
  saveCaseContextFromModal,
  resetCaseContextToDefault,
  clearCaseContextToNew,
  syncCalcFromTab01ToModal,
  clearDemoDataUI,
  updateDemoDataBadge,
  initMatterVault,
  openMatterVaultModal,
  closeMatterVaultModal,
  handleMatterVaultBackdropClick,
  updateDemoDataClearButton,
  clearVaultDemoData,
  fetchAndRenderMattersList,
  filterMattersList,
  renderMattersGrid,
  switchActiveMatter,
  openNewMatterDrawer,
  closeNewMatterDrawer,
  submitCreateNewMatter,
  previewNewMatterPersonnel,
  loadFirmRoster,
  saveFirmRosterLawyer,
  deleteFirmRosterLawyer,
  openMountDocModal,
  closeMountDocModal,
  handleMountDocBackdropClick,
  submitMountDocument,
  fetchAndRenderMatterDocs,
  switchVaultGraphTab,
  fetchAndRenderMatterGraphs,
  runExtractMatterGraphs,
  renderTimelineGraph,
  runGuaranteeAnalysisUI,
  renderGuaranteeSummaryBar,
  renderTopologySVG,
  renderEntityCardsWithGuarantee,
  copyGuaranteeTacticalMemo,
  renderEntityGraph,
  runCashflowAudit,
  switchCashflowMode,
  renderCashflowWithMode,
  copyCashflowStatement,
  renderCashflowGraph,
  switchLitigationMode,
  updateWorkflowStepperUI,
  startLitigationWorkflowUI,
  renderWorkflowStepUI,
  advanceWorkflowStep2UI,
  advanceWorkflowStep4UI,
  rollbackWorkflowUI,
  resetWorkflowUI,
  fetchAndRenderReviewTables,
  loadReviewTableData,
  renderReviewGrid,
  runCellRefreshUI,
  runColumnRefreshUI,
  runAllReviewTableUI,
  exportReviewTableCsvUI,
  openAddReviewColumnModal,
  closeAddReviewColumnModal,
  handleAddColumnBackdropClick,
  submitAddReviewColumn,
  deleteReviewColumnUI,
  switchGroundingTab,
  openSourceGroundingViewer,
  closeSourceGroundingViewer,
  copyGroundingSnippet,
  copyGroundingAnchor,
  updateMatterStatusUI,
  deleteMatterUI,
  exportReviewTableXlsxUI,
  uploadVaultDocumentFile,
  handleVaultBatchFilesSelect,
  handleVaultBatchFiles,
  setupVaultDnD,
  fetchAndRenderVaultDeadlines,
  renderVaultDeadlinesList,
  renderMatterLedger,
  addSealDraft,
  removeSealDraft,
  saveMatterLedger,
  loadTodayDeadlineBoard,
  toggleCustomCause,
  loadCauseCatalog,
  addLocalFilingRow,
  setLocalFilingStatus,
  removeLocalFilingRow,
  addDeskClaim,
  addDeskParty,
  runJurisdictionDesk,
  confirmJurisdictionDesk,
  savePracticeDesk,
  archiveMatterWithCloseout,
};

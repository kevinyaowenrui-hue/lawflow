/**
 * LawFlow Module: 01_calc.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const CALC_TAB_HTML = `      
      <!-- 1. 顶部高频要素即时速查条 (单行/双行紧凑常驻) -->
      <div class="quick-lookup-bar">
        <!-- 工具 1: 人民币大写实时转 -->
        <div class="quick-tool-col">
          <div class="quick-tool-header">
            <span>人民币大写实时转换</span>
            <span class="tool-tip">输入即转 · 点击大写一键复制</span>
          </div>
          <div class="quick-input-group">
            <input aria-label="人民币大写实时转换金额"  type="number" id="rmb-input" class="quick-input" value="123000.50" step="0.01" placeholder="输入金额数字" oninput="handleRmbInput()">
            <div role="button" tabindex="0"  class="live-badge amber" id="rmb-result-badge" title="点击复制标准大写金额" onclick="copyBadgeText('rmb-result-badge', '已复制大写金额')">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
              <span id="rmb-result-text">人民币壹拾贰万叁仟元伍角整</span>
            </div>
          </div>
        </div>

        <!-- 工具 2: 主体资格秒查 (18位身份证 / 统一社会信用代码二合一) -->
        <div class="quick-tool-col">
          <div class="quick-tool-header">
            <span>主体资格秒查 (身份证 / 统一信用代码二合一)</span>
            <span class="tool-tip">自动识别个人退休资格或企业信用代码</span>
          </div>
          <div class="quick-input-group">
            <input aria-label="主体资格核验（身份证或统一社会信用代码）"  type="text" id="subject-input" class="quick-input" value="110101196001012377" maxlength="18" placeholder="粘贴18位身份证号或企业统一信用代码" oninput="handleSubjectInput(event)" onkeydown="if(event.key==='Enter') runSubjectValidate()">
            <button class="btn btn-secondary btn-sm" onclick="runSubjectValidate()">核验</button>
            <div role="button" tabindex="0"  class="live-badge warn" id="subject-result-badge" title="点击复制定性法律说明" onclick="copySubjectNote()">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
              <span id="subject-result-text">66岁 · 男 · 已达退休年龄（劳务关系）</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 2. 下方主工作区采用【左算右稿 (55% : 45%)】分屏结构 -->
      <div class="split-grid-55-45">
        
        <!-- 左栏：精算参数台 (胶囊分段控制器切换三大计算器) -->
        <div class="surface-card">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
              精算参数台
            </div>
            <!-- 胶囊分段控制器 (已扩充三大专业级实务防线计算) -->
            <div class="segmented-control" style="flex-wrap: wrap;">
              <button class="segmented-btn active" id="seg-btn-lpr" onclick="switchCalcSegment('lpr')">LPR 逾期利息</button>
              <button class="segmented-btn" id="seg-btn-court" onclick="switchCalcSegment('court')">诉讼与保全费</button>
              <button class="segmented-btn" id="seg-btn-labor" onclick="switchCalcSegment('labor')">劳动仲裁补偿</button>
              <button class="segmented-btn" id="seg-btn-statute" onclick="switchCalcSegment('statute')">诉讼时效推算</button>
              <button class="segmented-btn" id="seg-btn-preserv" onclick="switchCalcSegment('preserv')">保全续封红线</button>
              <button class="segmented-btn" id="seg-btn-validity" onclick="switchCalcSegment('validity')">法条时效核验</button>
              <button class="segmented-btn" id="seg-btn-settlement" onclick="switchCalcSegment('settlement')">商业和解与抵债</button>
              <button class="segmented-btn" id="seg-btn-appeal" onclick="switchCalcSegment('appeal')">上诉期截止日</button>
            </div>
          </div>

          <!-- 子表单 A: LPR 逾期利息精算 -->
          <div id="calc-pane-lpr" class="calc-sub-pane">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">拖欠本金 (元)</label>
                <input aria-label="lpr p"  type="number" id="lpr-p" value="200000" step="1000">
              </div>
              <div class="form-group">
                <label class="form-label">起息日</label>
                <input aria-label="lpr start"  type="date" id="lpr-start" value="2023-01-01">
              </div>
              <div class="form-group">
                <label class="form-label">截止日</label>
                <input aria-label="lpr end"  type="date" id="lpr-end" value="2024-01-01">
              </div>
            </div>

            <div class="form-row" style="margin-top: 14px;">
              <div class="form-group">
                <label class="form-label">执行利率标准</label>
                <select aria-label="lpr mult"  id="lpr-mult">
                  <option value="1.0">1.0 倍 LPR (同期贷款市场报价基准)</option>
                  <option value="1.5">1.5 倍 LPR (合同约定逾期加计 50%)</option>
                  <option value="4.0">4.0 倍 LPR (民间借贷司法保护红线)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">利率期限品种</label>
                <select aria-label="LPR利率期限品种（1年期/5年期以上）"  id="lpr-term">
                  <option value="1Y">一年期 LPR (流动性借款常用)</option>
                  <option value="5Y">五年期以上 LPR (长期固定资产类)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">起诉日期（2020-08-20 前成立的民间借贷合同必填）</label>
                <input aria-label="lpr filing"  type="date" id="lpr-filing" value="">
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runLprCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
                核算逾期利息并生成诉状公文段落
              </button>
            </div>
          </div>

          <!-- 子表单 B: 诉讼费与保全费核算 -->
          <div id="calc-pane-court" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">诉讼请求标的金额 (元)</label>
                <input aria-label="fee amount"  type="number" id="fee-amount" value="500000" step="5000">
              </div>
              <div class="form-group">
                <label class="form-label">审理程序</label>
                <select aria-label="fee proc"  id="fee-proc">
                  <option value="false">普通程序 (全额交纳)</option>
                  <option value="true">简易程序 / 调解结案 (减半交纳)</option>
                </select>
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runCourtFeeCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                核算案件受理费与保全费
              </button>
            </div>
          </div>

          <!-- 子表单 C: 劳动仲裁赔偿金 (N / N+1 / 2N) -->
          <div id="calc-pane-labor" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">劳动者离职前12个月平均工资 (元)</label>
                <input aria-label="labor salary"  type="number" id="labor-salary" value="12000" step="500">
              </div>
              <div class="form-group">
                <label class="form-label">当地职工月平均工资 (选填，用于社平三倍封顶)</label>
                <input aria-label="默认 11500"  type="number" id="labor-avg-salary" value="11500" placeholder="默认 11500">
              </div>
            </div>

            <div class="form-row" style="margin-top: 14px;">
              <div class="form-group">
                <label class="form-label">入职日期</label>
                <input aria-label="实际入职起算日期"  type="date" id="labor-hire-date" value="2021-03-01">
              </div>
              <div class="form-group">
                <label class="form-label">解除劳动关系日期</label>
                <input aria-label="labor term date"  type="date" id="labor-term-date" value="2024-05-15">
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runLaborArbitrationCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                精算仲裁补偿金 (N / N+1 / 2N)
              </button>
            </div>
          </div>

          <!-- 子表单 D: 诉讼时效与除斥期间精算 (《民法典》第188/194/195/199条) -->
          <div id="calc-pane-statute" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">时效起算日期 (知道权利受损/还款期满日)</label>
                <input aria-label="statute start"  type="date" id="statute-start" value="2023-03-10">
              </div>
              <div class="form-group">
                <label class="form-label">诉讼时效/除斥期间法定类型</label>
                <select aria-label="statute type"  id="statute-type">
                  <option value="general_3y">普通民事诉讼时效（3年，民法典第188条）</option>
                  <option value="intl_trade_4y">国际买卖与技术进出口争议（4年，民法典第594条）</option>
                  <option value="cancel_mistake_90d">重大误解撤销权（90日）</option>
                  <option value="cancel_right_1y">欺诈/显失公平撤销权（1年，不适用中断）</option>
                  <option value="construction_priority_18m">建工价款优先受偿权除斥期间（18个月）</option>
                  <option value="rescission_right_1y">合同解除权除斥期间（1年，民法典第564条）</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">行为发生日（撤销权校验5年最长除斥）</label>
                <input aria-label="statute act date"  type="date" id="statute-act-date" value="">
              </div>
            </div>

            <div class="form-group" style="margin-top: 12px;">
              <label class="form-label">
                <span>时效中断事由留痕 (催告/还款自认/仲裁，每行一次)</span>
              </label>
              <textarea aria-label="例如：2023-09-15 借款人在微信中回复宽限两个月并承诺付息&#10;2024-03-10 发送EMS律师催告函签收"  id="statute-interrupt-notes" rows="2" placeholder="例如：2023-09-15 借款人在微信中回复宽限两个月并承诺付息&#10;2024-03-10 发送EMS律师催告函签收">2023-09-15 李四在微信中确认欠款并请求宽限两个月承诺照付利息</textarea>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runStatuteLimitCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                推演诉讼时效剩余天数与中断推演
              </button>
            </div>
          </div>

          <!-- 子表单 E: 财产保全续查封续冻结红线精算 (法释〔2016〕22号第18条) -->
          <div id="calc-pane-preserv" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">保全标的财产类型</label>
                <select aria-label="preserv type"  id="preserv-type">
                  <option value="bank_deposit">银行存款及其他资金冻结 (限1年 / 届满七日前申请续冻)</option>
                  <option value="movable_property">动产车辆、机器设备查封 (限2年 / 届满七日前申请续封)</option>
                  <option value="real_estate_equity">不动产房产土地、股权冻结 (限3年 / 届满七日前申请续封)</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">法院首封/冻结裁定生效日期</label>
                <input aria-label="preserv start"  type="date" id="preserv-start" value="2024-01-15">
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runPreservationRenewalCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
                核算法定续封截止红线与穿仓预警
              </button>
            </div>
          </div>

          <!-- 子表单 F: 规范性法律文件现行有效性与废止拦截核验 -->
          <div id="calc-pane-validity" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">拟援引法律规范/条文文本</label>
                <input aria-label="输入法规名称或条款，如《合同法》《民法通则》《物权法》"  type="text" id="validity-citation" value="依据《中华人民共和国合同法》第一百零七条及《担保法》第十九条" placeholder="输入法规名称或条款，如《合同法》《民法通则》《物权法》">
              </div>
              <div class="form-group">
                <label class="form-label">争议法律事实发生日期 (用于时间效力判定)</label>
                <input aria-label="validity incident date"  type="date" id="validity-incident-date" value="2023-05-01">
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runStatuteValidityCheck()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                探针核验法条时效状态 (废止拦截与新旧法衔接)
              </button>
            </div>
          </div>

          <!-- 子表单 G: 商业和解与以物抵债现值/回收率精算 (NPV & Debt-for-Asset) -->
          <div id="calc-pane-settlement" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">债权标的名义总额 (元)</label>
                <input aria-label="settle claim"  type="number" id="settle-claim" value="5000000" step="50000">
              </div>
              <div class="form-group">
                <label class="form-label">年化资本折现率 (%)</label>
                <input aria-label="settle rate"  type="number" id="settle-rate" value="8.0" step="0.5">
              </div>
              <div class="form-group">
                <label class="form-label">和解方案模式</label>
                <select aria-label="settle type"  id="settle-type" onchange="toggleSettlementPlanUI()">
                  <option value="hybrid">混合方案 (现金分期 + 工抵房/不动产)</option>
                  <option value="debt_for_asset">纯以物抵债方案 (房产/股权/设备)</option>
                  <option value="cash_installments">纯现金分期和解 (无抵债资产)</option>
                </select>
              </div>
            </div>

            <!-- 现金分期子卡片 -->
            <div id="settle-cash-card" style="margin-top: 12px; background: #FAF9F6; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 10px 12px;">
              <div style="font-size: 11.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px; display: flex; justify-content: space-between;">
                <span>💵 现金分期回款安排 (首期及后续款项)</span>
                <span style="font-size: 10.5px; color: var(--text-muted);">自动按月计算折现净值</span>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">第1期：月数 / 金额</label>
                  <div style="display:flex; gap:6px;">
                    <input aria-label="月"  type="number" id="settle-m1" value="3" style="width:38%;" placeholder="月">
                    <input aria-label="元"  type="number" id="settle-a1" value="500000" style="width:62%;" placeholder="元">
                  </div>
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">第2期：月数 / 金额</label>
                  <div style="display:flex; gap:6px;">
                    <input aria-label="月"  type="number" id="settle-m2" value="6" style="width:38%;" placeholder="月">
                    <input aria-label="元"  type="number" id="settle-a2" value="500000" style="width:62%;" placeholder="元">
                  </div>
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">第3期：月数 / 金额</label>
                  <div style="display:flex; gap:6px;">
                    <input aria-label="月"  type="number" id="settle-m3" value="12" style="width:38%;" placeholder="月">
                    <input aria-label="元"  type="number" id="settle-a3" value="500000" style="width:62%;" placeholder="元">
                  </div>
                </div>
              </div>
            </div>

            <!-- 抵债资产子卡片 -->
            <div id="settle-asset-card" style="margin-top: 12px; background: #FAF9F6; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 10px 12px;">
              <div style="font-size: 11.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px; display: flex; justify-content: space-between;">
                <span>🏢 抵债资产穿透参数 (刺破虚假评估价)</span>
                <span style="font-size: 10.5px; color: #DC2626; font-weight: 600;">依法扣除在先顺位与法拍折价</span>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">抵债资产名称</label>
                  <input aria-label="settle asset name"  type="text" id="settle-asset-name" value="朝阳区商办写字楼3套/工抵房">
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">名义评估作价值 (元)</label>
                  <input aria-label="settle asset val"  type="number" id="settle-asset-val" value="4500000" step="50000">
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">在先优先受偿/银行抵押 (元)</label>
                  <input aria-label="settle asset lien"  type="number" id="settle-asset-lien" value="1500000" step="50000">
                </div>
              </div>
              <div class="form-row" style="margin-top: 8px;">
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">法拍预期处置折价率</label>
                  <select aria-label="settle asset disc"  id="settle-asset-disc">
                    <option value="0.70">0.70 (一拍起拍价 · 评估价7折)</option>
                    <option value="0.56">0.56 (二拍起拍价 · 评估价56折)</option>
                    <option value="0.80">0.80 (协议转让折扣率)</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">税费与处置维护成本率</label>
                  <select aria-label="settle asset tax"  id="settle-asset-tax">
                    <option value="0.12">12% (土增/契税/印花及过户中介费)</option>
                    <option value="0.18">18% (高额土增税非住宅商办)</option>
                    <option value="0.08">8% (普通住宅过户简易税费)</option>
                  </select>
                </div>
                <div class="form-group">
                  <label class="form-label" style="font-size: 11px;">预计变现周期 (月)</label>
                  <input aria-label="settle asset months"  type="number" id="settle-asset-months" value="18">
                </div>
              </div>
            </div>

            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runSettlementCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path></svg>
                穿透精算真实净现值(NPV)与生成合伙人和解战术备忘录
              </button>
            </div>
          </div>

          <!-- 子表单 H: 上诉期截止日测算 (《民事诉讼法》第171条) -->
          <div id="calc-pane-appeal" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">裁判文书送达日期</label>
                <input aria-label="appeal service date"  type="date" id="appeal-service-date" value="2026-03-01">
              </div>
              <div class="form-group">
                <label class="form-label">裁判文书类型</label>
                <select aria-label="appeal judgment type"  id="appeal-judgment-type">
                  <option value="judgment">一审判决书（15日，送达次日起算）</option>
                  <option value="ruling">一审裁定书（10日，送达次日起算）</option>
                </select>
              </div>
            </div>
            <div style="margin-top: 18px;">
              <button class="btn" style="width: 100%;" onclick="runAppealCalc()">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>
                测算上诉期截止日（法定节假日自动顺延）
              </button>
            </div>
          </div>

        </div>

        <!-- 右栏：实时公文凭条预览纸 (带有微弱阴影和顶部琥珀金装订线的白纸卡片) -->
        <div class="docket-receipt-paper">
          <div class="receipt-header">
            <div class="receipt-title">
              <span>公文凭条 · 诉讼计算明细</span>
              <span class="badge" id="receipt-type-badge">LPR 逾期利息</span>
            </div>
            <div style="display: flex; align-items: center; gap: 6px;">
              <button class="btn btn-secondary btn-sm" onclick="copyLegalStatement()">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                复制公文段落
              </button>
              <button class="btn btn-secondary btn-sm" id="btn-calc-add-deadline" onclick="addCurrentCalcDeadlineToVault()" style="display:none;" title="将计算结果的法定到期日加入案件期限日历">
                📅 加入案件期限
              </button>
              <button class="btn btn-amber btn-sm" onclick="syncCurrentCalcToCaseContext()" title="将本笔本金、利息与公文段落同步至全局在办案件上下文">
                📥 同步至在办案件
              </button>
            </div>
          </div>

          <!-- 核心金额大字高亮区 (大号琥珀金数字) -->
          <div class="metric-summary-box" id="metric-summary-box">
            <div class="metric-item">
              <span class="metric-label" id="metric-l1">利息总额 (元)</span>
              <span class="metric-value highlight" id="metric-v1">¥ 7,120.26</span>
              <span class="metric-sub" id="metric-s1">大写：人民币柒仟壹佰贰拾元贰角陆分</span>
            </div>
            <div class="metric-item">
              <span class="metric-label" id="metric-l2">本息合计 (元)</span>
              <span class="metric-value" id="metric-v2">¥ 207,120.26</span>
              <span class="metric-sub" id="metric-s2">本金 200,000.00 元</span>
            </div>
            <div class="metric-item">
              <span class="metric-label" id="metric-l3">计息周期</span>
              <span class="metric-value" id="metric-v3">365 天</span>
              <span class="metric-sub" id="metric-s3">2023-01-01 至 2024-01-01</span>
            </div>
          </div>

          <!-- 排版规范公文正文 (衬线字体，真实卷宗质感) -->
          <div>
            <span style="font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; display: block;">
              《计算明细说明（可直接粘贴至起诉状/仲裁申请书）》
            </span>
            <div class="legal-statement-box" id="legal-statement-text">以拖欠款项本金人民币 200,000.00 元为基数，自 2023-01-01 起至 2024-01-01 止，按照同期全国银行间同业拆借中心公布的一年期贷款市场报价利率（LPR）的 1.0 倍标准分段计算逾期违约利息。
计息期间累计逾期 365 天，共计产生利息人民币 7,120.26 元（大写：人民币柒仟壹佰贰拾元贰角陆分），本息合计人民币 207,120.26 元。
分段计息具体明细如下：
  (1) 2023-01-01 至 2023-06-20（共 170 天）：基准LPR 3.65% × 1.0倍 = 执行年化 3.65%，该段利息为人民币 3,400.00 元；
  (2) 2023-06-20 至 2023-08-21（共 62 天）：基准LPR 3.55% × 1.0倍 = 执行年化 3.55%，该段利息为人民币 1,206.03 元；
  (3) 2023-08-21 至 2024-01-01（共 133 天）：基准LPR 3.45% × 1.0倍 = 执行年化 3.45%，该段利息为人民币 2,514.23 元。</div>
          </div>

        </div>

      </div>
    </section>

    <!-- ======================================================================
         模块 02：立案文书流水线 (左表单 + 右公文纸预览)
         ====================================================================== -->
`;

export function renderTabCalc() {
  const el = document.getElementById('tab-calc');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = CALC_TAB_HTML;
  }
}


    // =========================================================================
    
    // 客户端高精度毫秒级人民币大写即时转换算法 (输入零延迟响应)
    function clientConvertRmbCapital(n) {
      if (n === "" || isNaN(n) || Number(n) < 0) return "人民币零元整";
      let num = parseFloat(n);
      if (num === 0) return "人民币零元整";
      if (num > 999999999999.99) return "金额超出计算范围";

      const fraction = ['角', '分'];
      const digit = ['零', '壹', '贰', '叁', '肆', '伍', '陆', '柒', '捌', '玖'];
      const unit = [
        ['元', '万', '亿'],
        ['', '拾', '佰', '仟']
      ];

      const numFixed = Math.round(num * 100);
      const jiao = Math.floor(numFixed / 10) % 10;
      const fen = numFixed % 10;
      let s = '';
      if (jiao === 0 && fen === 0) {
        s = '整';
      } else {
        if (jiao > 0) s += digit[jiao] + '角';
        else if (fen > 0 && Math.floor(num) > 0) s += '零';
        if (fen > 0) s += digit[fen] + '分';
      }

      let integerPart = Math.floor(num);
      let intStr = '';
      for (let i = 0; i < unit[0].length && integerPart > 0; i++) {
        let p = '';
        for (let j = 0; j < unit[1].length && integerPart > 0; j++) {
          p = digit[integerPart % 10] + unit[1][j] + p;
          integerPart = Math.floor(integerPart / 10);
        }
        intStr = p.replace(/(零.)*零$/, '').replace(/^$/, '零') + unit[0][i] + intStr;
      }

      const formatted = (intStr.replace(/(零.)*零元/, '元')
        .replace(/(零.)+/g, '零')
        .replace(/^整$/, '零元整') || '零元') + s;

      return '人民币' + formatted.replace(/^人民币零元整$/, '零元整').replace(/^人民币/, '');
    }

    let rmbDebounceTimer = null;
    function handleRmbInput() {
      const val = document.getElementById('rmb-input').value;
      const textElem = document.getElementById('rmb-result-text');
      if (!val) {
        textElem.innerText = "人民币零元整";
        return;
      }
      // 1. 本地即时响应
      textElem.innerText = clientConvertRmbCapital(val);

      // 2. 防抖校验后端 cn2an 接口，保证 100% 司法标准统一
      clearTimeout(rmbDebounceTimer);
      rmbDebounceTimer = setTimeout(async () => {
        try {
          const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/rmb-capital`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: parseFloat(val) || 0 })
          });
          if (resp.ok) {
            const d = await resp.json();
            textElem.innerText = d.rmb_capital;
          }
        } catch (e) {
          // 降级保持本地结果
        }
      }, 250);
    }

    // 主体资格秒查 (身份证 / 统一社会信用代码二合一)
    let lastSubjectNote = "该当事人已满 66 周岁，达到现行法定退休年龄（60周岁）。依据最高人民法院《关于审理劳动争议案件适用法律问题的解释（一）》第三十二条，双方形成的用工关系按劳务关系处理。";

    function handleSubjectInput(e) {
      const val = document.getElementById('subject-input').value.trim();
      if (val.length === 18) {
        runSubjectValidate();
      }
    }

    async function runSubjectValidate() {
      const val = document.getElementById('subject-input').value.trim().toUpperCase();
      if (!val) {
        showToast("请输入18位身份证号或统一代码");
        return;
      }

      const badge = document.getElementById('subject-result-badge');
      const textEl = document.getElementById('subject-result-text');

      // 智能识别：如果是 18 位且前 6 位是纯数字出生地，且没有包含除末位 X 外的字母 -> 优先按身份证解析
      const isPureDigitsOrTrailingX = /^\d{17}[\dX]$/.test(val);
      // 若第 1 位是 9 或 1 或 5 且含有字母，通常为企业信用代码
      const isUSCC = /^[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}$/.test(val) && (val.startsWith('9') || val.startsWith('1') || val.startsWith('5') || /[A-Z]/.test(val.substring(0, 17)));

      if (isUSCC) {
        // 企业统一社会信用代码校验
        try {
          const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/uscc`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uscc: val })
          });
          const d = await resp.json();
          if (d.valid) {
            badge.className = "live-badge valid";
            textEl.innerText = `代码合法 · ${d.province || '工商'} · ${d.department || '市场监督'}`;
            lastSubjectNote = `企业统一信用代码：${d.uscc}；登记机构：${d.department}；属地：${d.province}；校验状态：合法有效。`;
            showToast("企业代码核验通过");
          } else {
            badge.className = "live-badge warn";
            textEl.innerText = `代码校验异常: ${d.error_message || '无效'}`;
            lastSubjectNote = `企业代码异常：${d.error_message}`;
          }
        } catch (e) {
          showToast("核验请求失败: " + e);
        }
      } else {
        // 个人身份证解析与退休年龄判断
        try {
          const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/idcard`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id_card: val, is_cadre: false })
          });
          const d = await resp.json();
          if (d.valid) {
            if (d.is_retired) {
              badge.className = "live-badge warn";
              textEl.innerText = `${d.age}岁 · ${d.gender} · 已达退休年龄 (劳务关系)`;
            } else {
              badge.className = "live-badge valid";
              textEl.innerText = `${d.age}岁 · ${d.gender} · 未达退休年龄 (劳动关系)`;
            }
            lastSubjectNote = d.retirement_note;
            showToast(`身份解析成功：${d.gender}性 ${d.age}岁`);
          } else {
            badge.className = "live-badge warn";
            textEl.innerText = `校验异常: ${d.error_message || '无效'}`;
            lastSubjectNote = `身份证号校验失败：${d.error_message}`;
          }
        } catch (e) {
          showToast("核验请求失败: " + e);
        }
      }
    }

    function copySubjectNote() {
      copyToClipboard(lastSubjectNote, "已复制主体法律资格说明");
    }

    // =========================================================================
    // 2. 模块 01：左算右稿 (胶囊切换与三个核心计算器)
    // =========================================================================
    let currentCalcMode = 'lpr'; // 'lpr', 'court', 'labor'

    function switchCalcSegment(mode) {
      currentCalcMode = mode;
      document.querySelectorAll('.segmented-btn').forEach(b => b.classList.remove('active'));
      const activeBtn = document.getElementById(`seg-btn-${mode}`);
      if (activeBtn) activeBtn.classList.add('active');

      document.getElementById('calc-pane-lpr').style.display = mode === 'lpr' ? 'block' : 'none';
      document.getElementById('calc-pane-court').style.display = mode === 'court' ? 'block' : 'none';
      document.getElementById('calc-pane-labor').style.display = mode === 'labor' ? 'block' : 'none';
      const paneStatute = document.getElementById('calc-pane-statute');
      if (paneStatute) paneStatute.style.display = mode === 'statute' ? 'block' : 'none';
      const panePreserv = document.getElementById('calc-pane-preserv');
      if (panePreserv) panePreserv.style.display = mode === 'preserv' ? 'block' : 'none';
      const paneValidity = document.getElementById('calc-pane-validity');
      if (paneValidity) paneValidity.style.display = mode === 'validity' ? 'block' : 'none';
      const paneSettlement = document.getElementById('calc-pane-settlement');
      if (paneSettlement) paneSettlement.style.display = mode === 'settlement' ? 'block' : 'none';
      const paneAppeal = document.getElementById('calc-pane-appeal');
      if (paneAppeal) paneAppeal.style.display = mode === 'appeal' ? 'block' : 'none';

      // 调整右侧凭条类型徽章
      const typeBadge = document.getElementById('receipt-type-badge');
      if (mode === 'lpr') {
        typeBadge.innerText = "LPR 逾期利息";
        runLprCalc();
      } else if (mode === 'court') {
        typeBadge.innerText = "诉讼与保全费";
        runCourtFeeCalc();
      } else if (mode === 'labor') {
        typeBadge.innerText = "劳动争议经济补偿";
        runLaborArbitrationCalc();
      } else if (mode === 'statute') {
        typeBadge.innerText = "诉讼时效与除斥期间";
        runStatuteLimitCalc();
      } else if (mode === 'preserv') {
        typeBadge.innerText = "保全续封红线监控";
        runPreservationRenewalCalc();
      } else if (mode === 'validity') {
        typeBadge.innerText = "法条时效有效性核验";
        runStatuteValidityCheck();
      } else if (mode === 'settlement') {
        typeBadge.innerText = "商业和解与以物抵债精算";
        runSettlementCalc();
      } else if (mode === 'appeal') {
        typeBadge.innerText = "上诉期截止日测算";
        runAppealCalc();
      }
    }

    
    // 2.8 上诉期截止日测算
    async function runAppealCalc() {
      const sDateEl = document.getElementById('appeal-service-date');
      const jTypeEl = document.getElementById('appeal-judgment-type');
      const serviceDate = sDateEl ? sDateEl.value : '2026-03-01';
      const judgmentType = jTypeEl ? jTypeEl.value : 'judgment';
      if (!serviceDate) return;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/appeal-deadline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ service_date: serviceDate, judgment_type: judgmentType })
        });
        if (!resp.ok) return;
        const data = await resp.json();
        const rEl = document.getElementById('receipt-container');
        if (!rEl) return;
        rEl.innerHTML = `
          <div style="padding: 16px; background: white; border-radius: 6px; border: 1px solid var(--border-hairline);">
            <div style="display: flex; justify-content: space-between; align-items: baseline; border-bottom: 2px solid var(--primary-navy); padding-bottom: 8px;">
              <h3 style="margin: 0; font-size: 15px; color: var(--primary-navy);">上诉期截止日测算凭条</h3>
              <span style="font-size: 11px; color: var(--text-muted);">${escapeHtml(data.legal_basis || '')}</span>
            </div>
            <div style="margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
              <div style="background: #F8FAFC; padding: 10px; border-radius: 4px;">
                <div style="font-size: 11px; color: var(--text-muted);">送达日期</div>
                <div style="font-size: 14px; font-weight: 700; color: var(--text-primary); margin-top: 4px;">${escapeHtml(data.service_date || '')}</div>
              </div>
              <div style="background: #EFF6FF; padding: 10px; border-radius: 4px; border: 1px solid #BFDBFE;">
                <div style="font-size: 11px; color: #1E40AF;">上诉期届满截止日</div>
                <div style="font-size: 15px; font-weight: 800; color: #1D4ED8; margin-top: 4px;">${escapeHtml(data.deadline || '')} ${data.extended_for_holiday_or_weekend ? '<span style="font-size:10.5px; background:#FEF3C7; color:#92400E; padding:1px 5px; border-radius:8px;">(节假日顺延)</span>' : escapeHtml('')}</div>
              </div>
            </div>
            <div style="margin-top: 12px; font-size: 11.5px; line-height: 1.6; color: var(--text-secondary); background: #FAF9F6; padding: 10px; border-radius: 4px;">
              ${(data.notes || []).map(n => '<div>• ' + escapeHtml(n) + '</div>').join('')}
            </div>
          </div>
        `;
      } catch (err) {
        console.error("runAppealCalc error:", err);
      }
    }

    // 2.1 LPR 逾期利息精算
    async function runLprCalc() {
      const principal = parseFloat(document.getElementById('lpr-p').value) || 0;
      const startDate = document.getElementById('lpr-start').value;
      const endDate = document.getElementById('lpr-end').value;
      const multiplier = parseFloat(document.getElementById('lpr-mult').value) || 1.0;
      const term = document.getElementById('lpr-term').value;
      const filingDate = (document.getElementById('lpr-filing') || {}).value || "";

      try {
        const payload = { principal, start_date: startDate, end_date: endDate, multiplier, term };
        if (filingDate) payload.filing_date = filingDate;
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/lpr-interest`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await resp.json();

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "逾期利息总额 (元)";
        document.getElementById('metric-v1').innerText = `¥ ${d.total_interest.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s1').innerText = `大写：${d.interest_capital}`;

        document.getElementById('metric-l2').innerText = "本息合计 (元)";
        document.getElementById('metric-v2').innerText = `¥ ${d.total_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s2').innerText = `本金 ${d.principal.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元`;

        document.getElementById('metric-l3').innerText = "计息总周期";
        document.getElementById('metric-v3').innerText = `${d.total_days} 天`;
        document.getElementById('metric-s3').innerText = `${d.start_date} 至 ${d.end_date}`;

        // 渲染排版公文
        document.getElementById('legal-statement-text').innerText = d.complaint_statement;
        showToast("LPR 逾期利息与明细公文已更新");
      } catch (e) {
        showToast("LPR 计算失败: " + e);
      }
    }

    // 2.2 诉讼费与保全费核算
    async function runCourtFeeCalc() {
      const amount = parseFloat(document.getElementById('fee-amount').value) || 0;
      const isSummary = document.getElementById('fee-proc').value === 'true';

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/court-fees`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ claim_amount: amount, is_summary_procedure: isSummary, case_type: "财产案件" })
        });
        const d = await resp.json();

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "实际应交受理费";
        document.getElementById('metric-v1').innerText = `¥ ${d.actual_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s1').innerText = `大写：${d.rmb_capital} (${isSummary ? '简易程序减半' : '普通程序全额'})`;

        document.getElementById('metric-l2').innerText = "财产保全申请费";
        document.getElementById('metric-v2').innerText = `¥ ${d.preservation_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s2').innerText = "封顶 5,000.00 元";

        document.getElementById('metric-l3').innerText = "诉讼标的额";
        document.getElementById('metric-v3').innerText = `¥ ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s3').innerText = "依据《诉讼费用交纳办法》第13/14条";

        // 生成公文说明段落
        const statement = `【诉讼费用与保全费用核算说明】
一、案件受理费交纳依据与数额：
本案诉讼请求标的总金额为人民币 ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。
依据国务院《诉讼费用交纳办法》第十三条第一款关于财产案件受理费交纳比例之规定，本案基准案件受理费为人民币 ${d.standard_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。
因本案适用${isSummary ? '简易程序审理（或经人民法院调解达成协议结案），依法减半交纳案件受理费，原告实际预交案件受理费' : '普通程序审理，原告全额交纳案件受理费'}人民币 ${d.actual_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（大写：${d.rmb_capital}）。

二、诉讼财产保全申请费：
依据《诉讼费用交纳办法》第十四条第二款规定，申请财产保全数额为人民币 ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元，依法应向人民法院交纳保全申请费人民币 ${d.preservation_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

以上诉讼费用及保全费用，原告在起诉状中请求判令由被告全额承担。`;

        document.getElementById('legal-statement-text').innerText = statement;
        showToast("诉讼与保全费公文说明已更新");
      } catch (e) {
        showToast("诉讼费核算失败: " + e);
      }
    }

    // 2.3 劳动争议仲裁补偿金 (N / N+1 / 2N)
    async function runLaborArbitrationCalc() {
      const salary = parseFloat(document.getElementById('labor-salary').value) || 0;
      const hireDate = document.getElementById('labor-hire-date').value;
      const termDate = document.getElementById('labor-term-date').value;
      const avgSalary = parseFloat(document.getElementById('labor-avg-salary').value) || null;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/labor-arbitration`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            monthly_salary: salary,
            hire_date: hireDate,
            termination_date: termDate,
            local_avg_salary: avgSalary
          })
        });
        const d = await resp.json();

        const nAmt = d.tiers['N'].amount;
        const np1Amt = d.tiers['N+1'].amount;
        const twoNAmt = d.tiers['2N'].amount;

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "违法解除赔偿金 (2N)";
        document.getElementById('metric-v1').innerText = `¥ ${twoNAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s1').innerText = `大写：${d.tiers['2N'].rmb_capital}`;

        document.getElementById('metric-l2').innerText = "代通知金补偿 (N+1)";
        document.getElementById('metric-v2').innerText = `¥ ${np1Amt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s2').innerText = `经济补偿 N 为 ¥ ${nAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-l3').innerText = "折算工龄计发月数";
        document.getElementById('metric-v3').innerText = `${d.compensation_months} 个月`;
        document.getElementById('metric-s3').innerText = `实际工龄：${d.tenure_str}`;

        // 生成公文说明段落
        const statement = `【劳动人事争议经济补偿与赔偿金精算说明（可写入仲裁申请书）】
一、工龄核定与计发基数：
申请人于 ${d.hire_date} 入职被申请人处，至双方劳动合同解除日 ${d.termination_date} 止，在被申请人处连续工作时间为 ${d.tenure_str}。
依据《中华人民共和国劳动合同法》第四十七条第一款规定，本案计发经济补偿的年限依法核定为 ${d.compensation_months} 个月。
申请人离职前十二个月的月平均工资为人民币 ${d.monthly_salary.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。${d.cap_reason}

二、三档主张请求金额核算：
1. 法定经济补偿金（N）：
   依据《劳动合同法》第四十六条、第四十七条，计算公式为：${d.tiers['N'].formula}；
   金额为：人民币 ${nAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（大写：${d.tiers['N'].rmb_capital}）。
2. 未提前三十日书面通知代通知金补偿（N+1）：
   依据《劳动合同法》第四十条、第四十七条，计算公式为：${d.tiers['N+1'].formula}；
   金额为：人民币 ${np1Amt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（大写：${d.tiers['N+1'].rmb_capital}）。
3. 用人单位违法解除劳动合同赔偿金（2N）：
   依据《劳动合同法》第八十七条“用人单位违反本法规定解除或者终止劳动合同的，应当依照本法第四十七条规定的经济补偿标准的二倍向劳动者支付赔偿金”之规定；
   计算公式为：${d.tiers['2N'].formula}；
   金额为：人民币 ${twoNAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（大写：${d.tiers['2N'].rmb_capital}）。`;

        document.getElementById('legal-statement-text').innerText = statement;
        showToast("仲裁赔偿金 (N/N+1/2N) 公文说明已更新");
      } catch (e) {
        showToast("仲裁补偿金计算失败: " + e);
      }
    }

    // 2.4 诉讼时效与除斥期间精算
    async function runStatuteLimitCalc() {
      const startDate = document.getElementById('statute-start').value;
      const causeType = document.getElementById('statute-type').value;
      const actDate = (document.getElementById('statute-act-date') || {}).value || "";
      const notes = document.getElementById('statute-interrupt-notes').value.trim();
      
      const interruptions = [];
      if (notes) {
        notes.split('\n').forEach(line => {
          const m = line.match(/^(\d{4}-\d{2}-\d{2})\s*(.*)$/);
          if (m) {
            interruptions.push({ date: m[1], description: m[2] || "主张权利或还款承诺" });
          } else if (line.trim()) {
            interruptions.push({ date: "2023-09-15", description: line.trim() });
          }
        });
      }

      try {
        const payload = { start_date: startDate, cause_type: causeType, interruption_events: interruptions };
        if (actDate) payload.act_date = actDate;
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/statute-limitations`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await resp.json();

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "剩余执业安全期";
        document.getElementById('metric-v1').innerText = `${d.days_remaining} 天`;
        document.getElementById('metric-s1').innerText = d.status_label;
        document.getElementById('metric-v1').style.color = d.is_expired ? 'var(--status-warn)' : (d.days_remaining <= 30 ? 'var(--status-warn)' : 'var(--accent-amber)');

        document.getElementById('metric-l2').innerText = "最终届满到期日";
        document.getElementById('metric-v2').innerText = d.final_expire_date;
        document.getElementById('metric-s2').innerText = `起算日：${d.start_date} (历经${d.effective_interruptions_count}次中断)`;

        document.getElementById('metric-l3').innerText = "适用法律规范";
        document.getElementById('metric-v3').innerText = d.is_preclusive ? "除斥期间" : "诉讼时效";
        document.getElementById('metric-s3').innerText = d.legal_basis;

        // 生成公文说明段落
        let statement = `【民事诉讼时效与除斥期间精算核定意见书】\n`;
        statement += `一、适用规则与法定起算点：\n本案权利保护请求属于【${d.rule_name}】，法定依据为 ${d.legal_basis}。\n`;
        statement += `原告知道或者应当知道权利受到损害以及义务人之日为 ${d.start_date}，法定初始届满到期日为 ${d.initial_expire_date}。\n\n`;
        statement += `二、时效推演与中断效力审查：\n`;
        d.timeline_log.forEach(item => {
          statement += `• ${item.date} [${item.action}]：${item.event} -> 到期日顺延至 ${item.expire_date}\n`;
        });
        statement += `\n三、执业风险研判与结论：\n截至基准核算日(${d.calculation_benchmark_today})，距离法定届满期限尚余 ${d.days_remaining} 天。\n`;
        statement += `【风险评级】${d.status_label}：${d.risk_alert}\n`;
        if (d.is_preclusive) {
          statement += `特别警示：本期间性质为除斥期间，依《民法典》第一百九十九条，不适用中止、中断和延长，存续期间届满实体权利消灭！\n`;
        }

        document.getElementById('legal-statement-text').innerText = statement;
        lastCalcDeadline = {
          kind: 'statute_limitation',
          dueDate: d.final_expire_date,
          source: '诉讼时效与除斥期间计算器',
          note: `适用规则: ${d.rule_name} · ${d.legal_basis}`
        };
        const dlBtn = document.getElementById('btn-calc-add-deadline');
        if (dlBtn && d.final_expire_date) dlBtn.style.display = 'inline-flex';
        showToast("诉讼时效推演与风险公文已更新");
      } catch (e) {
        showToast("诉讼时效核算失败: " + e);
      }
    }

    // 2.5 财产保全续查封续冻结红线精算
    async function runPreservationRenewalCalc() {
      const pType = document.getElementById('preserv-type').value;
      const startDate = document.getElementById('preserv-start').value;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/preservation-renewal`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ preservation_type: pType, start_date: startDate })
        });
        const d = await resp.json();

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "续封申请法定截止日";
        document.getElementById('metric-v1').innerText = d.renewal_application_deadline;
        document.getElementById('metric-s1').innerText = `提前 ${d.advance_days_required} 日申请 (保全到期日: ${d.expire_date})`;
        document.getElementById('metric-v1').style.color = (d.days_to_renewal_deadline <= 15) ? 'var(--status-warn)' : 'var(--accent-amber)';

        document.getElementById('metric-l2').innerText = "距续封截止剩余";
        document.getElementById('metric-v2').innerText = `${d.days_to_renewal_deadline} 天`;
        document.getElementById('metric-s2').innerText = d.status_label;

        document.getElementById('metric-l3').innerText = "保全标的类别";
        document.getElementById('metric-v3').innerText = d.type_name.split(' ')[0];
        document.getElementById('metric-s3').innerText = d.statute_basis;

        // 生成公文说明段落
        let statement = `【财产保全续查封/续冻结执业红线监控说明】\n`;
        statement += `一、首封/冻结裁定信息与期限：\n标的类别：${d.type_name}；\n首封裁定生效日：${d.start_date}；保全自然到期日：${d.expire_date}。\n`;
        statement += `法定依据：${d.statute_basis}（${d.statute_description}）。\n\n`;
        statement += `二、续封法定期限与红线警示：\n依据最高法保全规定第十八条，申请续行财产保全应当在保全期限届满前 ${d.advance_days_required} 日内向执行或审判业务庭提交申请书。\n`;
        statement += `【续封申请截止日】必须在 ${d.renewal_application_deadline} 前完成向法院递交与立案签收！\n`;
        statement += `距离申请截止日仅剩 ${d.days_to_renewal_deadline} 天。\n\n`;
        statement += `三、执业风险提示：\n${d.alert_message}\n`;

        document.getElementById('legal-statement-text').innerText = statement;
        lastCalcDeadline = {
          kind: 'preservation_renewal',
          dueDate: d.renewal_application_deadline,
          source: '财产保全续行期限计算器',
          note: `标的: ${d.type_name} · ${d.statute_basis}`
        };
        const dlBtn = document.getElementById('btn-calc-add-deadline');
        if (dlBtn && d.renewal_application_deadline) dlBtn.style.display = 'inline-flex';
        showToast("保全续封红线公文已更新");
      } catch (e) {
        showToast("保全续封核算失败: " + e);
      }
    }

    // 2.6 规范性法律文件现行有效性与废止拦截核验
    async function runStatuteValidityCheck() {
      const citation = document.getElementById('validity-citation').value.trim();
      const incidentDate = document.getElementById('validity-incident-date').value;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/statute-validity`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ citation_text: citation, incident_date: incidentDate })
        });
        const d = await resp.json();

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "法规有效性状态";
        document.getElementById('metric-v1').innerText = d.is_safe ? "现行有效" : "已废止/瑕疵";
        document.getElementById('metric-v1').style.color = d.is_safe ? 'var(--status-valid)' : 'var(--status-warn)';
        document.getElementById('metric-s1').innerText = d.summary;

        document.getElementById('metric-l2').innerText = "检测到的废止法规";
        document.getElementById('metric-v2').innerText = `${d.detected_abrogated.length} 部`;
        document.getElementById('metric-s2').innerText = d.detected_abrogated.length > 0 ? d.detected_abrogated.map(x=>x.full_name).join(', ') : "无废止风险";

        document.getElementById('metric-l3').innerText = "法律事实基准日";
        document.getElementById('metric-v3').innerText = d.incident_date || "未指定";
        document.getElementById('metric-s3').innerText = "用于新旧法时间效力判定";

        // 生成公文说明段落
        let statement = `【规范性法律文件现行有效性与时间效力核验意见】\n`;
        statement += `待核验文本：『${d.query_citation}』\n核验判定：${d.summary}\n\n`;
        if (d.detected_abrogated.length > 0) {
          statement += `一、检测到援引已废止法规明细：\n`;
          d.detected_abrogated.forEach((item, idx) => {
            statement += `  (${idx+1}) ${item.full_name}：已于 ${item.abrogated_date} 起废止！\n`;
            statement += `      替换现行规范：${item.replaced_by}\n`;
            statement += `      执业风险防范：${item.risk_tip}\n`;
          });
          statement += `\n二、民法典时间效力适用意见：\n${d.time_validity_note}\n`;
        } else {
          statement += `一、现行法规检验通过：\n所援引之条文在现行有效的国家法律规范库中，未发现直接废止风险。\n`;
          if (d.detected_valid.length > 0) {
            d.detected_valid.forEach(v => {
              statement += `• ${v.full_name}（${v.status}，施行日期：${v.effective_date}）\n`;
            });
          }
        }

        document.getElementById('legal-statement-text').innerText = statement;
        showToast("法规现行有效性探针已完成检测");
      } catch (e) {
        showToast("法规有效性核验失败: " + e);
      }
    }

    // 2.7 商业诉讼和解与以物抵债现值/真实回收率精算 (Settlement NPV Simulator)
    function toggleSettlementPlanUI() {
      const t = document.getElementById('settle-type').value;
      const cashCard = document.getElementById('settle-cash-card');
      const assetCard = document.getElementById('settle-asset-card');
      if (cashCard) cashCard.style.display = (t === 'debt_for_asset') ? 'none' : 'block';
      if (assetCard) assetCard.style.display = (t === 'cash_installments') ? 'none' : 'block';
    }

    async function runSettlementCalc() {
      const claim = parseFloat(document.getElementById('settle-claim').value) || 5000000;
      const rate = (parseFloat(document.getElementById('settle-rate').value) || 8.0) / 100.0;
      const planType = document.getElementById('settle-type').value;

      const installments = [];
      if (planType !== 'debt_for_asset') {
        const m1 = parseInt(document.getElementById('settle-m1').value) || 3;
        const a1 = parseFloat(document.getElementById('settle-a1').value) || 0;
        const m2 = parseInt(document.getElementById('settle-m2').value) || 6;
        const a2 = parseFloat(document.getElementById('settle-a2').value) || 0;
        const m3 = parseInt(document.getElementById('settle-m3').value) || 12;
        const a3 = parseFloat(document.getElementById('settle-a3').value) || 0;
        if (a1 > 0) installments.push({ months: m1, amount: a1, note: "第 1 期分期款" });
        if (a2 > 0) installments.push({ months: m2, amount: a2, note: "第 2 期分期款" });
        if (a3 > 0) installments.push({ months: m3, amount: a3, note: "第 3 期分期款" });
      }

      const assetPlan = {
        asset_name: document.getElementById('settle-asset-name').value || "抵债资产",
        nominal_asset_valuation: parseFloat(document.getElementById('settle-asset-val').value) || 0,
        prior_liens: parseFloat(document.getElementById('settle-asset-lien').value) || 0,
        auction_discount_rate: parseFloat(document.getElementById('settle-asset-disc').value) || 0.70,
        liquidation_costs_rate: parseFloat(document.getElementById('settle-asset-tax').value) || 0.12,
        time_to_liquidate_months: parseInt(document.getElementById('settle-asset-months').value) || 18,
        encumbrance_status: "在先权利负担核验"
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/settlement-simulation`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            total_claim_nominal: claim,
            plan_type: planType,
            annual_discount_rate: rate,
            installments: installments,
            asset_plan: assetPlan
          })
        });
        const d = await resp.json();
        const m = d.metrics;

        // 渲染大号指标
        document.getElementById('metric-l1').innerText = "真实可收回净现值 (NPV)";
        document.getElementById('metric-v1').innerText = `¥ ${m.total_npv_settlement.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-v1').style.color = (m.effective_recovery_rate < 60) ? 'var(--status-warn)' : 'var(--accent-amber)';
        document.getElementById('metric-s1').innerText = `实质回收率 ${m.effective_recovery_rate}% · 名义清偿 ¥${m.total_nominal_settlement.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-l2').innerText = "虚胖差额 / 实质让利";
        document.getElementById('metric-v2').innerText = `虚胖 ${m.illusion_gap}% / 缩水 ${m.economic_haircut_rate}%`;
        document.getElementById('metric-s2').innerText = `现金现值 ¥${m.cash_npv_total.toLocaleString('zh-CN', {minimumFractionDigits: 2})} · 抵债残值 ¥${m.asset_npv_total.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-l3').innerText = "诉讼债权标的总额";
        document.getElementById('metric-v3').innerText = `¥ ${m.total_claim_nominal.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;
        document.getElementById('metric-s3').innerText = `折现率 ${(d.annual_discount_rate*100).toFixed(1)}% · 处置变现 ${d.asset_breakdown ? (d.asset_breakdown.liquidation_period_months || 0) : 0} 个月`;

        // 渲染合伙人谈判备忘录
        document.getElementById('legal-statement-text').innerText = d.partner_tactical_memo;
        showToast("商业和解与以物抵债现值精算已完成");
      } catch (e) {
        showToast("和解测算失败: " + e);
      }
    }


    function addCurrentCalcDeadlineToVault() {
      if (!lastCalcDeadline) {
        showToast("暂无计算完成的期限结果！");
        return;
      }
      addCalculatorDeadlineToVault(
        lastCalcDeadline.kind,
        lastCalcDeadline.dueDate,
        lastCalcDeadline.source,
        lastCalcDeadline.note
      );
    }

    function addAppealDeadlineToVault() {
      if (!lastAppealDeadline) {
        showToast("上诉期截止日未计算，请先输入送达日期！");
        return;
      }
      addCalculatorDeadlineToVault('appeal', lastAppealDeadline, '上诉期计算器', '一审判决送达后上诉期');
    }

    async function addCalculatorDeadlineToVault(kind, dueDate, sourceName, note) {
      if (!activeMatterId) {
        showToast("请先在 07 案件空间选择或激活一个案件！");
        return;
      }
      if (!dueDate || dueDate.includes("待填写")) {
        showToast("截止日期尚未计算生成，无法加入期限！");
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/vault/deadlines`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            matter_id: activeMatterId,
            kind: kind,
            due_date: dueDate,
            source: sourceName,
            note: note || ""
          })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const res = await resp.json();
        showToast(`已成功将【${sourceName}】(${dueDate}) 加入当前案件期限日历！`);
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function openAddDeadlineModal() {
      const modal = document.getElementById('modal-add-deadline');
      if (modal) modal.classList.add('active');
    }

    function closeAddDeadlineModal() {
      const modal = document.getElementById('modal-add-deadline');
      if (modal) modal.classList.remove('active');
    }

    function handleAddDeadlineBackdropClick(e) {
      if (e.target.id === 'modal-add-deadline') closeAddDeadlineModal();
    }

    function onDeadlineKindChange() {
      const kind = document.getElementById('new-deadline-kind')?.value;
      const tip = document.getElementById('deadline-kind-tip');
      if (tip) {
        tip.style.display = (kind === 'enforcement_application') ? 'block' : 'none';
      }
    }

    async function submitManualDeadline() {
      if (!activeMatterId) {
        showToast("请先在上方切换或选择一个案件空间！");
        return;
      }
      const kind = document.getElementById('new-deadline-kind')?.value || 'custom';
      const date = document.getElementById('new-deadline-date')?.value;
      const source = document.getElementById('new-deadline-source')?.value.trim() || '律师手工录入';
      const note = document.getElementById('new-deadline-note')?.value.trim() || '';
      if (!date) {
        showToast("请选择截止日期！");


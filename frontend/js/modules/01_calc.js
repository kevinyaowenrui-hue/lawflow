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

            <input aria-label="人民币大写实时转换金额"  type="number" id="rmb-input" class="quick-input" value="" step="0.01" placeholder="输入本案金额" oninput="handleRmbInput()">

            <div role="button" tabindex="0"  class="live-badge amber" id="rmb-result-badge" title="点击复制标准大写金额" onclick="copyBadgeText('rmb-result-badge', '已复制大写金额')">

              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>

              <span id="rmb-result-text">填写金额后显示大写</span>

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

            <input aria-label="主体资格核验（身份证或统一社会信用代码）"  type="text" id="subject-input" class="quick-input" value="" maxlength="18" placeholder="粘贴18位身份证号或企业统一信用代码" oninput="handleSubjectInput(event)" onkeydown="if(event.key==='Enter') runSubjectValidate()">

            <button class="btn btn-secondary btn-sm" onclick="runSubjectValidate()">核验</button>

            <div role="button" tabindex="0"  class="live-badge" id="subject-result-badge" title="点击复制定性说明" onclick="copySubjectNote()">

              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>

              <span id="subject-result-text">女性请先选岗位。选定岗位后才显示法定退休时间</span>

            </div>

          </div>

          <div style="display:flex; gap:14px; margin-top:6px; font-size:12px; color:var(--text-secondary);">

            <span>女性岗位（须律师选择，身份证不能推出）</span>
            <label><input type="radio" name="subject-female-post" id="subject-post-cadre" value="cadre" aria-label="女性管理或技术岗位，按原55周岁测算"> 管理/技术</label>
            <label><input type="radio" name="subject-female-post" id="subject-post-worker" value="worker" aria-label="女性工人岗位，按原50周岁测算"> 工人</label>

            <label><input type="checkbox" id="subject-pension" aria-label="已依法享受养老保险待遇或领取退休金"> 已依法享受养老保险待遇或领取退休金</label>

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
              <button class="segmented-btn" id="seg-btn-defense" onclick="switchCalcSegment('defense')">答辩期</button>
              <button class="segmented-btn" id="seg-btn-evidence" onclick="switchCalcSegment('evidence')">举证期限</button>

              <button class="segmented-btn" id="seg-btn-enforce" onclick="switchCalcSegment('enforce')">执行申请期限</button>

              <button class="segmented-btn" id="seg-btn-delay" onclick="switchCalcSegment('delay')">迟延利息与违约金</button>

            </div>

          </div>



          <!-- 子表单 A: LPR 逾期利息精算 -->

          <div id="calc-pane-lpr" class="calc-sub-pane">

            <div class="form-row">

              <div class="form-group">

                <label class="form-label" for="lpr-p">拖欠本金 (元)</label>

                <input aria-label="lpr p"  type="number" id="lpr-p" value="" step="1000" placeholder="本案本金" oninput="hideCalcSyncEmptyNoticeIfFilled()">

              </div>

              <div class="form-group">

                <label class="form-label" id="lpr-start-label" for="lpr-start">起息日</label>

                <input aria-label="lpr start"  type="date" id="lpr-start" value="" oninput="hideCalcSyncEmptyNoticeIfFilled()">

              </div>

              <div class="form-group">

                <label class="form-label" for="lpr-end">截止日</label>

                <input aria-label="lpr end"  type="date" id="lpr-end" value="" oninput="hideCalcSyncEmptyNoticeIfFilled()">

              </div>

            </div>



            <div class="form-row" style="margin-top: 14px;">

              <div class="form-group">

                <label class="form-label">计息规则</label>

                <select aria-label="计息规则" id="lpr-rule" onchange="onLprRuleChange()">

                  <option value="commercial_floating">合同约定按 LPR 或基准利率浮动</option>

                  <option value="sales_fixed_lpr_markup">买卖合同未约定逾期付款违约金（违约日利率加计，整段固定）</option>

                  <option value="private_lending_cap">民间借贷司法保护上限</option>

                </select>

              </div>

              <div class="form-group" id="lpr-mult-wrap">

                <label class="form-label">约定倍数（随报价调整，不是买卖合同法定加计）</label>

                <select aria-label="lpr mult"  id="lpr-mult">

                  <option value="1.0">1.0 倍（同期报价或基准利率）</option>

                  <option value="1.5">1.5 倍（合同约定按 1.5 倍浮动）</option>

                </select>

              </div>

              <div class="form-group" id="lpr-term-wrap">

                <label class="form-label">利率期限品种</label>

                <select aria-label="LPR利率期限品种（1年期/5年期以上）"  id="lpr-term">

                  <option value="1Y">一年期（一年以内贷款）</option>

                  <option value="5Y">五年期以上</option>

                </select>

              </div>

              <div class="form-group" id="lpr-markup-wrap" style="display:none;">

                <label class="form-label">加计比例（法院在 30% 至 50% 内确定，这里选主张口径）</label>

                <select aria-label="买卖合同加计比例" id="lpr-markup">

                  <option value="0.3">加计 30%</option>

                  <option value="0.4">加计 40%</option>

                  <option value="0.5" selected>加计 50%</option>

                </select>

              </div>

            </div>



            <div class="form-row" id="lpr-private-row" style="margin-top: 14px; display:none;">

              <div class="form-group" id="lpr-contract-wrap">

                <label class="form-label">借款合同成立日</label>

                <input aria-label="lpr contract" type="date" id="lpr-contract" value="">

              </div>

              <div class="form-group" id="lpr-filing-wrap">

                <label class="form-label">起诉日期（合同成立于 2020-08-20 前时必填）</label>

                <input aria-label="lpr filing" type="date" id="lpr-filing" value="">

              </div>

              <div class="form-group" id="lpr-agreed-wrap">

                <label class="form-label">约定年利率 %（借期和逾期都没约定时留空，按当时一年期 LPR，不是四倍）</label>

                <input aria-label="约定年利率" type="number" id="lpr-agreed" value="" min="0" max="36" step="0.01" placeholder="例如 24">

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

                <input aria-label="fee amount"  type="number" id="fee-amount" value="" step="5000" placeholder="本案标的">

              </div>

              <div class="form-group">

                <label class="form-label">案件类型</label>

                <select aria-label="案件类型" id="fee-case-type" onchange="toggleCourtFeeExtras()">

                  <option value="property">财产案件受理费</option>

                  <option value="divorce">离婚案件受理费</option>

                  <option value="labor">向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项</option>

                  <option value="personality">人格权案件受理费</option>

                  <option value="execution">申请执行费</option>

                  <option value="payment_order">支付令申请费（受理费三分之一）</option>

                  <option value="public_summons">公示催告（每件100元）</option>

                  <option value="arbitration_revoke">撤销仲裁裁决或认定仲裁协议效力（每件400元）</option>

                </select>

              </div>

            </div>

            <div class="form-row" id="fee-extra-row" style="margin-top: 10px;">

              <div class="form-group" id="fee-divorce-wrap" style="display:none;">

                <label class="form-label">离婚案件每件基础收费（50—300元）</label>

                <input aria-label="离婚基础收费" type="number" id="fee-divorce-base" value="100" min="50" max="300" step="10">

              </div>

              <div class="form-group" id="fee-personality-wrap" style="display:none;">

                <label class="form-label">人格权案件每件基础收费（100—500元）</label>

                <input aria-label="人格权基础收费" type="number" id="fee-personality-base" value="300" min="100" max="500" step="50">

              </div>

              <div class="form-group" id="fee-execution-wrap" style="display:none;">

                <label class="form-label">没有执行金额时的申请费（50—500元）</label>

                <input aria-label="无金额执行申请费" type="number" id="fee-execution-flat" value="50" min="50" max="500" step="10">

              </div>

            </div>

            <div id="fee-acceptance-flags" style="margin-top: 10px; font-size: 12px; color: var(--text-secondary); display: flex; flex-direction: column; gap: 6px;">

              <label><input type="checkbox" id="fee-summary" aria-label="简易程序结案减半"> 简易程序（第16条结案减半，属退费口径；未确定适用时立案仍预交全额）</label>

              <label><input type="checkbox" id="fee-mediation" aria-label="调解结案或撤诉减半"> 调解结案或撤诉（第15条结案减半，属退费口径；立案仍预交全额）</label>

              <label><input type="checkbox" id="fee-counterclaim" aria-label="反诉合并审理减半"> 反诉且法院决定合并审理（分别减半；未合并审理不要按减半预交）</label>

            </div>

            <div class="form-row" style="margin-top: 10px;">

              <div class="form-group" style="flex: 1;">

                <label class="form-label">财产保全申请标的金额 (元，选填)</label>

                <input aria-label="preservation amount" type="number" id="fee-preserv-amount" placeholder="留空则不计保全费和诉责险" step="5000">

                <span style="font-size: 11px; color: var(--text-muted); margin-top: 4px; display: block;">

                  诉责险市场参考费率 0.08%~0.15%，起保最低收费 500 元（法释〔2016〕22号第七条）

                </span>

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

                <input aria-label="labor salary"  type="number" id="labor-salary" value="" step="500" placeholder="本案月工资">

              </div>

              <div class="form-group">

                <label class="form-label">当地职工月平均工资（手填，用于三倍封顶）</label>

                <input aria-label="当地职工月平均工资" type="number" id="labor-avg-salary" value="" placeholder="留空则不封顶。不要用未核验的省份估算">

              </div>

            </div>



            <div class="form-row" style="margin-top: 14px;">

              <div class="form-group">

                <label class="form-label">入职日期</label>

                <input aria-label="实际入职起算日期"  type="date" id="labor-hire-date" value="">

              </div>

              <div class="form-group">

                <label class="form-label">解除劳动关系日期</label>

                <input aria-label="labor term date"  type="date" id="labor-term-date" value="">

              </div>

            </div>



            <div class="form-row" style="margin-top: 14px;">

              <div class="form-group">

                <label class="form-label">解除事由</label>

                <select aria-label="解除事由" id="labor-reason">

                  <option value="">未选择（不计代通知金）</option>

                  <option value="employer_dismissal_with_notice">第四十条解除（无过失性辞退）</option>

                  <option value="unlawful_dismissal">违法解除（最终请求为 2N）</option>

                  <option value="mutual_agreement">协商一致解除</option>

                  <option value="expiry_termination">劳动合同到期终止</option>

                  <option value="employee_resign_employer_fault">劳动者因用人单位过错解除</option>

                </select>

              </div>

              <div class="form-group">

                <label class="form-label">提前三十日书面通知</label>

                <select aria-label="是否提前三十日通知" id="labor-notice">

                  <option value="false">未提前三十日通知</option>

                  <option value="true">已经提前三十日书面通知</option>

                </select>

              </div>

            </div>

            <p style="font-size:12px; color:var(--text-secondary); margin-top:8px;">代通知金只在第四十条且未提前三十日通知时计入。N、N+1、2N 不能相加，也不能同时作为最终请求。</p>

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

                <input aria-label="statute start"  type="date" id="statute-start" value="">

              </div>

              <div class="form-group">

                <label class="form-label">诉讼时效/除斥期间法定类型</label>

                <select aria-label="statute type"  id="statute-type" onchange="toggleLaborStatuteFields()">

                  <option value="general_3y">普通民事诉讼时效（3年，民法典第188条）</option>

                  <option value="labor_arbitration_1y">劳动争议申请仲裁时效（1年，调解仲裁法第二十七条，不是民事诉讼三年）</option>

                  <option value="intl_trade_4y">国际买卖与技术进出口争议（4年，民法典第594条）</option>

                  <option value="cancel_mistake_90d">重大误解撤销权（90日）</option>

                  <option value="cancel_right_1y">欺诈/显失公平撤销权（1年，不适用中断）</option>

                  <option value="construction_priority_18m">建工价款优先受偿权除斥期间（18个月）</option>

                  <option value="guarantee_general_6m">一般保证期间（没有约定时6个月，须起诉主债务人）</option>

                  <option value="guarantee_joint_6m">连带保证期间（没有约定时6个月，须向保证人主张）</option>

                  <option value="cancel_duress_1y">胁迫终止之日起撤销权（1年）</option>

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

              <textarea aria-label="例如：2023-09-15 借款人在微信中回复宽限两个月并承诺付息&#10;2024-03-10 发送EMS律师催告函签收"  id="statute-interrupt-notes" rows="2" placeholder="例如：2023-09-15 借款人在微信中回复宽限两个月并承诺付息&#10;2024-03-10 发送EMS律师催告函签收"></textarea>

            </div>

            <div id="labor-statute-fields" style="display:none; margin-top:12px;">
              <label style="display:flex; gap:6px; font-size:12px; margin-bottom:6px;"><input type="checkbox" id="statute-employment-ongoing">劳动关系仍在存续</label>
              <label style="display:flex; gap:6px; font-size:12px; margin-bottom:6px;"><input type="checkbox" id="statute-wage-arrears">请求的是劳动报酬</label>
              <label class="form-label">劳动关系结束日（报酬争议在离职后从这天起算一年）</label>
              <input aria-label="劳动关系结束日" type="date" id="statute-employment-end" class="quick-input">
              <p style="font-size:12px; color:var(--text-muted);">在职期间拖欠劳动报酬不按一年届满，也不改按三年。离职后的报酬从劳动关系终止日起算一年。中断从中断时起重新计算一年。</p>
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

                <input aria-label="preserv start"  type="date" id="preserv-start" value="">

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

                <input aria-label="输入法规名称或条款，如《合同法》《民法通则》《物权法》"  type="text" id="validity-citation" value="" placeholder="粘贴文书里的法条，例如《合同法》第一百零七条">

              </div>

              <div class="form-group">

                <label class="form-label">争议法律事实发生日期 (用于时间效力判定)</label>

                <input aria-label="validity incident date"  type="date" id="validity-incident-date" value="">

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

                <input aria-label="settle claim"  type="number" id="settle-claim" value="" step="50000" placeholder="本案债权">

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

                    <input aria-label="元"  type="number" id="settle-a1" value="" style="width:62%;" placeholder="元">

                  </div>

                </div>

                <div class="form-group">

                  <label class="form-label" style="font-size: 11px;">第2期：月数 / 金额</label>

                  <div style="display:flex; gap:6px;">

                    <input aria-label="月"  type="number" id="settle-m2" value="6" style="width:38%;" placeholder="月">

                    <input aria-label="元"  type="number" id="settle-a2" value="" style="width:62%;" placeholder="元">

                  </div>

                </div>

                <div class="form-group">

                  <label class="form-label" style="font-size: 11px;">第3期：月数 / 金额</label>

                  <div style="display:flex; gap:6px;">

                    <input aria-label="月"  type="number" id="settle-m3" value="12" style="width:38%;" placeholder="月">

                    <input aria-label="元"  type="number" id="settle-a3" value="" style="width:62%;" placeholder="元">

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

                  <input aria-label="settle asset name"  type="text" id="settle-asset-name" value="" placeholder="抵债资产名称">

                </div>

                <div class="form-group">

                  <label class="form-label" style="font-size: 11px;">名义评估作价值 (元)</label>

                  <input aria-label="settle asset val"  type="number" id="settle-asset-val" value="" step="50000" placeholder="评估价">

                </div>

                <div class="form-group">

                  <label class="form-label" style="font-size: 11px;">在先优先受偿/银行抵押 (元)</label>

                  <input aria-label="settle asset lien"  type="number" id="settle-asset-lien" value="" step="50000" placeholder="优先债权">

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

                <input aria-label="appeal service date"  type="date" id="appeal-service-date" value="">

              </div>

              <div class="form-group">

                <label class="form-label">裁判文书类型</label>

                <select aria-label="appeal judgment type"  id="appeal-judgment-type">

                  <option value="judgment">一审判决书（15日，送达次日起算）</option>

                  <option value="ruling">一审裁定书（10日，送达次日起算）</option>

                  <option value="worker_final_15">劳动者不服劳动终局裁决起诉（15日，用人单位不能用这一项）</option>

                  <option value="either_party_nonfinal_15">当事人不服非终局劳动裁决起诉（15日）</option>

                  <option value="employer_revoke_30">用人单位申请撤销劳动终局裁决（30日，不是15日起诉）</option>

                  <option value="arbitration_set_aside">申请撤销商事仲裁裁决（三个月，不要按六个月）</option>

                </select>

              </div>

            </div>
            <label style="display:flex; align-items:flex-start; gap:6px; font-size:12px; margin:8px 0; line-height:1.5;">
              <input aria-label="域外没有住所" type="checkbox" id="appeal-no-domicile">
              <span>当事人在中华人民共和国领域内没有住所。判决和裁定的上诉期都是三十日（《民事诉讼法》第二百八十六条），不要按十五日或十日。</span>
            </label>

            <div style="margin-top: 18px;">

              <button class="btn" style="width: 100%;" onclick="runAppealCalc()">

                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 16 14"></polyline></svg>

                测算上诉期截止日（法定节假日自动顺延）

              </button>

            </div>

          </div>

          <div id="calc-pane-defense" class="calc-sub-pane" style="display: none;">
            <div class="form-group">
              <label class="form-label">收到起诉状副本之日</label>
              <input aria-label="答辩期起算日" type="date" id="defense-service-date" class="quick-input">
            </div>
            <p style="font-size:12px; color:var(--text-muted); line-height:1.5;">《民事诉讼法》（2023修正）第一百二十八条：收到副本之日起十五日。收到当日不计入。届满日遇法定休假日顺延。公告送达以法院通知为准。</p>
            <button class="btn" style="width:100%;" onclick="runDefenseDeadlineCalc()">测算答辩期届满日</button>
          </div>

          <div id="calc-pane-evidence" class="calc-sub-pane" style="display: none;">
            <div class="form-row">
              <div class="form-group">
                <label class="form-label">测算类型</label>
                <select aria-label="举证期限类型" id="evidence-period-mode" class="quick-input">
                  <option value="first_ordinary_minimum">一审普通程序下限（十五日，不是法院指定日）</option>
                  <option value="second_new_evidence_minimum">二审新证据下限（十日，不是法院指定日）</option>
                  <option value="court_designated">法院已经指定的天数</option>
                  <option value="notice_due_date">通知书已经写明届满日（原样录入，不换算、不改成十五日）</option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">起算日</label>
                <input aria-label="举证期限起算日" type="date" id="evidence-anchor-date" class="quick-input">
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">法院指定天数（只在第三项填写）</label>
              <input aria-label="举证天数" type="number" id="evidence-period-days" class="quick-input" min="1" placeholder="例如 15">
            </div>
            <p style="font-size:12px; color:var(--text-muted); line-height:1.5;">依据《民事诉讼法解释》（2022年修正）第九十九条。下限结果不能覆盖法院通知上已经写明的届满日。通知写了具体日期的，选「通知书已经写明届满日」，把那个日期填进起算日，系统只记录、不重算。</p>
            <button class="btn" style="width:100%;" onclick="runEvidencePeriodCalc()">测算举证期限</button>
          </div>



          <div id="calc-pane-enforce" class="calc-sub-pane" style="display: none;">

            <div class="form-row">

              <div class="form-group">

                <label class="form-label">起算类型（《民事诉讼法》第二百五十条）</label>

                <select aria-label="执行申请起算类型" id="enf-calc-anchor-type" onchange="toggleEnforcementDays()">

                  <option value="performance_last_day">履行期间的最后一日</option>

                  <option value="last_installment">最后一期履行期限届满之日</option>

                  <option value="effective_date">未规定履行期间，自法律文书生效之日</option>

                  <option value="effective_plus_days">生效之日起若干日内履行</option>

                </select>

              </div>

              <div class="form-group">

                <label class="form-label">起算日期</label>

                <input aria-label="执行申请起算日期" type="date" id="enf-calc-anchor-date" value="">

              </div>

              <div class="form-group" id="enf-calc-days-wrap" style="display:none;">

                <label class="form-label">履行天数</label>

                <input aria-label="履行天数" type="number" id="enf-calc-performance-days" value="10" min="0" step="1">

              </div>

            </div>

            <p style="font-size:12px; color:var(--text-secondary); margin-top:8px;">申请执行期间为二年。开始的当日不计入。届满日遇法定休假日或未调休的周六、周日顺延。分期履行从最后一期届满日起算。中止、中断须另按诉讼时效处理，这里不算进去。</p>

            <div style="margin-top: 18px;">

              <button class="btn" style="width: 100%;" onclick="runEnforcementDeadlineCalc()">

                测算申请执行期间届满日

              </button>

            </div>

          </div>



          <div id="calc-pane-delay" class="calc-sub-pane" style="display: none;">

            <p style="font-size:12px; color:var(--text-secondary);">加倍部分按日万分之一点七五。只填履行期间届满日和清偿日。一般债务利息另计。分期履行要每一期单独算。</p>

            <div class="form-row">

              <div class="form-group">

                <label class="form-label">尚未清偿的金钱债务（不含一般债务利息）</label>

                <input aria-label="未清偿本金" type="number" id="delay-principal" value="" step="1000" placeholder="本案未清偿本金">

              </div>

              <div class="form-group">

                <label class="form-label">履行期间届满日（当日不计入）</label>

                <input aria-label="履行期间届满日" type="date" id="delay-start" value="">

              </div>

              <div class="form-group">

                <label class="form-label">清偿日或测算截止日（当日计入）</label>

                <input aria-label="清偿日" type="date" id="delay-end" value="">

              </div>

            </div>

            <div style="margin-top: 12px;">

              <button class="btn" style="width: 100%;" onclick="runDelayInterestCalc()">核算加倍部分债务利息</button>

            </div>

            <div class="form-row" style="margin-top: 16px;">

              <div class="form-group">

                <label class="form-label">约定违约金</label>

                <input aria-label="约定违约金" type="number" id="penalty-agreed" value="" step="1000" placeholder="约定违约金">

              </div>

              <div class="form-group">

                <label class="form-label">造成的损失</label>

                <input aria-label="实际损失" type="number" id="penalty-loss" value="" step="1000" placeholder="实际损失">

              </div>

            </div>

            <div style="margin-top: 12px;">

              <button class="btn btn-secondary" style="width: 100%;" onclick="runPenaltyAdjustCalc()">对照损失百分之三十（只判断是否过分高于）</button>

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

          <div id="calc-sync-empty-notice" role="status" hidden style="display:none; margin: 8px 0 0; padding: 8px 10px; background: #FEF3C7; color: #92400E; border: 1px solid #FDE68A; border-radius: 4px; font-size: 12px;">
            还没有可同步的计算结果
            <button type="button" onclick="dismissCalcSyncEmptyNotice()" style="margin-left: 8px;">关闭</button>
          </div>



          <!-- 核心金额大字高亮区 (大号琥珀金数字) -->

          <div class="metric-summary-box" id="metric-summary-box">

            <div class="metric-item">

              <span class="metric-label" id="metric-l1">利息总额 (元)</span>

              <span class="metric-value highlight" id="metric-v1">—</span>

              <span class="metric-sub" id="metric-s1">填写本案数字后才会计算</span>

            </div>

            <div class="metric-item">

              <span class="metric-label" id="metric-l2">本息合计 (元)</span>

              <span class="metric-value" id="metric-v2">—</span>

              <span class="metric-sub" id="metric-s2">尚未计算</span>

            </div>

            <div class="metric-item">

              <span class="metric-label" id="metric-l3">计息周期</span>

              <span class="metric-value" id="metric-v3">—</span>

              <span class="metric-sub" id="metric-s3">尚未计算</span>

            </div>

            <div class="metric-item" id="metric-item-4" style="display: none;">

              <span class="metric-label" id="metric-l4">诉责险市场参考成本</span>

              <span class="metric-value highlight" id="metric-v4">¥ 500.00 ~ ¥ 750.00</span>

              <span class="metric-sub" id="metric-s4">费率 0.08%~0.15% (起保 500 元)</span>

            </div>

          </div>



          <!-- 排版规范公文正文 (衬线字体，真实卷宗质感) -->

          <div>

            <span style="font-size: 12px; font-weight: 600; color: var(--text-secondary); margin-bottom: 6px; display: block;">

              《计算明细说明（可直接粘贴至起诉状/仲裁申请书）》

            </span>

            <div class="legal-statement-box" id="legal-statement-text">填写本金、期间和计息规则后，点击核算。这里会生成可核对的计算说明，不会预先放一套示例数字。</div>

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

    let lastSubjectNote = "尚未核验。结果只显示年龄和法定退休时间，不预判劳务关系。";



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

        const postCadre = !!document.getElementById('subject-post-cadre')?.checked;

        const postWorker = !!document.getElementById('subject-post-worker')?.checked;

        const genderHint = /^\d{17}[\dX]$/.test(val) ? (parseInt(val.charAt(16), 10) % 2 === 0 ? '女' : '男') : '';

        if (genderHint === '女' && !postCadre && !postWorker) {

          const prompt = '请先选岗位。女性须由律师选择「管理/技术」或「工人」后，才能测算法定退休时间。岗位不是身份证号码推出来的。';

          badge.className = 'live-badge warn';

          textEl.innerText = '请先选岗位';

          lastSubjectNote = prompt;

          showToast('请先选岗位');

          return;

        }

        const idPayload = {

          id_card: val,

          receives_pension: document.getElementById('subject-pension')?.checked ? true : null

        };

        if (postCadre) idPayload.is_cadre = true;

        else if (postWorker) idPayload.is_cadre = false;

        try {

          const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/idcard`, {

            method: 'POST',

            headers: { 'Content-Type': 'application/json' },

            body: JSON.stringify(idPayload)

          });

          const d = await resp.json();

            if (d.valid && d.retirement_date_available === false) {

              badge.className = "live-badge warn";

              textEl.innerText = "请先选岗位";

              lastSubjectNote = d.retirement_note || "请先选岗位。女性须由律师选择「管理/技术」或「工人」。岗位不是身份证号码推出来的。";

              showToast("请先选岗位");

            } else if (d.valid) {

              badge.className = d.is_retired ? "live-badge warn" : "live-badge valid";

              textEl.innerText = d.badge_text || `${d.age}岁 · ${d.gender} · 法定退休时间 ${d.statutory_retire_date || ""}`;

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

      const paneDefense = document.getElementById('calc-pane-defense');

      if (paneDefense) paneDefense.style.display = mode === 'defense' ? 'block' : 'none';

      const paneEvidence = document.getElementById('calc-pane-evidence');

      if (paneEvidence) paneEvidence.style.display = mode === 'evidence' ? 'block' : 'none';

      const paneEnforce = document.getElementById('calc-pane-enforce');

      if (paneEnforce) paneEnforce.style.display = mode === 'enforce' ? 'block' : 'none';

      const paneDelay = document.getElementById('calc-pane-delay');

      if (paneDelay) paneDelay.style.display = mode === 'delay' ? 'block' : 'none';

      if (typeof window !== 'undefined') window.currentCalcMode = mode;



      // 调整第4项指标（诉责险）：仅在诉讼与保全费模式下展示

      const m4 = document.getElementById('metric-item-4');

      if (m4) m4.style.display = mode === 'court' ? 'flex' : 'none';



      // 调整右侧凭条类型徽章

      const typeBadge = document.getElementById('receipt-type-badge');

      if (mode === 'lpr') {

        typeBadge.innerText = "LPR 逾期利息";

        if (document.getElementById('lpr-p')?.value && document.getElementById('lpr-start')?.value && document.getElementById('lpr-end')?.value) runLprCalc();

      } else if (mode === 'court') {

        typeBadge.innerText = "诉讼与保全费";

        if (document.getElementById('fee-amount')?.value || document.getElementById('fee-case-type')?.value !== 'property') runCourtFeeCalc();

      } else if (mode === 'labor') {

        typeBadge.innerText = "劳动争议经济补偿";

        if (document.getElementById('labor-salary')?.value && document.getElementById('labor-hire-date')?.value && document.getElementById('labor-term-date')?.value) runLaborArbitrationCalc();

      } else if (mode === 'statute') {

        typeBadge.innerText = "诉讼时效与除斥期间";

        if (document.getElementById('statute-start')?.value) runStatuteLimitCalc();

      } else if (mode === 'preserv') {

        typeBadge.innerText = "保全续封红线监控";

        if (document.getElementById('preserv-start')?.value) runPreservationRenewalCalc();

      } else if (mode === 'validity') {

        typeBadge.innerText = "法条时效有效性核验";

        runStatuteValidityCheck();

      } else if (mode === 'settlement') {

        typeBadge.innerText = "商业和解与以物抵债精算";

        if (document.getElementById('settle-claim')?.value) runSettlementCalc();

      } else if (mode === 'appeal') {

        typeBadge.innerText = "上诉期截止日测算";

        if (document.getElementById('appeal-service-date')?.value) runAppealCalc();

      } else if (mode === 'enforce') {

        typeBadge.innerText = "申请执行期间";

        if (document.getElementById('enf-calc-anchor-date')?.value) runEnforcementDeadlineCalc();

      } else if (mode === 'delay') {

        typeBadge.innerText = "迟延履行加倍利息";

        if (document.getElementById('delay-principal')?.value && document.getElementById('delay-start')?.value && document.getElementById('delay-end')?.value) runDelayInterestCalc();

      }

    }



    function toggleCourtFeeExtras() {

      const ct = document.getElementById('fee-case-type')?.value || 'property';

      const show = (id, on) => {

        const el = document.getElementById(id);

        if (el) el.style.display = on ? 'block' : 'none';

      };

      show('fee-divorce-wrap', ct === 'divorce');

      show('fee-personality-wrap', ct === 'personality');

      show('fee-execution-wrap', ct === 'execution');

      const flags = document.getElementById('fee-acceptance-flags');

      if (flags) flags.style.display = ['property', 'divorce', 'labor', 'personality'].includes(ct) ? 'flex' : 'none';

    }



    function toggleEnforcementDays() {

      const kind = document.getElementById('enf-calc-anchor-type')?.value;

      const wrap = document.getElementById('enf-calc-days-wrap');

      if (wrap) wrap.style.display = kind === 'effective_plus_days' ? 'block' : 'none';

    }



    

    // 2.8 上诉期截止日测算

    async function runAppealCalc() {

      const sDateEl = document.getElementById('appeal-service-date');

      const jTypeEl = document.getElementById('appeal-judgment-type');

      const serviceDate = sDateEl ? sDateEl.value : '';

      const judgmentType = jTypeEl ? jTypeEl.value : 'judgment';

      if (!serviceDate) {

        showToast("请先填写裁判文书送达日期");

        return;

      }



      const laborPaths = ['worker_final_15', 'either_party_nonfinal_15', 'employer_revoke_30'];
      const endpoint = laborPaths.includes(judgmentType)
        ? `${API_BASE}/api/v1/phase1/calc/labor-award-deadline`
        : (judgmentType === 'arbitration_set_aside'
          ? `${API_BASE}/api/v1/phase1/calc/arbitration-set-aside`
          : `${API_BASE}/api/v1/phase1/calc/appeal-deadline`);
      const body = judgmentType === 'arbitration_set_aside'
        ? { receipt_date: serviceDate }
        : (laborPaths.includes(judgmentType)
          ? { receipt_date: serviceDate, path: judgmentType }
          : {
            service_date: serviceDate,
            judgment_type: judgmentType,
            party_without_domicile: !!document.getElementById('appeal-no-domicile')?.checked
          });

      try {

        const resp = await api.request(endpoint, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify(body)

        });

        const data = await resp.json();

        const noDomicile = !!document.getElementById('appeal-no-domicile')?.checked;
        const kindLabel = judgmentType === 'arbitration_set_aside'
          ? '三个月，不要按六个月'
          : (laborPaths.includes(judgmentType)
            ? (data.period_label || '劳动裁决后期限')
            : (noDomicile ? '域外没有住所，三十日' : (judgmentType === 'ruling' ? '裁定十日' : '判决十五日')));

        document.getElementById('metric-l1').innerText = "上诉期届满日";

        document.getElementById('metric-v1').innerText = data.deadline;

        document.getElementById('metric-s1').innerText = data.extended_for_holiday_or_weekend ? "届满日遇法定休假日，已顺延" : "届满日未遇法定休假日";

        document.getElementById('metric-l2').innerText = "送达日期";

        document.getElementById('metric-v2').innerText = data.service_date;

        document.getElementById('metric-s2').innerText = kindLabel + "，自送达次日起算";

        document.getElementById('metric-l3').innerText = "法律依据";

        document.getElementById('metric-v3').innerText = data.period_label || "民诉法第171条";

        document.getElementById('metric-s3').innerText = data.legal_basis || "";

        const typeBadge = document.getElementById('receipt-type-badge');

        if (typeBadge) typeBadge.innerText = data.period_label || "上诉期截止日测算";

        const warnText = (data.warnings || []).length ? "\n\n" + data.warnings.join("\n") : "";

        const notes = (data.notes || []).map(n => "• " + n).join("\n");

        const anchorShown = data.service_date || data.anchor_date || serviceDate;

        document.getElementById('legal-statement-text').innerText =

          `【期限测算】\n起算或送达日：${anchorShown}\n届满日：${data.deadline}\n${notes}${warnText}`;

        const holidayWarn = (data.warnings || []).find((item) => String(item).indexOf('节假日') >= 0);

        if (holidayWarn) {

          showToast("【节假日数据缺失警告】" + holidayWarn);

        }

        const deadlineKind = data.kind || (judgmentType === 'arbitration_set_aside' ? 'arbitration_set_aside' : (laborPaths.includes(judgmentType) ? 'labor_award_sue' : 'appeal'));

        lastCalcDeadline = {

          kind: deadlineKind,

          dueDate: data.deadline,

          source: data.legal_basis || '期限计算器',

          note: `${kindLabel}，起算日 ${anchorShown}`

        };

        const dlBtn = document.getElementById('btn-calc-add-deadline');

        if (dlBtn) dlBtn.style.display = 'inline-flex';

        showToast("上诉期届满日已更新");

      } catch (err) {

        showToast("上诉期测算失败: " + err);

      }

    }



    async function runEnforcementDeadlineCalc() {

      const anchorDate = document.getElementById('enf-calc-anchor-date')?.value || '';

      const anchorType = document.getElementById('enf-calc-anchor-type')?.value || 'performance_last_day';

      const performanceDays = parseInt(document.getElementById('enf-calc-performance-days')?.value || '10', 10);

      if (!anchorDate) {

        showToast("请先填写起算日期");

        return;

      }

      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/enforcement-deadline`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({

            anchor_date: anchorDate,

            anchor_type: anchorType,

            performance_days: Number.isNaN(performanceDays) ? 10 : performanceDays

          })

        });

        const d = await resp.json();

        document.getElementById('metric-l1').innerText = "申请执行期间届满日";

        document.getElementById('metric-v1').innerText = d.deadline;

        document.getElementById('metric-s1').innerText = d.status_label;

        document.getElementById('metric-l2').innerText = "期间起算点";

        document.getElementById('metric-v2').innerText = d.period_start_date;

        document.getElementById('metric-s2').innerText = d.anchor_label;

        document.getElementById('metric-l3').innerText = "剩余天数";

        document.getElementById('metric-v3').innerText = `${d.days_remaining} 天`;

        document.getElementById('metric-s3').innerText = d.legal_basis;

        document.getElementById('legal-statement-text').innerText =

          `【申请执行期间测算】\n${d.start_note}\n二年期间届满日：${d.deadline}${d.extended_for_holiday_or_weekend ? '（法定休假日顺延）' : ''}。\n${d.installment_note}\n${d.interruption_note}\n${d.risk_alert}`;

        lastCalcDeadline = {

          kind: 'enforcement_application',

          dueDate: d.deadline,

          source: '申请执行期间计算器（《民事诉讼法》第二百五十条）',

          note: d.start_note

        };

        const dlBtn = document.getElementById('btn-calc-add-deadline');

        if (dlBtn) dlBtn.style.display = 'inline-flex';

        showToast("申请执行期间届满日已更新");

      } catch (err) {

        showToast("申请执行期间测算失败: " + err);

      }

    }



    async function runDelayInterestCalc() {

      const principal = parseFloat(document.getElementById('delay-principal')?.value || '0');

      const startDate = document.getElementById('delay-start')?.value || '';

      const endDate = document.getElementById('delay-end')?.value || '';

      if (!startDate || !endDate || !(principal > 0)) {

        showToast("请填写未清偿金额、履行期间届满日和清偿日");

        return;

      }

      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/delay-interest`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({ principal_unpaid: principal, start_date: startDate, end_date: endDate })

        });

        const d = await resp.json();

        document.getElementById('metric-l1').innerText = "加倍部分债务利息";

        document.getElementById('metric-v1').innerText = `¥ ${d.interest.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-s1').innerText = d.interest_capital;

        document.getElementById('metric-l2').innerText = "迟延天数";

        document.getElementById('metric-v2').innerText = `${d.days} 天`;

        document.getElementById('metric-s2').innerText = d.day_count_note;

        document.getElementById('metric-l3').innerText = "日利率";

        document.getElementById('metric-v3').innerText = "日万分之1.75";

        document.getElementById('metric-s3').innerText = d.scope_note;

        document.getElementById('legal-statement-text').innerText =

          `【迟延履行加倍部分债务利息】\n未清偿金钱债务（不含一般债务利息）人民币 ${d.principal_unpaid.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。\n履行期间届满日 ${d.start_date}，测算至 ${d.end_date}，共 ${d.days} 天。${d.day_count_note}\n加倍部分债务利息人民币 ${d.interest.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（${d.interest_capital}）。\n${(d.warnings || []).join('\n')}`;

        showToast("加倍部分债务利息已更新");

      } catch (err) {

        showToast("迟延履行利息核算失败: " + err);

      }

    }



    async function runPenaltyAdjustCalc() {

      const agreed = parseFloat(document.getElementById('penalty-agreed')?.value || '0');

      const loss = parseFloat(document.getElementById('penalty-loss')?.value || '0');

      if (!(loss > 0) || agreed < 0) {

        showToast("请填写约定违约金和大于 0 的损失");

        return;

      }

      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/penalty-adjustment`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({ agreed_penalty: agreed, actual_loss: loss })

        });

        const d = await resp.json();

        document.getElementById('metric-l1').innerText = "是否超过损失的百分之三十";

        document.getElementById('metric-v1').innerText = d.exceeds_30_percent ? "一般可认定为过分高于" : "一般不认定过分高于";

        document.getElementById('metric-s1').innerText = d.ratio_percent;

        document.getElementById('metric-l2').innerText = "约定违约金";

        document.getElementById('metric-v2').innerText = `¥ ${d.agreed_penalty.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-s2').innerText = `损失 ¥ ${d.actual_loss.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-l3').innerText = "减到多少";

        document.getElementById('metric-v3').innerText = "本页不计算";

        document.getElementById('metric-s3').innerText = d.note;

        document.getElementById('legal-statement-text').innerText =

          `【违约金是否过分高于损失】\n${d.evaluation}\n超出损失的比例 ${d.ratio_percent}。${d.note}\n${(d.warnings || []).join('\n')}\n依据：${d.legal_basis}`;

        showToast("违约金对照已更新");

      } catch (err) {

        showToast("违约金对照失败: " + err);

      }

    }



    function onLprRuleChange() {

      const rule = document.getElementById('lpr-rule')?.value || 'commercial_floating';

      const isSales = rule === 'sales_fixed_lpr_markup';

      const isPrivate = rule === 'private_lending_cap';

      const show = (id, visible) => {

        const el = document.getElementById(id);

        if (el) el.style.display = visible ? '' : 'none';

      };

      show('lpr-mult-wrap', !isSales && !isPrivate);

      show('lpr-term-wrap', !isSales && !isPrivate);

      show('lpr-markup-wrap', isSales);

      show('lpr-private-row', isPrivate);

      const startLabel = document.getElementById('lpr-start-label');

      if (startLabel) startLabel.innerText = isSales ? '违约行为发生日' : '起息日';

    }



    // 2.1 LPR 逾期利息精算

    async function runLprCalc() {

      const principal = parseFloat(document.getElementById('lpr-p').value) || 0;

      const startDate = document.getElementById('lpr-start').value;

      const endDate = document.getElementById('lpr-end').value;

      if (!principal || !startDate || !endDate) {
        showToast("请填写本案本金、起息日和截止日。不会用示例本金或 2023-01-01 计算。");
        return;
      }

      const multiplier = parseFloat(document.getElementById('lpr-mult').value) || 1.0;

      const term = document.getElementById('lpr-term').value;

      const rule = document.getElementById('lpr-rule')?.value || 'commercial_floating';

      const filingDate = (document.getElementById('lpr-filing') || {}).value || "";



      if (rule === 'commercial_floating' && multiplier >= 4.0) {

        showToast("【提示】商业浮动不得选4倍LPR计息。民间借贷法定保护上限为合同成立时一年期LPR的4倍，请切换至民间借贷规则填报。");

        document.getElementById('lpr-rule').value = 'private_lending_cap';

        onLprRuleChange();

        return;

      }

      const payload = { principal, start_date: startDate, end_date: endDate, term, rule_mode: rule };

      if (rule === 'sales_fixed_lpr_markup') {

        payload.term = '1Y';

        payload.markup_ratio = parseFloat(document.getElementById('lpr-markup').value);

      } else if (rule === 'private_lending_cap') {

        const contractDate = document.getElementById('lpr-contract').value;

        if (!contractDate) {

          showToast("民间借贷请填写借款合同成立日");

          return;

        }

        payload.contract_date = contractDate;

        if (filingDate) payload.filing_date = filingDate;

        const agreed = document.getElementById('lpr-agreed').value;

        if (agreed !== "") payload.fixed_annual_rate = parseFloat(agreed);

      } else {

        payload.multiplier = multiplier;

      }



      try {

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

        const warn = (d.warnings || []).length ? `\n\n${d.warnings.join('\n')}` : '';

        document.getElementById('legal-statement-text').innerText = `${d.complaint_statement}${warn}`;

        showToast("LPR 逾期利息与明细公文已更新");

      } catch (e) {

        showToast("LPR 计算失败: " + e);

      }

    }



    // 2.2 诉讼费与保全费核算

    async function runCourtFeeCalc() {

      const amount = parseFloat(document.getElementById('fee-amount').value) || 0;

      const caseType = document.getElementById('fee-case-type')?.value || 'property';

      if (caseType === 'property' && !amount) {
        showToast("请填写本案标的额。财产案件不会按 0 元或示例金额计算受理费。");
        return;
      }

      const isSummary = !!document.getElementById('fee-summary')?.checked;

      const isMediation = !!document.getElementById('fee-mediation')?.checked;

      const isCounterclaim = !!document.getElementById('fee-counterclaim')?.checked;



      const payload = {

        claim_amount: amount,

        is_summary_procedure: isSummary,

        is_mediation_or_withdrawal: isMediation,

        is_counterclaim: isCounterclaim,

        case_type: caseType,

        divorce_base_fee: parseFloat(document.getElementById('fee-divorce-base')?.value || '100') || 100,

        personality_base_fee: parseFloat(document.getElementById('fee-personality-base')?.value || '300') || 300,

        execution_flat_fee: parseFloat(document.getElementById('fee-execution-flat')?.value || '50') || 50

      };



      const preservEl = document.getElementById('fee-preserv-amount');

      if (preservEl && preservEl.value.trim() !== '') {

        const parsedPreserv = parseFloat(preservEl.value.trim());

        if (!isNaN(parsedPreserv) && parsedPreserv >= 0) {

          payload.preservation_amount = parsedPreserv;

        }

      }



      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/court-fees`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify(payload)

        });

        const d = await resp.json();

        if (typeof window !== 'undefined') window.lastCourtFeeSnapshot = d;



        // 渲染大号指标

        document.getElementById('metric-l1').innerText = d.fee_nature === '申请费' ? "应交申请费" : "案件受理费（结案口径）";

        document.getElementById('metric-v1').innerText = `¥ ${d.actual_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        const prepay = d.filing_prepay_fee != null ? d.filing_prepay_fee : d.actual_fee;

        document.getElementById('metric-s1').innerText = `大写：${d.rmb_capital} · 立案预交 ¥ ${prepay.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;



        document.getElementById('metric-l2').innerText = "财产保全申请规费";

        document.getElementById('metric-v2').innerText = `¥ ${d.preservation_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        const included = d.preservation_included !== false && preservEl && preservEl.value.trim() !== '';

        const pAmount = included ? d.preservation_amount : 0;

        document.getElementById('metric-s2').innerText = included

          ? `保全标的 ¥ ${pAmount.toLocaleString('zh-CN', {minimumFractionDigits: 2})} (封顶 5,000 元)`

          : "未填写保全金额，不计保全费和诉责险";



        document.getElementById('metric-l3').innerText = "诉讼标的额";

        document.getElementById('metric-v3').innerText = `¥ ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        const laborScope = caseType === 'labor'
          ? '向人民法院起诉的劳动争议案件受理费，每件 10 元。劳动仲裁不收费，不要用本项。'
          : '';

        document.getElementById('metric-s3').innerText = isSummary

          ? `结案减半 ¥ ${d.reduction_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})}（依据《诉讼费用交纳办法》第十六条；退费口径，不是立案就预交一半）${laborScope ? ' ' + laborScope : ''}`

          : (laborScope || '依据《诉讼费用交纳办法》第13条');



        const m4 = document.getElementById('metric-item-4');

        if (m4) {

          m4.style.display = included ? 'flex' : 'none';

          if (included) {

            const ins = d.preservation_insurance || {};

            document.getElementById('metric-l4').innerText = "诉责险市场参考成本";

            document.getElementById('metric-v4').innerText = ins.cost_range_display || "¥ 0.00 ~ ¥ 0.00";

            const minNote = ins.is_minimum_charge_applied_low ? "起保底价 500 元" : `参考费率 ${ins.rate_range_desc || '0.08%~0.15%'}`;

            document.getElementById('metric-s4').innerText = minNote;

          }

        }



        // 生成公文说明段落 (完整三部分说明)

        const ins = d.preservation_insurance || {};

        const pAmountDisplay = pAmount.toLocaleString('zh-CN', {minimumFractionDigits: 2});

        const laborFeeNote = d.labor_court_fee_note ? `${d.labor_court_fee_note}` : '';

        const feeLine = `${laborFeeNote ? laborFeeNote + ' ' : ''}${d.filing_prepay_note || ''} 全额基准为人民币 ${d.standard_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元，本次测算应交人民币 ${d.actual_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（大写：${d.rmb_capital}），立案预交人民币 ${prepay.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。${d.statutory_reduction_rule || ''}`;

        const feeTitle = d.fee_nature === '申请费' ? '申请费' : '案件受理费';

        const statement = included

          ? `【诉讼费用、保全规费与诉责险测算说明】

一、${feeTitle}交纳依据与数额：

本案标的金额为人民币 ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。案件类型：${d.case_type}。

依据国务院《诉讼费用交纳办法》，全额基准为人民币 ${d.standard_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

${feeLine}



二、诉讼财产保全申请规费：

依据《诉讼费用交纳办法》第十四条第二款，保全申请金额为人民币 ${pAmountDisplay} 元，保全申请费为人民币 ${d.preservation_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（最高 5,000 元）。



三、诉讼保全责任保险市场参考：

这是商业保费估算，不是法定收费。参考费率 ${ins.rate_range_desc || '0.08% ~ 0.15%'}，最低起保 ${ins.min_premium ? ins.min_premium.toFixed(2) : '500.00'} 元。

以保全标的人民币 ${pAmountDisplay} 元测算，参考区间 ${ins.cost_range_display || ''}。最终以承保机构核保为准。



案件受理费和保全申请费可在起诉状中请求由被告承担。诉责险保费是否能主张，以合同约定和受诉法院口径为准。`

          : `【诉讼费用测算说明】

一、${feeTitle}交纳依据与数额：

本案标的金额为人民币 ${d.claim_amount.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。案件类型：${d.case_type}。

依据国务院《诉讼费用交纳办法》，全额基准为人民币 ${d.standard_fee.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

${feeLine}



未填写保全金额，本说明不含保全申请费，也不含诉责险。案件受理费可在起诉状中请求由被告承担。`;



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

      if (!salary || !hireDate || !termDate) {
        showToast("请填写本案月工资、入职日和解除日。不会用示例工资计算补偿。");
        return;
      }

      const avgRaw = document.getElementById('labor-avg-salary').value.trim();

      const avgSalary = avgRaw === '' ? null : parseFloat(avgRaw);

      const reason = document.getElementById('labor-reason')?.value || null;

      const priorNotice = document.getElementById('labor-notice')?.value === 'true';



      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/labor-arbitration`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({

            monthly_salary: salary,

            hire_date: hireDate,

            termination_date: termDate,

            local_avg_salary: avgSalary,

            termination_reason: reason || null,

            prior_30days_notice: priorNotice

          })

        });

        const d = await resp.json();



        const seg = d.segment_2008;

        const nAmt = seg ? seg.total_segmented_n : d.tiers['N'].amount;

        const noticePay = d.tiers['N+1'].notice_pay || 0;

        const np1Amt = seg ? (nAmt + noticePay) : d.tiers['N+1'].amount;

        const twoNAmt = seg ? seg.total_segmented_2n : d.tiers['2N'].amount;

        const reasonNow = document.getElementById('labor-reason')?.value || '';

        const finalAmt = reasonNow === 'unlawful_dismissal' ? twoNAmt : (d.notice_applicable ? np1Amt : nAmt);

        const finalLabel = reasonNow === 'unlawful_dismissal' ? '最终请求：违法解除赔偿金 2N' : (d.notice_applicable ? '最终请求：经济补偿加代通知金' : '最终请求：经济补偿 N');



        document.getElementById('metric-l1').innerText = finalLabel;

        document.getElementById('metric-v1').innerText = `¥ ${finalAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-s1').innerText = d.pleading_note || d.claim_mutex_note || '';



        document.getElementById('metric-l2').innerText = "对照：N / N+1 / 2N";

        document.getElementById('metric-v2').innerText = `¥ ${nAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;

        document.getElementById('metric-s2').innerText = `N+1 ¥ ${np1Amt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} · 2N ¥ ${twoNAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})}`;



        document.getElementById('metric-l3').innerText = "折算工龄计发月数";

        document.getElementById('metric-v3').innerText = `${d.compensation_months} 个月`;

        document.getElementById('metric-s3').innerText = `实际工龄：${d.tenure_str}`;



        // 生成公文说明段落

        const statement = `【劳动人事争议经济补偿与赔偿金精算说明（可写入仲裁申请书）】

一、工龄核定与计发基数：

申请人于 ${d.hire_date} 入职被申请人处，至双方劳动合同解除日 ${d.termination_date} 止，在被申请人处连续工作时间为 ${d.tenure_str}。

依据《中华人民共和国劳动合同法》第四十七条第一款规定，整段折算月数为 ${d.compensation_months} 个月。

申请人离职前十二个月的月平均工资为人民币 ${d.monthly_salary.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。${d.cap_reason}

${d.pleading_note || ''}



二、请求金额（N、N+1、2N 不能相加）：

本次建议写入请求的金额为人民币 ${finalAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元（${finalLabel}）。

经济补偿 N：人民币 ${nAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

代通知金口径：${d.tiers['N+1'].notice_note || ''} 对应金额人民币 ${np1Amt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

违法解除赔偿金 2N：人民币 ${twoNAmt.toLocaleString('zh-CN', {minimumFractionDigits: 2})} 元。

${seg ? `跨2008年分段：2008年前 ${seg.pre_2008_compensation_months} 个月、金额 ${seg.pre_2008_amount} 元；2008年后 ${seg.post_2008_compensation_months} 个月、金额 ${seg.post_2008_amount} 元。整段合并 N（${d.tiers['N'].amount} 元）只作对照。` : `计算公式：${d.tiers['N'].formula}。`}

${d.claim_mutex_note || ''}`;



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

      const skippedInterruptions = [];

      if (notes) {

        notes.split('\n').forEach(line => {

          const trimmed = line.trim();

          if (!trimmed) return;

          const m = trimmed.match(/^(\d{4}-\d{2}-\d{2})\s*(.*)$/);

          if (m) {

            interruptions.push({ date: m[1], description: m[2] || "主张权利或还款承诺" });

          } else {

            skippedInterruptions.push(trimmed);

          }

        });

      }

      if (skippedInterruptions.length) {

        showToast("有 " + skippedInterruptions.length + " 行中断记录没有以 YYYY-MM-DD 开头，已忽略，避免把日期算错");

      }



      try {

        const payload = { start_date: startDate, cause_type: causeType, interruption_events: interruptions };

        if (actDate) payload.act_date = actDate;

        if (causeType === 'labor_arbitration_1y') {
          payload.employment_ongoing = !!document.getElementById('statute-employment-ongoing')?.checked;
          payload.wage_arrears = !!document.getElementById('statute-wage-arrears')?.checked;
          const employmentEnd = document.getElementById('statute-employment-end')?.value;
          if (employmentEnd) payload.employment_end_date = employmentEnd;
        }

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/statute-limitations`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify(payload)

        });

        const d = await resp.json();



        // 渲染大号指标

        document.getElementById('metric-l1').innerText = "剩余执业安全期";

        document.getElementById('metric-v1').innerText = d.open_ended ? '不届满' : `${d.days_remaining} 天`;

        document.getElementById('metric-s1').innerText = d.status_label;

        document.getElementById('metric-v1').style.color = d.open_ended ? 'var(--accent-amber)' : (d.is_expired ? 'var(--status-warn)' : ((d.days_remaining != null && d.days_remaining <= 30) ? 'var(--status-warn)' : 'var(--accent-amber)'));



        document.getElementById('metric-l2').innerText = "最终届满到期日";

        document.getElementById('metric-v2').innerText = d.final_expire_date || '尚未起算';

        document.getElementById('metric-s2').innerText = `起算日：${d.start_date} (历经${d.effective_interruptions_count}次中断)`;



        document.getElementById('metric-l3').innerText = "适用法律规范";

        document.getElementById('metric-v3').innerText = d.is_preclusive ? "除斥期间" : "诉讼时效";

        document.getElementById('metric-s3').innerText = d.legal_basis;



        // 生成公文说明段落

        let statement = `【民事诉讼时效与除斥期间精算核定意见书】\n`;

        statement += `一、适用规则与法定起算点：\n本案权利保护请求属于【${d.rule_name}】，法定依据为 ${d.legal_basis}。\n`;

        statement += `原告知道或者应当知道权利受到损害以及义务人之日为 ${d.start_date}，法定初始届满到期日为 ${d.initial_expire_date}。\n\n`;

        statement += `二、时效推演与中断效力审查：\n`;

        (d.timeline_log || []).forEach(item => {

          statement += `• ${item.date} [${item.action}]：${item.event} -> 到期日顺延至 ${item.expire_date}\n`;

        });

        statement += `\n三、执业风险研判与结论：\n截至基准核算日(${d.calculation_benchmark_today})，距离法定届满期限尚余 ${d.days_remaining} 天。\n`;

        statement += `【风险评级】${d.status_label}：${d.risk_alert}\n`;

        if (d.is_preclusive) {

          statement += `特别警示：本期间性质为除斥期间，依《民法典》第一百九十九条，不适用中止、中断和延长，存续期间届满实体权利消灭！\n`;

        }

        if (d.special_notice) {

          statement += `${d.special_notice}\n`;

        }

        if ((d.rule_name || "").indexOf("保证") >= 0) {

          statement = statement.replace(

            `原告知道或者应当知道权利受到损害以及义务人之日为 ${d.start_date}`,

            `主债务履行期限届满日按 ${d.start_date} 填写。这不是普通诉讼时效的知道权利受损之日`

          );

        }



        document.getElementById('legal-statement-text').innerText = statement;

        lastCalcDeadline = d.open_ended ? null : {

          kind: causeType === 'labor_arbitration_1y' ? 'labor_arbitration' : 'statute_limitation',

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

        statement += `二、续封期限与申请时点：\n期限见《民事诉讼法解释》第四百八十五条，诉中保全经第一百五十六条依照执行程序办理。申请续行的时点见财产保全规定第十八条，应当在届满前 ${d.advance_days_required} 日提出。\n`;

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





    let lastCalcDeadline = null;

    let lastAppealDeadline = null;



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



    async function addCalculatorDeadlineToVault(kind, dueDate, sourceName, note, origin) {

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

            note: note || "",

            origin: origin || "statutory_calc"

          })

        });

        if (!resp.ok) {

          const err = await resp.json().catch(() => null);

          throw new Error(err?.detail || ('HTTP ' + resp.status));

        }

        const res = await resp.json();

        showToast(`已成功将【${sourceName}】(${dueDate}) 加入当前案件期限日历！`);

      } catch (e) {

        showToast(e instanceof ApiError ? e.userMessage : (e && e.userMessage ? e.userMessage : `操作失败：${e.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");

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



    function toggleLaborStatuteFields() {
      const box = document.getElementById('labor-statute-fields');
      const kind = document.getElementById('statute-type')?.value;
      if (box) box.style.display = kind === 'labor_arbitration_1y' ? 'block' : 'none';
    }

    function onDeadlineKindChange() {

      const kind = document.getElementById('new-deadline-kind')?.value;

      const tip = document.getElementById('deadline-kind-tip');

      const helper = document.getElementById('deadline-enforcement-helper');

      const show = kind === 'enforcement_application';

      if (tip) tip.style.display = show ? 'block' : 'none';

      if (helper) helper.style.display = show ? 'block' : 'none';

      const origin = document.getElementById('new-deadline-origin');

      const courtKinds = ['hearing', 'evidence_production', 'service_received'];

      if (origin) origin.value = courtKinds.includes(kind) ? 'court_notice' : 'statutory_calc';

    }



    async function fillEnforcementDeadlineFromCalc() {

      const anchorDate = document.getElementById('enf-modal-anchor-date')?.value || '';

      const anchorType = document.getElementById('enf-modal-anchor-type')?.value || 'performance_last_day';

      const performanceDays = parseInt(document.getElementById('enf-modal-performance-days')?.value || '10', 10);

      if (!anchorDate) {

        showToast("请先填写执行申请的起算日期");

        return;

      }

      try {

        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/enforcement-deadline`, {

          method: 'POST',

          headers: { 'Content-Type': 'application/json' },

          body: JSON.stringify({

            anchor_date: anchorDate,

            anchor_type: anchorType,

            performance_days: Number.isNaN(performanceDays) ? 10 : performanceDays

          })

        });

        const d = await resp.json();

        const dateEl = document.getElementById('new-deadline-date');

        const sourceEl = document.getElementById('new-deadline-source');

        const noteEl = document.getElementById('new-deadline-note');

        if (dateEl) dateEl.value = d.deadline;

        if (sourceEl) sourceEl.value = '《民事诉讼法》第二百五十条申请执行期间';

        if (noteEl) noteEl.value = `${d.start_note} ${d.interruption_note}`;

        showToast("已填入申请执行期间届满日 " + d.deadline);

      } catch (err) {

        showToast("测算失败: " + err);

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

      const origin = document.getElementById('new-deadline-origin')?.value || 'court_notice';

      if (!date) {

        showToast("请选择截止日期！");

        return;

      }

      await addCalculatorDeadlineToVault(kind, date, source, note, origin);

      closeAddDeadlineModal();

      await fetchAndRenderVaultDeadlines();

    }



    async function runDefenseDeadlineCalc() {
      const serviceDate = document.getElementById('defense-service-date')?.value || '';
      if (!serviceDate) {
        showToast("请先填写收到起诉状副本的日期");
        return;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/defense-deadline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ service_date: serviceDate })
        });
        const data = await resp.json();
        document.getElementById('metric-l1').innerText = "答辩期届满日";
        document.getElementById('metric-v1').innerText = data.deadline;
        document.getElementById('metric-s1').innerText = data.extended_for_holiday_or_weekend ? "届满日遇法定休假日，已顺延" : "届满日未遇法定休假日";
        document.getElementById('metric-l2').innerText = "收到起诉状副本";
        document.getElementById('metric-v2').innerText = data.anchor_date;
        document.getElementById('metric-s2').innerText = "十五日，收到当日不计入";
        document.getElementById('metric-l3').innerText = "依据";
        document.getElementById('metric-v3').innerText = "第128条";
        document.getElementById('metric-s3').innerText = data.legal_basis;
        const warnText = (data.warnings || []).length ? `\n${data.warnings.join('\n')}` : '';
        document.getElementById('legal-statement-text').innerText =
          `【答辩期测算】\n收到起诉状副本：${data.anchor_date}\n届满日：${data.deadline}\n${(data.notes || []).join('\n')}${warnText}`;
        lastCalcDeadline = {
          kind: 'defense_answer',
          dueDate: data.deadline,
          source: '答辩期计算器（《民事诉讼法》第一百二十八条）',
          note: '收到起诉状副本之日起十五日。公告送达或法院另定期间的，以通知为准。'
        };
        const typeBadge = document.getElementById('receipt-type-badge');
        if (typeBadge) typeBadge.innerText = "答辩期届满日测算";
        showToast("答辩期届满日已更新");
      } catch (err) {
        showToast("答辩期测算失败: " + err);
      }
    }

    async function runEvidencePeriodCalc() {
      const anchorDate = document.getElementById('evidence-anchor-date')?.value || '';
      const mode = document.getElementById('evidence-period-mode')?.value || 'first_ordinary_minimum';
      const daysRaw = document.getElementById('evidence-period-days')?.value;
      if (!anchorDate) {
        showToast("请先填写举证期限起算日");
        return;
      }
      const payload = { anchor_date: anchorDate, mode };
      if (mode === 'court_designated') {
        const days = parseInt(daysRaw, 10);
        if (!days) {
          showToast("法院指定举证期限时，请填写天数");
          return;
        }
        payload.period_days = days;
      }
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase1/calc/evidence-period`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await resp.json();
        document.getElementById('metric-l1').innerText = data.period_label || "举证期限";
        document.getElementById('metric-v1').innerText = data.deadline;
        document.getElementById('metric-s1').innerText = data.mode === 'notice_due_date'
          ? "按通知书原文记录，没有换算"
          : (data.is_statutory_minimum_only ? "这是法定下限，不是法院指定日" : "按录入的法院指定天数换算");
        document.getElementById('metric-l2').innerText = data.mode === 'notice_due_date' ? "通知书届满日" : "起算日";
        document.getElementById('metric-v2').innerText = data.anchor_date;
        document.getElementById('metric-s2').innerText = data.period_days == null
          ? "没有改成十五日下限"
          : `${data.period_days} 日，起算当日不计入`;
        document.getElementById('metric-l3').innerText = "依据";
        document.getElementById('metric-v3').innerText = "解释第99条";
        document.getElementById('metric-s3').innerText = data.legal_basis;
        const warnText = (data.warnings || []).join('\n');
        document.getElementById('legal-statement-text').innerText =
          `【举证期限测算】\n${data.period_label}\n起算日：${data.anchor_date}\n届满日：${data.deadline}\n${warnText}`;
        lastCalcDeadline = {
          kind: 'evidence_production',
          dueDate: data.deadline,
          source: data.is_statutory_minimum_only ? '举证期限下限测算（《民事诉讼法解释》第九十九条）' : '法院指定举证期限测算',
          note: warnText
        };
        const typeBadge = document.getElementById('receipt-type-badge');
        if (typeBadge) typeBadge.innerText = data.period_label || "举证期限测算";
        showToast(data.mode === 'notice_due_date'
          ? "已按通知书日期记录，没有重算。"
          : (data.is_statutory_minimum_only ? "已算出下限。法院通知另有日期的，以通知为准。" : "已按指定天数算出届满日"));
      } catch (err) {
        showToast("举证期限测算失败: " + err);
      }
    }

export {

  clientConvertRmbCapital,

  handleRmbInput,

  handleSubjectInput,

  runSubjectValidate,

  copySubjectNote,

  switchCalcSegment,

  runAppealCalc,

  runDefenseDeadlineCalc,

  runEvidencePeriodCalc,

  runEnforcementDeadlineCalc,

  runDelayInterestCalc,

  runPenaltyAdjustCalc,

  toggleCourtFeeExtras,

  toggleEnforcementDays,

  fillEnforcementDeadlineFromCalc,

  runLprCalc,

  onLprRuleChange,

  runCourtFeeCalc,

  runLaborArbitrationCalc,

  runStatuteLimitCalc,

  runPreservationRenewalCalc,

  runStatuteValidityCheck,

  toggleSettlementPlanUI,

  runSettlementCalc,

  addCurrentCalcDeadlineToVault,

  addAppealDeadlineToVault,

  addCalculatorDeadlineToVault,

  openAddDeadlineModal,

  closeAddDeadlineModal,

  handleAddDeadlineBackdropClick,

  onDeadlineKindChange,
  toggleLaborStatuteFields,

  submitManualDeadline,

  lastCalcDeadline,

  lastAppealDeadline,

};


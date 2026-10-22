/**
 * LawFlow Module: 03_evidence.js
 */
import { api, ApiError, API_BASE, withDownloadToken } from '../api.js';
import { showToast } from '../ui/toast.js';


// safe-html: static tab template
export const EVIDENCE_TAB_HTML = `      
      <!-- 上方极简证据清洗与打码操作台 -->
      <div class="quick-lookup-bar quick-lookup-2col">
        <!-- 合卷与打码 -->
        <div class="quick-tool-col">
          <div class="quick-tool-header">
            <span>证据材料 A4 自动合卷与贝茨编码 (支持 HEIC/TIFF/PDF)</span>
            <span class="tool-tip">页眉右上角加盖“证据1 - 第 1 页”</span>
          </div>
          <div class="quick-input-group">
            <input aria-label="多源证据原材料批量上传（支持 PDF、图片、Word、音频）"  type="file" id="ev-files" class="quick-input" multiple accept="image/*,application/pdf,.heic,.heif,.tiff,.tif" style="padding: 5px;">
            <input aria-label="证据组别标签或证明序号"  type="text" id="ev-label" class="quick-input" value="证据1" style="max-width: 90px;" placeholder="编码前缀">
            <button class="btn btn-sm" onclick="runProcessEvidence()">合卷打码</button>
          </div>
          <div id="ev-bates-result" style="display: none; font-size: 12px; margin-top: 4px; color: var(--status-valid);"></div>
        </div>

        <!-- 敏感信息脱敏 -->
        <div class="quick-tool-col">
          <div class="quick-tool-header">
            <span>敏感信息合规脱敏涂黑</span>
            <span class="tool-tip">18位身份证号与银行卡号物理黑条覆盖</span>
          </div>
          <div class="quick-input-group">
            <input aria-label="输入证据 PDF 文件名 (例: 合卷证据包_1792.pdf)"  type="text" id="redact-pdf-name" class="quick-input" placeholder="输入证据 PDF 文件名 (例: 合卷证据包_1792.pdf)">
            <button class="btn btn-secondary btn-sm" onclick="runRedactSensitive()">执行脱敏</button>
          </div>
          <div id="redact-result" style="display: none; font-size: 12px; margin-top: 4px; color: var(--status-valid);"></div>
        </div>

        <!-- 全格式离线转码 (Filee 协同) 快捷通告条 -->
        <div style="grid-column: 1 / -1; display: flex; align-items: center; justify-content: space-between; background: #FAF9F6; border: 1px solid #EAE6DD; border-radius: var(--radius-sm); padding: 7px 12px; margin-top: 2px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span class="badge" style="background: rgba(197, 133, 50, 0.15); color: var(--accent-amber); font-size: 11px;">⚖️ 司法离线转码中枢</span>
            <span style="font-size: 12px; color: var(--text-secondary);">
              支持 <strong>iPhone HEIC 照片、录音取证 (M4A/AMR)、银行流水 (CSV/XLSX)</strong> 离线转为法院立案合规 PDF 或标准 MP3。
            </span>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" onclick="openFileConverterModal()" style="padding: 3px 10px; font-size: 11.5px; display: inline-flex; align-items: center; gap: 4px; border-color: var(--accent-amber-border); color: var(--primary-navy); background: #FFFFFF;">
            <span>⚖️ 打开离线转码箱 (Filee 协同)</span>
          </button>
        </div>
      </div>

      <!-- 下方双栏阅读器 (左输入、右输出) -->
      <div class="split-grid-50-50">
        
        <!-- 左侧输入 -->
        <div class="surface-card">
          <div class="card-header">
            <div class="card-title">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
              五模块庭审提纲生成与合同红线审查
            </div>
          </div>

          <!-- 折叠卡片 A: 庭审提纲输入 -->
          <div style="margin-bottom: 14px;">
            <div style="font-size: 12.5px; font-weight: 700; color: var(--primary-navy); margin-bottom: 6px;">
              庭审提纲案情与诉辩主张
            </div>
            <div class="form-group" style="margin-bottom: 8px;">
              <label class="form-label">原告起诉请求与主张事实</label>
              <input aria-label="to p claims"  type="text" id="to-p-claims" value="原告已按期完成系统开发并开通账号，被告验收合格试运行但拒付尾款20万。">
            </div>

            <div class="form-group" style="margin-bottom: 8px;">
              <label class="form-label">被告答辩意见与抗辩主张</label>
              <textarea aria-label="to d defense"  id="to-d-defense" rows="2">被告主张系统经常出现死机现象，未达验收标准；且原告逾期交付超30天，主张5万元违约金抵扣。</textarea>
            </div>

            <button class="btn btn-secondary btn-sm" id="btn-trial-outline" onclick="runTrialOutlineAgent()" style="width: 100%;">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
              生成五模块庭审提纲 (概览/焦点/矩阵/法条/发问)
            </button>
          </div>

          <!-- 折叠卡片 B: 合同审查红线手册 (Playbook) 与多版本比对 (Diff) -->
          <div style="border-top: 1px solid var(--border-hairline); padding-top: 12px;">
            <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
              <span>审查立场手册 (Playbook) 与多版本比对</span>
              <span class="badge" style="background:#ECFDF5; color:#059669; border:1px solid #A7F3D0; font-size:10.5px;">Word原生修订导出</span>
            </div>

            <!-- 模式切换：单合同红线审查 VS 跨版本/模板偏离度比对 -->
            <div style="display: flex; gap: 4px; background: #EEF2F6; padding: 2px; border-radius: 6px; margin-bottom: 10px;">
              <button type="button" class="tab-pill-btn active" id="btn-cr-mode-single" onclick="switchContractReviewMode('single')" style="flex:1; text-align:center; padding: 4px 6px;">
                单合同立场审查 (Playbook)
              </button>
              <button type="button" class="tab-pill-btn" id="btn-cr-mode-diff" onclick="switchContractReviewMode('diff')" style="flex:1; text-align:center; padding: 4px 6px;">
                多版本/模板比对 (Diff)
              </button>
            </div>

            <!-- 模式 1：单合同审查容器 -->
            <div id="cr-view-single">
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">待审合同名称</label>
                <input aria-label="cr contract title"  type="text" id="cr-contract-title" value="商业技术开发与采购合同" />
              </div>

              <div class="form-row" style="margin-bottom: 8px;">
                <div class="form-group" style="flex: 1; margin-bottom: 0;">
                  <label class="form-label">审查立场视角</label>
                  <select aria-label="cr perspective"  id="cr-perspective">
                    <option value="乙方防御版">乙方防御版 (最大限度防范单方扣款与无限连带责任)</option>
                    <option value="甲方强势版">甲方强势版 (扩大解约权与高额违约金)</option>
                    <option value="中立版">中立版 (商业公允平衡)</option>
                  </select>
                </div>

                <div class="form-group" style="flex: 1; margin-bottom: 0;">
                  <label class="form-label">红线手册 (Playbook)</label>
                  <select aria-label="cr playbook"  id="cr-playbook" onchange="onPlaybookChange()">
                    <option value="tech_service" selected>软件与技术服务红线库 (5项)</option>
                    <option value="general">通用商业合同红线库 (5项)</option>
                    <option value="procurement">大宗买卖与采购红线库 (4项)</option>
                    <option value="labor">企业劳动用工红线库 (3项)</option>
                  </select>
                </div>
              </div>

              <!-- 红线规则清单预览 -->
              <div id="cr-playbook-rules-preview" style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 7px 10px; font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; line-height: 1.5; max-height: 70px; overflow-y: auto;">
                <!-- 动态加载红线规则 -->
              </div>

              <!-- 上传原合同源文件 (.docx) 控件 -->
              <div style="margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between; background: #FAF9F6; border: 1px dashed var(--border-hairline); border-radius: var(--radius-sm); padding: 8px 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <span style="font-size: 11.5px; font-weight: 600; color: var(--primary-navy);">原合同源文件 (.docx)：</span>
                  <span id="cr-source-file-badge" style="font-size: 11px; color: var(--text-muted);">未上传（未上传时导出为新生成文档，非原位修订）</span>
                </div>
                <input aria-label="cr source file input"  type="file" id="cr-source-file-input" accept=".docx" style="display:none;" onchange="handleContractSourceFileSelect(event)">
                <button type="button" class="btn btn-secondary btn-sm" onclick="document.getElementById('cr-source-file-input').click()" style="font-size: 11px; padding: 2px 8px;">
                  📄 上传原合同 (.docx)
                </button>
              </div>

              <div class="form-group" style="margin-bottom: 10px;">
                <label class="form-label">待审合同条文正文</label>
                <textarea aria-label="cr contract text"  id="cr-contract-text" rows="3">第七条 违约责任：乙方如延期交付超过3日，每日应向甲方支付合同总价款5%的惩罚性违约金；甲方有权随时单方解除合同且无需退还首期款项。发生争议由甲方所在地人民法院管辖。</textarea>
              </div>

              <div style="display: flex; gap: 8px;">
                <button class="btn" style="flex: 1.2;" id="btn-run-contract-review" onclick="runContractReview()">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                  审查红线条款与偏离度
                </button>
                <button class="btn btn-secondary" style="flex: 1;" id="btn-export-redline" onclick="exportRedlineDocx()">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  导出修订 Word
                </button>
              </div>
            </div>

            <!-- 模式 2：多版本比对与模板偏离度容器 -->
            <div id="cr-view-diff" style="display: none;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-size: 11.5px; color: var(--text-secondary);">跨文档双版本对齐与条款变更审阅</span>
                <button type="button" class="btn btn-secondary btn-sm" onclick="loadVersionDiffPreset()" style="font-size: 11px; padding: 2px 7px;">
                  📄 填入标准借款合同母本 vs 修改稿
                </button>
              </div>

              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">基准母本/标准模板合同名称</label>
                <input aria-label="diff base title"  type="text" id="diff-base-title" value="《企业间借款合同·律所标准母本版》" />
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">基准母本条款正文</label>
                <textarea aria-label="diff base text"  id="diff-base-text" rows="3" style="font-size: 11.5px; font-family: var(--font-mono);">第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限自2025年1月10日起至2026年1月9日止。
第三条 借款利息：年利率固定为12%，按季度结息。
第四条 保证担保：丙方承担不可撤销的连带保证责任，保证范围包括本金、利息、违约金及律师费。
第五条 争议解决：因履行本合同引起的争议，由原告所在地人民法院管辖。</textarea>
              </div>

              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">待审版本/相对方修改稿名称</label>
                <input aria-label="diff target title"  type="text" id="diff-target-title" value="《企业间借款合同·借款人修订草案》" />
              </div>
              <div class="form-group" style="margin-bottom: 10px;">
                <label class="form-label">相对方修订条款正文</label>
                <textarea aria-label="diff target text"  id="diff-target-text" rows="3" style="font-size: 11.5px; font-family: var(--font-mono);">第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限经双方协商延长至2026年7月9日止。
第三条 借款利息：年利率固定为6%，到期一次性还本付息。
第五条 争议解决：发生争议由中国国际经济贸易仲裁委员会北京分会仲裁。
第六条 提前还款：借款人提前偿还本金的，不承担任何违约赔偿责任。</textarea>
              </div>

              <div style="display: flex; gap: 8px;">
                <button class="btn" style="flex: 1.2;" id="btn-run-version-diff" onclick="runVersionCompareUI()">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v1"></path><path d="M18 8h4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4"></path><polyline points="10 9 9 9 8 9"></polyline></svg>
                  启动条款对齐与偏离度比对
                </button>
                <button class="btn btn-secondary" style="flex: 1;" id="btn-export-version-diff" onclick="exportVersionDiffDocxUI()">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                  导出比对修订 Word
                </button>
              </div>
            </div>
          </div>

          <!-- 折叠卡片 C: 证据目录自动提炼、三性质证意见与对方红队攻击 -->
          <div style="border-top: 1px solid var(--border-hairline); padding-top: 12px; margin-top: 12px;">
            <div style="font-size: 13px; font-weight: 700; color: var(--primary-navy); margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
              <span>AI 证据目录、三性质证意见与红队攻击</span>
              <span class="badge" style="background:#EFF6FF; color:#1D4ED8; font-size:10.5px;">法庭质证实务</span>
            </div>

            <!-- 子工具切换 -->
            <div style="display: flex; gap: 4px; background: #EEF2F6; padding: 2px; border-radius: 6px; margin-bottom: 10px;">
              <button type="button" class="tab-pill-btn active" id="btn-evtool-catalog" onclick="switchEvidenceSubTool('catalog')" style="flex:1; text-align:center; padding: 4px 6px;">
                ① 证据目录
              </button>
              <button type="button" class="tab-pill-btn" id="btn-evtool-cross" onclick="switchEvidenceSubTool('cross')" style="flex:1; text-align:center; padding: 4px 6px;">
                ② 质证意见 (三性)
              </button>
              <button type="button" class="tab-pill-btn" id="btn-evtool-attack" onclick="switchEvidenceSubTool('attack')" style="flex:1; text-align:center; padding: 4px 6px;">
                ③ 红队攻击
              </button>
            </div>

            <!-- 子工具 1：证据目录提炼 -->
            <div id="evtool-pane-catalog">
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">案由与举证人</label>
                <div style="display: flex; gap: 8px;">
                  <input aria-label="案由"  type="text" id="ev-catalog-cause" placeholder="案由" value="民间借贷纠纷" style="flex: 1;" class="quick-input" />
                  <input aria-label="举证人"  type="text" id="ev-catalog-plaintiff" placeholder="举证人" value="原告" style="flex: 1;" class="quick-input" />
                </div>
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">原始证据碎片清单 / 提取文本</label>
                <textarea aria-label="ev catalog notes"  id="ev-catalog-notes" rows="3" class="quick-input">1. 《借款协议及转账凭证》：证明借款本金交付及利息约定事实；
2. 《催款微信聊天记录与通话录音》：证明原告多次催要、借款人认可借贷事实且时效中断；
3. 《连带责任保证承诺函》：证明丙方自愿承担不可撤销连带保证责任。</textarea>
              </div>
              <button class="btn btn-sm" style="width: 100%; background: var(--primary-navy);" onclick="runAutoEvidenceCatalogUI()">
                ⚡ 生成证据目录
              </button>
            </div>

            <!-- 子工具 2：证据三性质证 -->
            <div id="evtool-pane-cross" style="display: none;">
              <div class="form-row" style="margin-bottom: 8px;">
                <div class="form-group" style="flex: 1.5; margin-bottom: 0;">
                  <label class="form-label">对方出示证据名称</label>
                  <input aria-label="ev cross name"  type="text" id="ev-cross-name" value="被告提交的手写收据复印件" class="quick-input" />
                </div>
                <div class="form-group" style="flex: 1; margin-bottom: 0;">
                  <label class="form-label">证据种类</label>
                  <select aria-label="ev cross category"  id="ev-cross-category" class="quick-input">
                    <option value="书证" selected>书证</option>
                    <option value="电子数据">电子数据</option>
                    <option value="证人证言">证人证言</option>
                    <option value="视听资料">视听资料</option>
                  </select>
                </div>
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">对方证明目的</label>
                <input aria-label="ev cross purpose"  type="text" id="ev-cross-purpose" value="证明原告已收取10万元货款并结清争议标的" class="quick-input" />
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">我方当事人真实情况与反驳事实</label>
                <textarea aria-label="ev cross facts"  id="ev-cross-facts" rows="2" class="quick-input">原告从未收到该款项，收据签名不是原告字迹，被告拒不出示原件，系伪造凭据。</textarea>
              </div>
              <button class="btn btn-sm" style="width: 100%; background: var(--primary-navy);" onclick="runCrossExaminationUI()">
                ⚡ 生成质证意见
              </button>
            </div>

            <!-- 子工具 3：对方红队质证攻击 -->
            <div id="evtool-pane-attack" style="display: none;">
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">我方关键证据名称</label>
                <input aria-label="ev attack name"  type="text" id="ev-attack-name" value="银行电子转账回执单（附言为往来款）" class="quick-input" />
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">我方证明目的</label>
                <input aria-label="ev attack purpose"  type="text" id="ev-attack-purpose" value="证明原告已向被告全额出借款项50万元" class="quick-input" />
              </div>
              <div class="form-group" style="margin-bottom: 8px;">
                <label class="form-label">证据原始文本或瑕疵摘录</label>
                <textarea aria-label="ev attack snippet"  id="ev-attack-snippet" rows="2" class="quick-input">回单转账附言备注为『往来款』而非『借款』，且收款账户为第三方个人。</textarea>
              </div>
              <button class="btn btn-sm" style="width: 100%; background: #991B1B;" onclick="runAdversarialAttackUI()">
                ⚡ 红队攻击
              </button>
            </div>
          </div>
        </div>

        <!-- 右侧阅读器输出 (多视图联动：庭审提纲 / 合同三栏修订 / 多版本比对) -->
        <div class="docket-receipt-paper">
          <div class="receipt-header" style="display: flex; justify-content: space-between; align-items: center;">
            <div style="display: flex; align-items: center; gap: 4px; background: #F1F5F9; padding: 2px 4px; border-radius: 6px;">
              <button type="button" class="tab-pill-btn" id="btn-p2-tab-outline" onclick="switchPhase2RightTab('outline')">
                五模块庭审提纲
              </button>
              <button type="button" class="tab-pill-btn active" id="btn-p2-tab-redline" onclick="switchPhase2RightTab('redline')">
                三栏修订卡片与偏离度
              </button>
              <button type="button" class="tab-pill-btn" id="btn-p2-tab-diff" onclick="switchPhase2RightTab('diff')">
                📑 多版本/模板偏离度比对
              </button>
              <button type="button" class="tab-pill-btn" id="btn-p2-tab-tools" onclick="switchPhase2RightTab('tools')">
                ⚖️ 证据目录与质证攻防
              </button>
            </div>

            <div style="display: flex; align-items: center; gap: 6px;" id="p2-right-actions">
              <button class="btn btn-secondary btn-sm" id="btn-copy-p2-content" onclick="copyPhase2ActiveContent()">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                复制当前公文
              </button>
            </div>
          </div>

          <!-- 视图 A：五模块庭审提纲 -->
          <div id="p2-pane-outline" style="display: none;">
            <div class="legal-statement-box" id="to-outline-result" style="min-height: 480px; max-height: 580px; overflow-y: auto;">
              点击左侧【生成五模块庭审提纲】，系统将依据原告起诉主张与被告答辩要点，输出包含：
一、案件核心概览
二、争议焦点拆解
三、事实查明矩阵
四、法律适用检索
五、法庭发问提纲与反制预案
的出庭专用结构化公文。
            </div>
          </div>

          <!-- 视图 B：合同三栏修订卡片与红线手册偏离度清单 -->
          <div id="p2-pane-redline" style="display: block; min-height: 480px; max-height: 580px; overflow-y: auto; padding: 6px 0;">
            <div id="cr-result-container">
              <div style="padding: 40px 20px; text-align: center; color: var(--text-muted); font-size: 13px;">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="margin-bottom: 8px; opacity: 0.5;"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line></svg>
                <div style="font-weight: 600; color: var(--primary-navy); margin-bottom: 4px;">合同审查红线手册 (Playbook) 与三栏修订模式</div>
                <div style="font-size: 12px; color: var(--text-secondary); max-width: 480px; margin: 0 auto; line-height: 1.6;">
                  点击左侧【审查红线条款与偏离度】，系统将对照所选审查立场及红线库标准，逐条输出：<br/>
                  <span style="color: #059669; font-weight: 600;">1. 偏离度判定</span> (严重踩雷 / 偏离标准 / 遵从红线)<br/>
                  <span style="color: #0284C7; font-weight: 600;">2. 三栏修订卡片</span> (原文 → 字符级Diff高亮 → 谈判话术)<br/>
                  <span style="color: #D97706; font-weight: 600;">3. Word 原生修订模式</span> (&lt;w:ins&gt; / &lt;w:del&gt;) 一键导出
                </div>
              </div>
            </div>
          </div>

          <!-- 视图 C：多版本比对与模板偏离度分析 -->
          <div id="p2-pane-diff" style="display: none; min-height: 480px; max-height: 580px; overflow-y: auto; padding: 6px 0;">
            <div id="version-diff-container">
              <div style="padding: 40px 20px; text-align: center; color: var(--text-muted); font-size: 13px;">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" style="margin-bottom: 8px; opacity: 0.5;"><path d="M16 16v1a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h11a2 2 0 0 1 2 2v1"></path><path d="M18 8h4a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-4"></path><polyline points="10 9 9 9 8 9"></polyline></svg>
                <div style="font-weight: 600; color: var(--primary-navy); margin-bottom: 4px;">多版本跨文档条款对齐与偏离度比对</div>
                <div style="font-size: 12px; color: var(--text-secondary); max-width: 480px; margin: 0 auto; line-height: 1.6;">
                  选择左侧【多版本/模板比对 (Diff)】并点击启动，系统将自动进行：<br/>
                  <span style="color: #059669; font-weight: 600;">1. 跨文档条款智能对齐</span> (跨越条款顺序颠倒与段落合并)<br/>
                  <span style="color: #D97706; font-weight: 600;">2. 实质性修改与红线删除标记</span> (高风险条款删除预警)<br/>
                  <span style="color: #0284C7; font-weight: 600;">3. Word 原生修订标记 (&lt;w:ins&gt; / &lt;w:del&gt;) 一键导出</span>
                </div>
              </div>
            </div>
          </div>

          <!-- 视图 D：证据目录与质证攻防结果展示 -->
          <div id="p2-pane-tools" style="display: none; min-height: 480px; max-height: 580px; overflow-y: auto; padding: 6px 0;">
            <div id="ev-tools-result-container">
              <div style="padding: 40px 20px; text-align: center; color: var(--text-muted); font-size: 13px;">
                <div style="font-weight: 600; color: var(--primary-navy); margin-bottom: 4px;">法庭证据目录、质证意见与红队攻击工作台</div>
                <div style="font-size: 12px; color: var(--text-secondary); max-width: 480px; margin: 0 auto; line-height: 1.6;">
                  在左侧选择对应工具并点击生成，此处将展示提炼出的证据四要素表格、真实性合法性关联性三性质证意见，或对方模拟质证攻击要点，并支持直接导出 Word (.docx)。
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </section>

    <!-- ======================================================================
         模块 04：类案检索与签署 (双路检索 + 远程委托闭环)
         ====================================================================== -->
`;

export function renderTabEvidence() {
  const el = document.getElementById('tab-evidence');
  if (el) {
    // safe-html: mount static tab template
    el.innerHTML = EVIDENCE_TAB_HTML;
  }
}


    // =========================================================================
    // 4. 模块 03：证据清洗与庭审
    // =========================================================================
    async function runProcessEvidence() {
      const fileInput = document.getElementById('ev-files');
      if (!fileInput.files.length) {
        showToast("请先选择证据文件 (图片或PDF)");
        return;
      }
      const formData = new FormData();
      for (let i = 0; i < fileInput.files.length; i++) {
        formData.append("files", fileInput.files[i]);
      }
      formData.append("evidence_label", document.getElementById('ev-label').value || "证据1");

      const resBox = document.getElementById('ev-bates-result');
      resBox.style.display = 'block';
      resBox.innerHTML = `<span class="spinner-dark"></span> 正在合卷并加盖右上角贝茨编码...`;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/process-evidence`, {
          method: 'POST',
          body: formData
        });
        const d = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          const errMsg = (d && (d.detail || d.message)) ? (typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail)) : `HTTP ${resp.status}`;
          resBox.innerHTML = `合卷失败: ${escapeHtml(errMsg)}`;
          showToast("证据合卷失败");
          return;
        }
        const statusNote = d.status === "partial" ? "（部分成功）" : "";
        let skipBlock = "";
        if (Array.isArray(d.skipped_files) && d.skipped_files.length > 0) {
          const lines = d.skipped_files.map(s => {
            const name = (s && s.filename) ? s.filename : String(s);
            const reason = (s && s.reason) ? `（${s.reason}）` : "";
            return `<li>${escapeHtml(name)}${escapeHtml(reason)}</li>`;
          }).join("");
          skipBlock = `<div style="margin-top:10px;padding:10px;border:1px solid #C58532;background:#FFF8E7;color:#7A4E00;"><strong>以下文件未并入：</strong><ul style="margin:6px 0 0 18px;">${lines}</ul></div>`;
        }
        resBox.innerHTML = ` // safe-html: skipBlock 列表项已 escapeHtml
          已成功合卷${escapeHtml(statusNote)}！总页数：${escapeHtml(d.total_pages)} 页 | 文件：${escapeHtml(d.merged_pdf_filename)}
          <a href="${escapeHtml(withDownloadToken(d.download_url))}" class="btn btn-secondary btn-sm" style="margin-left: 8px;" download>下载合卷 PDF</a>
          ${skipBlock} // safe-html: static or pre-escaped HTML fragment
        `;
        document.getElementById('redact-pdf-name').value = d.merged_pdf_filename || "";
        showToast(d.status === "partial" ? "证据合卷完成（有文件未并入）" : "证据合卷与贝茨编码完成");
      } catch (e) {
        resBox.innerHTML = `合卷失败: ${escapeHtml(e)}`;
      }
    }

    async function runRedactSensitive() {
      const filename = document.getElementById('redact-pdf-name').value.trim();
      if (!filename) {
        showToast("请输入待脱敏的 PDF 文件名");
        return;
      }
      const resBox = document.getElementById('redact-result');
      resBox.style.display = 'block';
      resBox.innerHTML = `<span class="spinner-dark"></span> 正在执行物理不可逆黑条脱敏...`;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/redact-sensitive`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pdf_filename: filename, redact_idcard: true, redact_bankcard: true })
        });
        const d = await resp.json();
        resBox.innerHTML = `
          已完成脱敏涂黑！遮蔽条数：${escapeHtml(d.redactions_count)} 处 (${escapeHtml(d.redacted_items.join('、'))})
          <a href="${escapeHtml(withDownloadToken(d.download_url))}" class="btn btn-secondary btn-sm" style="margin-left: 8px;" download>下载脱敏 PDF</a>
        `;
        showToast("敏感信息合规脱敏涂黑成功");
      } catch (e) {
        resBox.innerHTML = `脱敏失败: ${escapeHtml(e)}`;
      }
    }

    async function runTrialOutlineAgent() {
      const btn = document.getElementById('btn-trial-outline');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner"></span> 正在拆解焦点与盘问预案...`;
      btn.disabled = true;

      const payload = {
        case_title: "买卖合同与承揽纠纷一审出庭提纲",
        cause_of_action: "买卖与技术合同纠纷",
        plaintiff_claims_and_facts: document.getElementById('to-p-claims').value,
        defendant_defense: document.getElementById('to-d-defense').value
      };

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/trial-outline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const d = await resp.json();
        btn.innerHTML = origHtml;
        btn.disabled = false;
        document.getElementById('to-outline-result').innerText = d.trial_outline_markdown;
        showToast("五模块庭审提纲生成成功");
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        showToast("生成失败: " + e);
      }
    }

    let lastContractReviewData = null;
    let cachedPlaybooks = null;

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    function switchPhase2RightTab(tab) {
      const btnOutline = document.getElementById('btn-p2-tab-outline');
      const btnRedline = document.getElementById('btn-p2-tab-redline');
      const btnDiff = document.getElementById('btn-p2-tab-diff');
      const btnTools = document.getElementById('btn-p2-tab-tools');
      const paneOutline = document.getElementById('p2-pane-outline');
      const paneRedline = document.getElementById('p2-pane-redline');
      const paneDiff = document.getElementById('p2-pane-diff');
      const paneTools = document.getElementById('p2-pane-tools');

      btnOutline?.classList.toggle('active', tab === 'outline');
      btnRedline?.classList.toggle('active', tab === 'redline');
      btnDiff?.classList.toggle('active', tab === 'diff');
      btnTools?.classList.toggle('active', tab === 'tools');

      if (paneOutline) paneOutline.style.display = (tab === 'outline') ? 'block' : 'none';
      if (paneRedline) paneRedline.style.display = (tab === 'redline') ? 'block' : 'none';
      if (paneDiff) paneDiff.style.display = (tab === 'diff') ? 'block' : 'none';
      if (paneTools) paneTools.style.display = (tab === 'tools') ? 'block' : 'none';
    }

    function switchEvidenceSubTool(sub) {
      ['catalog', 'cross', 'attack'].forEach(k => {
        const btn = document.getElementById(`btn-evtool-${k}`);
        const pane = document.getElementById(`evtool-pane-${k}`);
        if (btn) btn.classList.toggle('active', k === sub);
        if (pane) pane.style.display = (k === sub) ? 'block' : 'none';
      });
    }

    async function loadPlaybooksIfNeeded() {
      if (cachedPlaybooks) return cachedPlaybooks;
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/contract-review/playbooks`);
        const d = await resp.json();
        cachedPlaybooks = d.playbooks;
        return cachedPlaybooks;
      } catch (e) {
        console.warn("加载 Playbook 列表失败:", e);
        return null;
      }
    }

    async function onPlaybookChange() {
      const pKey = document.getElementById('cr-playbook').value;
      const previewBox = document.getElementById('cr-playbook-rules-preview');
      const pbs = await loadPlaybooksIfNeeded();
      if (pbs && pbs[pKey]) {
        const rules = pbs[pKey].rules || [];
        previewBox.innerHTML = `<strong>${escapeHtml(pbs[pKey].name)}：</strong><br/>` + rules.map((r, i) => `${escapeHtml(i+1)}. ${escapeHtml(r)}`).join('<br/>');
      } else {
        previewBox.innerHTML = `可直接编辑左侧合同正文，系统将依据通用商业红线与严格防御标准进行穿透审查。`;
      }
    }

    function renderDiffHtml(diffChunks, origText, suggText) {
      if (Array.isArray(diffChunks) && diffChunks.length > 0) {
        return diffChunks.map(c => {
          if (c.type === 'delete') {
            return `<del class="diff-del">${escapeHtml(c.text)}</del>`;
          } else if (c.type === 'insert') {
            return `<ins class="diff-ins">${escapeHtml(c.text)}</ins>`;
          } else {
            return `<span>${escapeHtml(c.text)}</span>`;
          }
        }).join('');
      }
      return `<span>${escapeHtml(suggText || origText)}</span>`;
    }

    async function runContractReview() {
      const btn = document.getElementById('btn-run-contract-review');
      const origHtml = btn.innerHTML;
      btn.innerHTML = `<span class="spinner-dark"></span> 审查中...`;
      btn.disabled = true;

      const title = document.getElementById('cr-contract-title').value.trim() || "商业技术开发与采购合同";
      const perspective = document.getElementById('cr-perspective').value;
      const playbookKey = document.getElementById('cr-playbook').value;
      const contractText = document.getElementById('cr-contract-text').value.trim();

      switchPhase2RightTab('redline');
      const container = document.getElementById('cr-result-container');
      container.innerHTML = `
        <div style="padding: 50px 20px; text-align: center; color: var(--text-secondary);">
          <span class="spinner-dark"></span>
          <div style="margin-top: 10px; font-weight: 600; color: var(--primary-navy);">正在依据【${escapeHtml(perspective)}】与【红线手册】逐条比对审查...</div>
          <div style="font-size: 11.5px; color: var(--text-muted); margin-top: 4px;">正在计算条款偏离度、识别法律漏洞与生成 Word 原生修订标签</div>
        </div>
      `;

      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/contract-review`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            contract_title: title,
            contract_text: contractText,
            perspective: perspective,
            playbook_preset: playbookKey
          })
        });
        const d = await resp.json();
        btn.innerHTML = origHtml;
        btn.disabled = false;
        lastContractReviewData = d;

        const rev = d.review || {};
        const clauses = rev.clause_reviews || [];
        const riskLevel = rev.overall_risk_level || '中';
        const score = rev.playbook_compliance_score || 80;

        let riskBadgeBg = '#FEF3C7';
        let riskColor = '#D97706';
        if (riskLevel === '高') {
          riskBadgeBg = '#FFE4E6';
          riskColor = '#E11D48';
        } else if (riskLevel === '低') {
          riskBadgeBg = '#DCFCE7';
          riskColor = '#16A34A';
        }

        let html = `
          <!-- 审阅结果总览头部看板 -->
          <div style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-size: 14px; font-weight: 700; color: var(--primary-navy);">《${escapeHtml(d.contract_title || title)}》</span>
                <span class="badge" style="background: ${riskBadgeBg}; color: ${riskColor}; border: 1px solid ${riskColor}40; font-weight: 700;">
                  风险等级: ${riskLevel}
                </span>
                <span class="badge" style="background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE;">
                  红线遵从度: ${score} 分
                </span>
                <span class="badge" style="background: #F1F5F9; color: var(--text-secondary); border: 1px solid var(--border-hairline);">
                  立场: ${escapeHtml(d.perspective || perspective)}
                </span>
              </div>
              <button class="btn btn-primary btn-sm" onclick="exportRedlineDocx()" style="display: inline-flex; align-items: center; gap: 5px;">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                <span>下载原生修订 Word (.docx)</span>
              </button>
            </div>
            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 8px; line-height: 1.5; border-top: 1px dashed var(--border-hairline); padding-top: 8px;">
              <strong>综合策略：</strong>${escapeHtml(rev.review_summary || '已对齐审查红线手册，重构高风险条款。')}
            </div>
          </div>
        `;

        if (clauses.length === 0) {
          html += `<div style="padding: 20px; text-align: center; color: var(--text-muted);">未发现偏离红线条款，合同表述较为合规。</div>`;
        } else {
          clauses.forEach((c, idx) => {
            const dev = c.playbook_deviation || 'OUT_OF_SCOPE_DEVIATION';
            let devBadgeHtml = `<span class="badge-deviation">⚠ 偏离标准红线</span>`;
            if (dev === 'CRITICAL_BREACH') {
              devBadgeHtml = `<span class="badge-breach">⛔ 严重踩雷</span>`;
            } else if (dev === 'COMPLIANT') {
              devBadgeHtml = `<span class="badge-compliant">✓ 遵从红线</span>`;
            }

            const ruleDesc = c.matched_playbook_rule || '商业风险防范规则';
            const diffRendered = renderDiffHtml(c.diff_chunks, c.original_clause, c.suggested_clause);

            html += `
              <div class="review-card-item">
                <div class="review-card-header">
                  <div class="review-card-title">
                    <span>${idx + 1}. ${escapeHtml(c.clause_title || '关键风险条款')}</span>
                    ${devBadgeHtml}
                  </div>
                  <button class="btn btn-secondary btn-sm" style="font-size: 11px; padding: 2px 8px;" onclick="copySuggestedClause(${idx})">
                    复制修订条文
                  </button>
                </div>

                <div style="font-size: 11px; color: var(--text-muted); margin-bottom: 8px;">
                  <strong>对应审查红线：</strong>${escapeHtml(ruleDesc)}
                </div>

                <!-- 三栏对比卡片 (瑞士平面排版) -->
                <div class="review-3col-grid">
                  <!-- 第 1 栏：合同原文 -->
                  <div class="col-pane col-orig">
                    <div class="col-pane-title" style="color: var(--text-secondary);">
                      <span>原合同争议条款</span>
                    </div>
                    <div>${escapeHtml(c.original_clause || '')}</div>
                  </div>

                  <!-- 第 2 栏：AI 加固修订 (Diff 字符级高亮) -->
                  <div class="col-pane col-diff">
                    <div class="col-pane-title" style="color: #0284C7;">
                      <span>AI 修订建议 (原生 Diff 标记)</span>
                    </div>
                    <div>${diffRendered}</div>
                  </div>

                  <!-- 第 3 栏：法律漏洞与谈判话术 -->
                  <div class="col-pane col-tactics">
                    <div class="col-pane-title" style="color: #92400E;">
                      <span>漏洞分析与谈判交涉话术</span>
                    </div>
                    <div style="margin-bottom: 6px;"><strong>漏洞：</strong>${escapeHtml(c.risk_analysis || '')}</div>
                    <div><strong>话术：</strong>${escapeHtml(c.negotiation_tip || '')}</div>
                  </div>
                </div>
              </div>
            `;
          });
        }

        container.innerHTML = html;
        showToast("合同红线与三栏审查对比完成");
      } catch (e) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        container.innerHTML = `<div style="padding: 20px; color: var(--status-warn);">审查失败: ${escapeHtml(e)}</div>`;
      }
    }

    function copySuggestedClause(idx) {
      if (lastContractReviewData && lastContractReviewData.review && lastContractReviewData.review.clause_reviews) {
        const c = lastContractReviewData.review.clause_reviews[idx];
        if (c && c.suggested_clause) {
          navigator.clipboard.writeText(c.suggested_clause).then(() => {
            showToast("已复制建议修订条款至剪贴板");
          });
        }
      }
    }

    let contractSourceFileId = null;

    async function handleContractSourceFileSelect(event) {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      showToast("正在上传并解析原合同 (.docx)...");
      try {
        const formData = new FormData();
        formData.append('file', file);
        const resp = await api.request(`${API_BASE}/api/v1/phase2/contract-review/upload-source`, {
          method: 'POST',
          body: formData
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        contractSourceFileId = data.source_file_id;
        const badge = document.getElementById('cr-source-file-badge');
        if (badge) {
          badge.innerText = `已挂载原合同: ${file.name} (原位修订已就绪)`;
          badge.style.color = '#059669';
          badge.style.fontWeight = '600';
        }
        showToast("原合同上传成功，导出审查文档时将执行原位修订！");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    async function exportRedlineDocx() {
      const title = document.getElementById('cr-contract-title').value.trim() || "商业技术开发与采购合同";
      const perspective = document.getElementById('cr-perspective').value;
      const playbookKey = document.getElementById('cr-playbook').value;
      const contractText = document.getElementById('cr-contract-text').value.trim();

      const btn = document.getElementById('btn-export-redline');
      const origText = btn ? btn.innerHTML : "";
      if (btn) {
        btn.innerHTML = `<span class="spinner-dark"></span> 正在导出...`;
        btn.disabled = true;
      }

      showToast("正在生成带 Word 原生修订模式 (<w:ins>/<w:del>) 的 .docx 文档...");

      try {
        const payload = {
          contract_title: title,
          contract_text: contractText,
          perspective: perspective,
          playbook_preset: playbookKey,
          source_file_id: contractSourceFileId || null,
          clause_reviews: lastContractReviewData ? (lastContractReviewData.review || {}).clause_reviews : null,
          overall_risk_level: lastContractReviewData ? (lastContractReviewData.review || {}).overall_risk_level : "中",
          review_summary: lastContractReviewData ? (lastContractReviewData.review || {}).review_summary : "",
          playbook_compliance_score: lastContractReviewData ? (lastContractReviewData.review || {}).playbook_compliance_score : 85
        };

        const resp = await api.request(`${API_BASE}/api/v1/phase2/contract-review/export-redline`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        if (!resp.ok) {
          const errJson = await resp.json().catch(() => null);
          throw new Error(errJson?.detail || ('HTTP ' + resp.status));
        }
        const d = await resp.json();
        if (btn) {
          btn.innerHTML = origText;
          btn.disabled = false;
        }

        if (d.status === 'success' && d.download_url) {
          const a = document.createElement('a');
          a.href = withDownloadToken(d.download_url);
          a.download = d.filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          if (contractSourceFileId) {
            const revCount = d.revisions_count !== undefined ? d.revisions_count : 0;
            const unmatchCount = (d.unmatched_clauses || []).length;
            showToast(`已在原文中插入 ${revCount} 处修订，${unmatchCount} 条未定位`);
          } else {
            showToast("未上传原文档，导出为新生成文档，非原位修订");
          }
        } else {
          showToast("导出失败: " + (d.message || "未知错误"));
        }
      } catch (e) {
        if (btn) {
          btn.innerHTML = origText;
          btn.disabled = false;
        }
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function copyPhase2ActiveContent() {
      const paneOutline = document.getElementById('p2-pane-outline');
      const paneDiff = document.getElementById('p2-pane-diff');
      if (paneOutline && paneOutline.style.display !== 'none') {
        copyElementText('to-outline-result', '已复制五模块庭审提纲');
      } else if (paneDiff && paneDiff.style.display !== 'none') {
        if (lastVersionCompareData) {
          navigator.clipboard.writeText(JSON.stringify(lastVersionCompareData, null, 2)).then(() => showToast("已复制版本比对分析结果"));
        } else {
          showToast("暂无可复制的比对数据");
        }
      } else {
        if (lastContractReviewData && lastContractReviewData.review) {
          const text = JSON.stringify(lastContractReviewData.review, null, 2);
          navigator.clipboard.writeText(text).then(() => showToast("已复制审查结构化数据"));
        } else {
          showToast("请先执行合同红线审查");
        }
      }
    }

    // =========================================================================
    // 4.2 模块 03：多版本合同条款对齐与偏离度比对 (Multi-Version & Deviation Diff)
    // =========================================================================
    let lastVersionCompareData = null;

    function switchContractReviewMode(mode) {
      const btnSingle = document.getElementById('btn-cr-mode-single');
      const btnDiff = document.getElementById('btn-cr-mode-diff');
      const viewSingle = document.getElementById('cr-view-single');
      const viewDiff = document.getElementById('cr-view-diff');

      if (mode === 'diff') {
        btnDiff?.classList.add('active');
        btnSingle?.classList.remove('active');
        if (viewDiff) viewDiff.style.display = 'block';
        if (viewSingle) viewSingle.style.display = 'none';
        switchPhase2RightTab('diff');
      } else {
        btnSingle?.classList.add('active');
        btnDiff?.classList.remove('active');
        if (viewSingle) viewSingle.style.display = 'block';
        if (viewDiff) viewDiff.style.display = 'none';
        switchPhase2RightTab('redline');
      }
    }

    function loadVersionDiffPreset() {
      document.getElementById('diff-base-title').value = "《企业间借款合同·律所标准母本版》";
      document.getElementById('diff-base-text').value = `第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限自2025年1月10日起至2026年1月9日止。
第三条 借款利息：年利率固定为12%，按季度结息，逾期每日加收万分之五罚息。
第四条 保证担保：丙方（自然人股东）承担不可撤销的无限连带责任保证，保证范围涵盖本息、违约金及追偿实现债权的所有诉讼费与律师费。
第五条 争议解决：因履行本合同引起的争议，由出借人所在地人民法院管辖。`;

      document.getElementById('diff-target-title').value = "《企业间借款合同·借款人修订草案》";
      document.getElementById('diff-target-text').value = `第一条 借款金额：借款金额为人民币5,000,000.00元整。
第二条 借款期限：借款期限经双方协商延长至2026年7月9日止。
第三条 借款利息：年利率固定为6%，到期一次性还本付息，取消逾期罚息条款。
第五条 争议解决：发生争议由中国国际经济贸易仲裁委员会北京分会仲裁。
第六条 提前还款：借款人有权提前偿还全部或部分本金，且不承担任何违约赔偿责任。`;
      showToast("已载入商业借贷合同母本 vs 相对方争议修改稿！");
    }

    async function runVersionCompareUI() {
      const baseTitle = document.getElementById('diff-base-title')?.value.trim() || "基准版本";
      const baseText = document.getElementById('diff-base-text')?.value.trim();
      const targetTitle = document.getElementById('diff-target-title')?.value.trim() || "相对方修改版";
      const targetText = document.getElementById('diff-target-text')?.value.trim();

      if (!baseText || !targetText) {
        showToast("请同时输入基准母本条款与相对方修订条款！");
        return;
      }

      const btn = document.getElementById('btn-run-version-diff');
      let origHtml = '';
      if (btn) {
        origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-dark"></span> 正在智能对齐条款与计算偏离度...`;
        btn.disabled = true;
      }
      switchPhase2RightTab('diff');

      const container = document.getElementById('version-diff-container');
      if (container) {
        container.innerHTML = `<div style="text-align:center; padding: 40px; color: var(--text-muted);"><span class="spinner-dark"></span> 正在对齐条款结构、计算红线偏离度与生成 Diff...</div>`;
      }

      try {
        const resp = await api.request(`${API_BASE}/api/v1/contract/compare-versions`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            base_title: baseTitle,
            base_text: baseText,
            target_title: targetTitle,
            target_text: targetText
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        lastVersionCompareData = data.comparison;
        renderVersionDiffResult(data.comparison);
        showToast("多版本条款对齐比对完成！合规指数: " + data.comparison.stats.deviation_score + "分");
      } catch (e) {
        if (container) {
          container.innerHTML = `<div style="color: #DC2626; padding: 20px;">比对失败: ${escapeHtml(e)}</div>`;
        }
        showToast("比对请求异常: " + e);
      } finally {
        if (btn) {
          btn.innerHTML = origHtml;
          btn.disabled = false;
        }
      }
    }

    function renderVersionDiffResult(cmp) {
      const container = document.getElementById('version-diff-container');
      if (!container || !cmp) return;
      const stats = cmp.stats || {};
      const clauses = cmp.aligned_clauses || [];

      const scoreColor = stats.deviation_score >= 80 ? '#15803D' : (stats.deviation_score >= 60 ? '#D97706' : '#DC2626');
      const scoreBg = stats.deviation_score >= 80 ? '#DCFCE7' : (stats.deviation_score >= 60 ? '#FEF3C7' : '#FEE2E2');

      const statusBadges = {
        'UNCHANGED': { label: '一致保留', bg: '#DCFCE7', color: '#15803D' },
        'MODIFIED': { label: '实质修改', bg: '#FEF3C7', color: '#B45309' },
        'DELETED': { label: '相对方删除 (高风险)', bg: '#FEE2E2', color: '#DC2626' },
        'ADDED': { label: '相对方新增条款', bg: '#F3E8FF', color: '#7E22CE' }
      };

      let html = `
        <div style="background: #FFFFFF; border: 1px solid var(--border-hairline); border-radius: var(--radius-sm); padding: 14px 16px; margin-bottom: 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
            <div>
              <div style="font-size: 14px; font-weight: 700; color: var(--primary-navy);">
                ${escapeHtml(cmp.base_title)} <span style="color: var(--text-muted); font-size: 12px;">VS</span> ${escapeHtml(cmp.target_title)}
              </div>
              <div style="font-size: 11.5px; color: var(--text-secondary); margin-top: 3px;">
                对齐条款共 ${stats.total_aligned_clauses || 0} 项 · 条款总变动率 ${stats.clause_change_rate || 0}%
              </div>
            </div>
            <div style="text-align: right; background: ${scoreBg}; padding: 6px 14px; border-radius: 6px; border: 1px solid ${scoreColor}40;">
              <div style="font-size: 10.5px; color: ${scoreColor}; font-weight: 600;">模板遵从合规指数</div>
              <div style="font-size: 22px; font-weight: 800; color: ${scoreColor}; font-family: var(--font-mono); line-height: 1.1;">
                ${stats.deviation_score}<span style="font-size: 12px; font-weight: normal;">/100</span>
              </div>
            </div>
          </div>

          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 11.5px;">
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 6px 10px; text-align: center;">
              <span style="color: var(--text-muted);">一致保留条款</span><br/>
              <strong style="color: #15803D; font-size: 14px;">${stats.unchanged_count || 0}</strong>
            </div>
            <div style="background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 4px; padding: 6px 10px; text-align: center;">
              <span style="color: #92400E;">实质性变动</span><br/>
              <strong style="color: #D97706; font-size: 14px;">${stats.modified_count || 0}</strong>
            </div>
            <div style="background: #FEF2F2; border: 1px solid #FECDD3; border-radius: 4px; padding: 6px 10px; text-align: center;">
              <span style="color: #991B1B;">关键条款遭删除</span><br/>
              <strong style="color: #DC2626; font-size: 14px;">${stats.deleted_count || 0}</strong>
            </div>
            <div style="background: #FAF5FF; border: 1px solid #E9D5FF; border-radius: 4px; padding: 6px 10px; text-align: center;">
              <span style="color: #6B21A8;">相对方新增条款</span><br/>
              <strong style="color: #7E22CE; font-size: 14px;">${stats.added_count || 0}</strong>
            </div>
          </div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 10px;">
      `;

      clauses.forEach((c, idx) => {
        const sInfo = statusBadges[c.status] || { label: c.status, bg: '#F1F5F9', color: '#475569' };
        const statusClass = 'status-' + (c.status || '').toLowerCase();

        html += `
          <div class="diff-version-card ${statusClass}">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
              <div style="display: flex; align-items: center; gap: 8px;">
                <span style="font-weight: 700; font-size: 13px; color: var(--primary-navy);">
                  ${idx + 1}. ${escapeHtml(c.base_title || c.target_title || '未命名条款')}
                </span>
                <span class="badge" style="background: ${sInfo.bg}; color: ${sInfo.color}; font-size: 10.5px; font-weight: 600;">
                  ${sInfo.label}
                </span>
              </div>
              <span style="font-size: 11px; color: var(--text-muted); font-family: var(--font-mono);">
                对齐相似度: ${Math.round((c.similarity || 0) * 100)}%
              </span>
            </div>

            ${c.status === 'DELETED' ? `
              <div style="background: #FFF; border: 1px dashed #DC2626; border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; font-size: 12px; color: #DC2626; line-height: 1.5;">
                <strong style="color: #991B1B;">⚠️ 相对方删除了原母本条款：</strong><br/>
                <del class="diff-del">${escapeHtml(c.base_text || '')}</del>
              </div>
              <div style="font-size: 11.5px; color: #B91C1C; background: #FEF2F2; padding: 4px 8px; border-radius: 4px;">
                🚨 法律风险提示：该条款遭删除将导致债权担保或违约追偿权利充分丧失，严禁直接妥协！
              </div>
            ` : ''}

            ${c.status === 'ADDED' ? `
              <div style="background: #FFF; border: 1px dashed #7E22CE; border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; font-size: 12px; color: #6B21A8; line-height: 1.5;">
                <strong style="color: #581C87;">➕ 相对方单方新增条款：</strong><br/>
                <ins class="diff-ins">${escapeHtml(c.target_text || '')}</ins>
              </div>
              <div style="font-size: 11.5px; color: #6B21A8; background: #FAF5FF; padding: 4px 8px; border-radius: 4px;">
                ℹ️ 审查建议：该条款为对方新增抗辩或减轻履约责任之约定，需核查是否对己方构成不当限制。
              </div>
            ` : ''}

            ${c.status === 'MODIFIED' ? `
              <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 4px; padding: 8px 10px; margin-bottom: 6px; font-size: 12px; line-height: 1.7;">
                <div style="font-size: 10.5px; color: var(--text-muted); margin-bottom: 4px;">红线修订对齐比对 (删除线为原母本，下划线为对方修改)：</div>
                <div>${c.diff_html || escapeHtml(c.target_text || '')}</div>
              </div>
            ` : ''}

            ${c.status === 'UNCHANGED' ? `
              <div style="font-size: 11.5px; color: var(--text-secondary); line-height: 1.5; background: #F8FAFC; padding: 6px 10px; border-radius: 4px;">
                ${escapeHtml(c.target_text || c.base_text || '')}
              </div>
            ` : ''}
          </div>
        `;
      });

      html += `</div>`;
      container.innerHTML = html;
    }

    async function exportVersionDiffDocxUI() {
      const baseTitle = document.getElementById('diff-base-title')?.value.trim() || "基准母本";
      const baseText = document.getElementById('diff-base-text')?.value.trim();
      const targetTitle = document.getElementById('diff-target-title')?.value.trim() || "相对方修改版";
      const targetText = document.getElementById('diff-target-text')?.value.trim();

      if (!baseText || !targetText) {
        showToast("请先输入待比对的双方合同条款！");
        return;
      }

      const btn = document.getElementById('btn-export-version-diff');
      let origHtml = '';
      if (btn) {
        origHtml = btn.innerHTML;
        btn.innerHTML = `<span class="spinner-dark"></span> 正在生成 Word 修订稿...`;
        btn.disabled = true;
      }
      showToast("正在将双版本条款变更写入 Word 原生修订标签 (<w:ins>/<w:del>)...");

      try {
        const resp = await api.request(`${API_BASE}/api/v1/contract/export-version-diff`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            base_title: baseTitle,
            base_text: baseText,
            target_title: targetTitle,
            target_text: targetText
          })
        });
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const res = await resp.json();
        if (res.download_url) {
          const a = document.createElement('a');
          a.href = withDownloadToken(res.download_url);
          a.download = res.filename || "contract_version_diff.docx";
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          showToast(`已成功导出 ${res.filename}，Word 中可直接查看原生修订标记！`);
        }
      } catch (e) {
        showToast("导出比对文档失败: " + e);
      } finally {
        if (btn) {
          btn.innerHTML = origHtml;
          btn.disabled = false;
        }
      }
    }


    async function runAutoEvidenceCatalogUI() {
      const cause = document.getElementById('ev-catalog-cause')?.value.trim() || ((activeMatterData && activeMatterData.cause_of_action) || "民间借贷纠纷");
      const plaintiff = document.getElementById('ev-catalog-plaintiff')?.value.trim() || ((activeMatterData && activeMatterData.plaintiff_name) || "原告");
      const notes = document.getElementById('ev-catalog-notes')?.value.trim() || "";
      if (!notes) {
        showToast("请填写原始证据碎片清单或卷宗提取文字！");
        return;
      }
      showToast("正在提炼四要素并生成《证据目录.docx》...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/auto-catalog`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            cause_of_action: cause,
            plaintiff_name: plaintiff,
            evidence_notes: notes
          })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderEvidenceCatalogResult(data);
        switchPhase2RightTab('tools');
        showToast("《证据目录.docx》已生成完毕");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function renderEvidenceCatalogResult(data) {
      const container = document.getElementById('ev-tools-result-container');
      if (!container) return;
      const items = data.extracted_items || [];
      const rowsHtml = items.map((it, idx) => `
        <tr style="border-bottom: 1px solid var(--border-hairline);">
          <td style="padding: 6px 8px; font-weight: 600;">${escapeHtml(String(idx + 1))}</td>
          <td style="padding: 6px 8px; font-weight: 700; color: var(--primary-navy);">${escapeHtml(it.name || '')}</td>
          <td style="padding: 6px 8px;"><span class="badge" style="background:#E0F2FE; color:#0369A1; font-size:11px;">${escapeHtml(it.category || '')}</span></td>
          <td style="padding: 6px 8px; font-size: 11.5px;">${escapeHtml(it.source || '')}</td>
          <td style="padding: 6px 8px; font-size: 11.5px; color: var(--text-secondary);">${escapeHtml(it.purpose || '')}</td>
          <td style="padding: 6px 8px; font-family: var(--font-mono); font-size: 11px;">${escapeHtml(it.pages || '')}</td>
        </tr>
      `).join('');
      const downloadBtn = data.download_url
        ? `<a href="${withDownloadToken(data.download_url)}" download="${escapeHtml(data.catalog_filename || '证据目录.docx')}" class="btn btn-amber btn-sm" style="text-decoration:none;">📥 下载《证据目录.docx》</a>`
        : '';
      container.innerHTML = ` // safe-html: catalog summary table and download link
        <div style="padding: 12px 14px;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 12px; flex-wrap:wrap; gap:8px;">
            <div>
              <strong style="font-size: 14px; color: var(--primary-navy);">《法庭规范证据目录（共 ${escapeHtml(String(items.length))} 项）》</strong>
              <div style="font-size: 11.5px; color: var(--text-muted); margin-top:2px;">依据《民事诉讼法》证据规则自动提炼并按规范四要素排版</div>
            </div>
            <div>${downloadBtn}</div>
          </div>
          <table style="width:100%; border-collapse: collapse; font-size:12px;">
            <thead>
              <tr style="background:#F1F5F9; border-bottom: 1px solid #CBD5E1; text-align:left;">
                <th style="padding: 6px 8px; width:36px;">序号</th>
                <th style="padding: 6px 8px;">证据名称</th>
                <th style="padding: 6px 8px; width:70px;">证据种类</th>
                <th style="padding: 6px 8px; width:90px;">证据来源</th>
                <th style="padding: 6px 8px;">证明目的</th>
                <th style="padding: 6px 8px; width:70px;">页码</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      `;
    }

    async function runCrossExaminationUI() {
      const evName = document.getElementById('ev-cross-name')?.value.trim() || "借款证据";
      const evCat = document.getElementById('ev-cross-category')?.value || "书证";
      const oppPurpose = document.getElementById('ev-cross-purpose')?.value.trim() || "";
      const clientFacts = document.getElementById('ev-cross-facts')?.value.trim() || "";
      showToast("正在生成证据三性审查与反驳意见...");
      try {
        const resp = await api.request(`${API_BASE}/api/v1/phase2/cross-examination`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            evidence_name: evName,
            evidence_category: evCat,
            opponent_purpose: oppPurpose,
            client_facts: clientFacts
          })
        });
        if (!resp.ok) {
          const err = await resp.json().catch(() => null);
          throw new Error(err?.detail || ('HTTP ' + resp.status));
        }
        const data = await resp.json();
        renderCrossExaminationResult(data);
        switchPhase2RightTab('tools');
        showToast("质证意见已生成");
      } catch (e) {
        showToast(err instanceof ApiError ? err.userMessage : (err && err.userMessage ? err.userMessage : `操作失败：${err.message || "请求异常"}（错误码 CLIENT_ERROR）`), "error");
      }
    }

    function renderCrossExaminationResult(data) {
      const container = document.getElementById('ev-tools-result-container');
      if (!container) return;
      const parsed = data.cross_examination || {};
      const auth = parsed.authenticity || parsed.真实性 || '对真实性不予认可（对方未出示原件且存在涂改存疑）';
      const leg = parsed.legality || parsed.合法性 || '对合法性提出异议（取证形式不合法或违反强制性规定）';
      const rel = parsed.relevance || parsed.关联性 || '对关联性与证明目的不予认可（证据内容无法达到对方证明主张）';
      const conc = parsed.conclusion || parsed.综合质证结论 || '综上所述，该证据不具备证据三性，依法不能作为定案依据。';
      container.innerHTML = ` // safe-html: cross examination cards and text
        <div style="padding: 12px 14px;">
          <div style="margin-bottom: 12px;">
            <strong style="font-size: 14px; color: var(--primary-navy);">《证据三性法庭质证意见与反驳论点》</strong>
            <div style="font-size: 11.5px; color: var(--text-muted); margin-top:2px;">真实性 (Authenticity) · 合法性 (Legality) · 关联性 (Relevance)</div>
          </div>
          <div style="display:flex; flex-direction:column; gap:8px;">
            <div style="border-left: 3px solid #EF4444; background: #FEF2F2; padding: 8px 12px; border-radius: 4px;">
              <strong style="font-size:12px; color:#991B1B;">1. 真实性异议要点：</strong>
              <div style="font-size:11.5px; color:#7F1D1D; margin-top:3px; line-height:1.5;">${escapeHtml(String(auth))}</div>
            </div>
            <div style="border-left: 3px solid #F59E0B; background: #FFFBEB; padding: 8px 12px; border-radius: 4px;">
              <strong style="font-size:12px; color:#B45309;">2. 合法性审查要点：</strong>
              <div style="font-size:11.5px; color:#92400E; margin-top:3px; line-height:1.5;">${escapeHtml(String(leg))}</div>
            </div>
            <div style="border-left: 3px solid #3B82F6; background: #EFF6FF; padding: 8px 12px; border-radius: 4px;">
              <strong style="font-size:12px; color:#1D4ED8;">3. 关联性与证明力穿透：</strong>
              <div style="font-size:11.5px; color:#1E40AF; margin-top:3px; line-height:1.5;">${escapeHtml(String(rel))}</div>
            </div>
            <div style="border: 1px solid #CBD5E1; background: #F8FAFC; padding: 10px 12px; border-radius: 4px; margin-top: 4px;">
              <strong style="font-size:12px; color:var(--primary-navy);">⚖️ 法庭口头质证标准陈述意见：</strong>
              <div style="font-size:12px; color:var(--text-primary); margin-top:4px; line-height:1.6; font-family:var(--font-serif);">${escapeHtml(String(conc))}</div>
            </div>
          </div>
        </div>
      `;
    }



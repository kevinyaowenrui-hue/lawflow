# LawFlow 智律工作台 (LawFlow Workspace)

面向诉讼律师与企业法务的**本地优先**办案提效工作台：精算、文书流水线、证据整理、法条 FTS 检索、案件空间与可选云端大模型。

[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/kevinyaowenrui-hue/lawflow/actions/workflows/ci.yml/badge.svg)](https://github.com/kevinyaowenrui-hue/lawflow/actions/workflows/ci.yml)

---

## 功能概览（客观描述）

| 模块 | 说明 |
| :--- | :--- |
| 实务精算 | 人民币大写、身份证/信用代码校验、诉讼费分段、LPR 分段计息、劳动补偿 N/N+1/2N、时效与保全续封等 |
| 立案文书 | 按模板生成起诉状等 Word/PDF 打包下载 |
| 证据与庭审 | 合卷/贝茨码、敏感信息涂黑、证据目录、三性意见与庭审提纲（依赖大模型时需配置 Ollama 或云端） |
| 合同审查 | 红线手册对比，可导出带 Word 修订轨的稿件 |
| 法条库 | SQLite FTS5 关键词与条号检索、废止拦截、子母法关联（收录范围有限） |
| 类案检索 | 关键词/FTS 检索与咨询注入；**非**向量 RAG |
| 电子签约 | 可对接 DocuSeal；未配置时为**演示**签署流程 |
| 案件空间 | 卷宗挂载、图谱、阅卷表、工作流断点、任务看板 |
| 深度屏 | 要件推演、上诉审计、执行穿透等；部分场景在接入真实数据前为**演示** |

架构细节见 [ARCHITECTURE.md](ARCHITECTURE.md)；能力状态见 [ROADMAP.md](ROADMAP.md)。

---

## 已知限制

- **法条库**需律师核验；未核验条文不得当作权威全文引用。
- **判例库**默认可能为空；仅已核验案号可写入生成文书。
- **电子签约**在未配置 `DOCUSEAL_*` 时仅为演示，不具生产签署效力。
- **P3 / P4** 等攻防大屏在接入真实卷宗与财产线索前标注为演示。
- 检索为 **SQLite FTS5**，不是向量 RAG；外部向量引擎 / RAGFlow 为规划中、未使用。
- 可选 OCR/音频/HEIF 依赖见 `requirements-optional.txt`；缺失时自动降级。

---

## 快速启动

### 1. 环境准备

```bash
git clone https://github.com/kevinyaowenrui-hue/lawflow.git
cd lawflow

python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
# 可选能力（OCR / 音频 / HEIF）
# pip install -r requirements-optional.txt

copy .env.example .env
# 编辑 .env，至少设置 LAWFLOW_API_TOKEN=
```

### 2. 启动

```bash
python -m uvicorn gateway.main:app --host 127.0.0.1 --port 5221
```

浏览器打开：`http://127.0.0.1:5221`

也可使用仓库内 `start_gateway.bat`（优先项目 `.venv`）。

### 3. 测试

```bash
pip install -r requirements-dev.txt
python -m pytest
```

测试位于 `tests/`；CI 见 `.github/workflows/ci.yml`。

### 4. Docker（可选）

```bash
# 需已填写 .env 中的 LAWFLOW_API_TOKEN
docker compose up --build
# 映射 127.0.0.1:5221
```

Docassemble、RAGFlow 等为**规划中，当前代码未使用**（compose profile `planned`）。电子签容器：`docker compose --profile phase3 up`（需设置 `DOCUSEAL_WEBHOOK_SECRET`）。

---

## 当前不支持的功能 (MVP 边界说明)

LawFlow 智律工作台当前聚焦于单律师/团队在办案件的实务精算、起诉立案公文包生成、证据三性梳理与法条防幻觉熔断。以下大型律所与企业法务协同管理功能在当前 MVP 范围内**暂不支持**：
1. **计费工时**：律师工时记录、计费费率核算与客户对账账单；
2. **多人协作与权限**：团队成员角色权限分级 (RBAC)、跨团队分案与权限隔离；
3. **文书审批与用印**：律所公章用印流转、文书多级审核与合伙人审批流；
4. **企业法务合同台账与审批流**：企业内部采购/销售合同台账台账化归档与全流程审批；
5. **外聘律所管理**：外聘律所库名录准入、选聘评估与委托考核评价。

---

## 开源许可证

本项目附带 [MIT License](LICENSE)。若仓库已转为私有且不打算开源，请业主自行决定是否删除 `LICENSE` 与 README 中的 MIT 徽章。

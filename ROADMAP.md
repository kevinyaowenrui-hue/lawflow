# LawFlow 智律工作台 —— 能力状态看板 (ROADMAP)

> 状态标注约定：**已实现** / **演示** / **计划**。  
> 与代码、`ARCHITECTURE.md` 不一致时以代码为准。网关端口统一为 **5221**。

---

## 总览

| 能力域 | 状态 | 说明 |
| :--- | :---: | :--- |
| 工程底座（FastAPI + SPA + SQLite） | **已实现** | 路径由 `LAWFLOW_*` 环境变量配置 |
| 本土法律计算器（金额/身份证/诉讼费/LPR/劳动补偿等） | **已实现** | 确定性算法，见 `/api/v1/phase1/calc/lpr-interest` 等 |
| 立案文书 Word/PDF 流水线 | **已实现** | `/api/v1/phase1/generate-litigation-package` |
| 证据合卷、脱敏、目录、庭审提纲 | **已实现** | 如 `/api/v1/phase2/process-evidence`；OCR 可选依赖缺失时降级 |
| 合同红线审查与修订轨导出 | **已实现** | `/api/v1/phase2/contract-review` |
| 法条 FTS5 检索与子母法图谱 | **已实现** | 如 `/api/v1/statutes/search`；库需律师核验 |
| 类案关键词检索与咨询 | **已实现** | `/api/v1/phase3/rag/search`（关键词/FTS，非向量） |
| 电子签约 DocuSeal | **演示** | 未配置真实 DocuSeal 时为演示信封；接入真实数据前保持演示 |
| P3 二审/类案分歧攻防屏 | **演示** | `/api/v1/litigation/appeal-audit` 等；样例数据为演示 |
| P4 执行穿透与追加被执行人 | **演示** | `/api/v1/enforcement/penetration-audit`；样例金额为演示 |
| 案件空间 / 阅卷表 / 语音中枢 | **已实现** | 如 `/api/v1/vault/matters`、`/api/v1/copilot/tasks` |
| Docassemble 问卷 | **计划** | compose profile `planned`；代码未调用 |
| 向量 RAG 引擎 | **计划** | 未使用 |
| Docker 官方镜像 digest 锁定 | **计划** | 版本标签已钉住；digest 待业主核对 |

---

## 阶段拆解

### 底座 — **已实现**

- [x] 四层目录与 `gateway.core.paths` 路径集中化
- [x] `docker-compose.yml`（端口 5221；弱口令默认值已移除）
- [x] `.env.example` 与 `LAWFLOW_API_TOKEN` 鉴权
- [x] CI：`.github/workflows/ci.yml` + `tests/`

### 阶段一：立案与精算 — **已实现**

- [x] `gateway/utils/cn_legal_calc.py` 等计算器
- [x] `templates/` 文书模板与阶段一路由（如 `/api/v1/phase1/generate-litigation-package`）
- [x] `gateway/core/ollama_client.py`（本地 Ollama + 可选云端）

### 阶段二：证据与庭审 — **已实现**

- [x] `/api/v1/phase2/process-evidence` 合卷与贝茨码
- [x] `/api/v1/phase2/auto-catalog` 证据目录
- [x] `/api/v1/phase2/cross-examination` 三性意见
- [x] `/api/v1/phase2/trial-outline` 庭审提纲
- [x] 兼容别名（schema 外）：`/api/evidence/cross-examination`、`/api/evidence/trial-outline`

### 阶段三：检索与签约 — **已实现**（签约为 **演示**）

- [x] `/api/v1/phase3/rag/search`、`/api/v1/phase3/rag/consult`
- [x] `/api/v1/phase3/create-signing-link`、`/api/v1/phase3/signing-webhook`
- [ ] 真实 DocuSeal 生产对接与存证审计 — **计划**

### 深度实务屏 — **演示** / 部分 **已实现**

- [x] P0 英文合同修订轨 — **已实现**
- [x] P1 视觉切片与和解 NPV — **已实现**（依赖卷宗原件）
- [x] P2 法定冲抵与保证期间 — **已实现**
- [x] P3 上诉审计 — **演示**（接入真实卷宗前）
- [x] P4 执行穿透 — **演示**（接入真实财产线索前）

### 规划中 — **计划**

- [ ] Docassemble 引导式问卷（官方镜像 `jhpyle/docassemble`，profile `planned`）
- [ ] 外部向量检索引擎（规划中，未使用）替代或增强 FTS5
- [ ] 镜像 `@sha256` digest 锁定

---

## 验证方式

```bash
pip install -r requirements-dev.txt
python -m pytest
```

全量套件以 `tests/` 与 CI 为准；网关端口统一为 5221。

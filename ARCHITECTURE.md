# LawFlow 智律工作台 —— 四层解耦系统架构设计

> 面向中国执业律师的本地私有化办案提效中枢系统。基于本地大模型 `gemma4:12b` 与中国司法实务规则构建，实现从客户咨询、立案计算、起诉文书生成、证据链梳理质证到类案检索与电子签约的全流程闭环。

---

## 一、系统整体四层架构图

```mermaid
graph TD
    subgraph Layer1["1. 表现层 (Presentation Layer)"]
        UI["LawFlow 现代化律师工作台 (Web UI / SPA)<br/>端口: 5221<br/>纯原生系统字体 | 暗黑律所调性 | Zero-Jank 零卡顿"]
        Tab1["诉讼与本土计算工具箱"]
        Tab2["智能文书自动流水线"]
        Tab3["证据链梳理与质证 Agent"]
        Tab4["类案 RAG 检索与电子签约"]
        UI --> Tab1
        UI --> Tab2
        UI --> Tab3
        UI --> Tab4
    end

    subgraph Layer2["2. 编排网关层 (Orchestration Gateway Layer)"]
        GW["FastAPI 法律本土化编排网关 (端口: 5221)"]
        R1["阶段一路由: phase1_litigation<br/>诉讼计算 & 文书渲染"]
        R2["阶段二路由: phase2_evidence<br/>证据OCR & 质证提纲 Agent"]
        R3["阶段三路由: phase3_rag_sign<br/>私有类案检索 & 电子签约"]
        GW --> R1
        GW --> R2
        GW --> R3
    end

    subgraph Layer3["3. 引擎与服务层 (Engine & Utility Services)"]
        Calc["cn_legal_calc 精算法律数学引擎<br/>• 人民币大写规范转换<br/>• 18位二代身份证全校验<br/>• 《诉讼费用交纳办法》分段计费<br/>• 2019-2026年央行 LPR 历期分段计息<br/>• 《劳动合同法》N/N+1/2N 补偿金"]
        Docx["Word/Jinja2 司法文书渲染器<br/>• GB/T 9704-2012 公文排版规范<br/>• 方正小标宋/仿宋字体适配<br/>• docxtpl 动态表格与段落组装"]
        OCR["证据 OCR 与清洗引擎<br/>• 银行流水/微信记录/合同扫描件提取<br/>• 证据要素化 (名称/类型/目的/形成时间)"]
        Prompts["claude-for-legal-ZH 司法提示词库<br/>• 事实理由规范化提炼<br/>• 证据三性审查意见生成<br/>• 庭审发问提纲与举证焦点拆解"]
    end

    subgraph Layer4["4. 模型与基础设施层 (Model & Infrastructure Layer)"]
        Ollama["宿主机 Ollama 引擎<br/>http://host.docker.internal:11434<br/>• 主力大模型: gemma4:12b (262k 上下文)<br/>• 向量模型: embeddinggemma / nomic-embed-text"]
        Docassemble["Docassemble (可选 Profile: phase1)<br/>端口: 5223 引导式法律问卷系统"]
        DocuSeal["DocuSeal (可选 Profile: phase3)<br/>端口: 5224 私有化电子合同签署"]
        VectorDB["向量检索索引 (Qdrant/Local)<br/>端口: 5225 私有裁判文书与法律条文库"]
        Storage["本地安全存储卷<br/>• templates/ 文书模板库<br/>• storage/generated/ 密级文书导出<br/>• fonts/ 法院标准中文字体库"]
    end

    Layer1 ==>|RESTful API / JSON| Layer2
    Layer2 ==> Layer3
    Layer3 ==> Layer4
    Layer2 ==>|异步长文本推理| Ollama
    Layer2 ==>|电子签约调度| DocuSeal
```

---

## 二、端口映射与服务注册表

系统严格遵循全局端口隔离规范与私有化通信原则：

| 服务名称 | 编排/Profile | 内部端口 | 宿主机映射端口 | 监听地址 | 用途说明 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **LawFlow Gateway & Web** | 默认必启 (base) | `8000` | **8000** (或本地5221) | `127.0.0.1` | FastAPI 统一网关中枢与前端 SPA 静态界面 |
| **Stirling-PDF** | 默认必启 (base) | `8080` | **8081** | `127.0.0.1` | 司法文书 PDF 转换、合并、印章与 OCR 中间件 |
| **Docassemble** | `phase1` | `80` | **8080** | `127.0.0.1` | 引导式民事起诉问卷采访服务 (挂载 fonts 目录) |
| **DocuSeal** | `phase3` | `3000` | **8082** | `127.0.0.1` | 私有化电子签名与委托合同流转加签平台 |
| **RAGFlow** | `phase3` (预留) | `9380` | `9380` | `127.0.0.1` | 外部 RAGFlow 容器网络接口 (`ragflow-net`) |
| **Host Ollama Server** | 宿主机系统服务 | `11434` | **11434** | `127.0.0.1` | 本地大模型服务 (`gemma4:12b`, `embeddinggemma`) |

> [!IMPORTANT]
> - 本地原生开发时网关可同时支持 `8000` 或 `5221` 端口启动，容器化编排严格按照 `8000 / 8081 / 8080 / 8082` 分阶段映射。
> - 所有对外暴露的 Web 服务一律显式绑定 `127.0.0.1`，坚决杜绝直接暴露公网导致律所办案数据外泄。

---

## 三、四大核心业务流转机制

### 1. 诉讼立案文书流水线 (Phase 1)
```mermaid
sequenceDiagram
    autonumber
    actor Lawyer as 执业律师
    participant UI as 前端工作台 (SPA)
    participant GW as 编排网关 (FastAPI)
    participant Calc as cn_legal_calc 引擎
    participant LLM as 本地 Ollama (gemma4:12b)
    participant Docx as docxtpl 渲染引擎

    Lawyer->>UI: 输入原被告信息、诉讼请求及基本案情
    UI->>GW: 提交结构化立案请求
    GW->>Calc: 校验身份证号并计算诉讼标的大写、诉讼费分段数额
    Calc-->>GW: 返回精确计算指标 (免去人工计算误差)
    GW->>LLM: 注入 legal_prompts 生成逻辑严密的《事实与理由》段落
    LLM-->>GW: 返回符合法庭公文规范的事实与理由
    GW->>Docx: 组装数据并载入 templates/*.docx 标准模板渲染
    Docx-->>GW: 生成标准的 Word (.docx) 文件
    GW-->>UI: 返回预览数据与可一键下载的 docx 文档链接
    UI-->>Lawyer: 律师审核并在 Word 中微调后直接打印盖章提交法院
```

### 2. 证据链清洗与质证 Agent 流水线 (Phase 2)
```mermaid
sequenceDiagram
    autonumber
    actor Lawyer as 执业律师
    participant UI as 前端工作台 (SPA)
    participant GW as 编排网关 (FastAPI)
    participant OCR as OCR 提取引擎
    participant LLM as 本地 Ollama (gemma4:12b)
    participant Docx as 证据清单渲染器

    Lawyer->>UI: 上传证据图片/PDF/聊天记录截图
    UI->>GW: 提交多模态证据包
    GW->>OCR: 执行文字提取与图文关键要素分块
    OCR-->>GW: 提取原始文本 (如微信转账单号、时间、合同盖章)
    GW->>LLM: 调度【证据三性审查 Agent】，根据举证目的提炼质证要点
    LLM-->>GW: 产出结构化质证意见 (真实性、合法性、关联性及证明力瑕疵)
    GW->>Docx: 自动编排并填充《证据目录与证明目的清单.docx》
    Docx-->>GW: 输出符合各级法院立案庭要求的标准证据清单
    GW-->>UI: 呈现可视化质证清单，可导出庭审发问提纲
```

### 3. 私有类案 RAG 检索与电子签约流水线 (Phase 3)
```mermaid
sequenceDiagram
    autonumber
    actor Client as 当事人 / 客户
    actor Lawyer as 执业律师
    participant UI as 前端工作台 (SPA)
    participant GW as 编排网关 (FastAPI)
    participant RAG as 向量数据库 & 法条库
    participant DocuSeal as 私有 DocuSeal 服务

    Lawyer->>UI: 输入案情核心争议与法律要件
    UI->>GW: 触发私有类案检索
    GW->>RAG: 本地向量检索最高法指导性案例与裁判规则
    RAG-->>GW: 返回关联裁判要点与法律条文
    GW-->>UI: 输出精准法条援引与同类裁判说理指引
    Lawyer->>UI: 确定代理方案并生成《民事委托代理协议》
    UI->>GW: 触发电子签署工作流
    GW->>DocuSeal: 创建私有签署 Envelope 并生成安全签名链接
    DocuSeal-->>Client: 短信/链接提醒当事人在线人脸与手写签名
    Client-->>DocuSeal: 完成在线签署（若已接入真实 DocuSeal；否则为演示模式）
    DocuSeal-->>GW: 签署完成回调通知
    GW-->>UI: 归档已签署 PDF 委托书
```

---

## 四、安全合规与私有化保障

1. **绝对离线与隐私保护 (Zero Cloud Leaks)**:
   - 所有办案文书、当事人身份证、财务流水仅在律所内网/本地 Docker 存储卷中处理，不调用任何公网商业大模型 API。
   - 大模型直接运行在本地宿主机 Ollama（`gemma4:12b`），推理完全本地化。
2. **司法排版绝对合规 (Judicial Typography Standards)**:
   - 严格遵循《党政机关公文格式》(GB/T 9704-2012) 与最高人民法院裁判文书排版习惯。
   - 标题：二号方正小标宋简体 / 黑体；
   - 正文：三号仿宋_GB2312，首行缩进 2 字符，固定行距 28-30 磅；
   - 容器内预置中文字体刷新机制，根绝 Linux Docker 容器生成 Word/PDF 乱码方块问题。
3. **法律算法零容差 (Mathematical Determinism)**:
   - 诉讼费、LPR利息、仲裁补偿金严格由纯 Python 确定性数学算法执行，杜绝大模型在涉及金额数字时的幻觉。

# 法院公文标准字体挂载与配置规范 (GB/T 9704-2012)

为确保 Linux 容器和微服务在生成 Word (.docx) 以及转码法庭证据 PDF 时完全杜绝中文乱码、排版走样或方块“口口口”乱码，系统将本目录挂载至容器内部字体目录。

---

## 一、推荐放置的标准中文字体文件

建议将以下标准 TrueType / OpenType 字体文件放入本 `fonts/` 目录：

| 字体文件名称 | 字体全称 | 司法文书标准用途 |
| :--- | :--- | :--- |
| `simfang.ttf` / `fangsong_GB2312.ttf` | 仿宋 / 仿宋_GB2312 | 正文专用（三号字，固定行距28-30磅） |
| `FZXiaoBiaoSong-B05S.ttf` / `simhei.ttf` | 方正小标宋简体 / 黑体 | 裁判文书/起诉状大标题（二号字） |
| `simsun.ttc` / `simsun.ttf` | 宋体 | 表格表头、证据目录文字 |
| `simkai.ttf` / `kaiti_GB2312.ttf` | 楷体 / 楷体_GB2312 | 引用法条、文书签发及批注 |

---

## 二、Docker 容器字体加载方案

根据 `gateway/Dockerfile` 配置：
1. 镜像构建阶段已安装 `fontconfig` 与 `libmagic1`；
2. 环境变量 `LAWFLOW_FONTS_DIR=/usr/share/fonts/truetype/custom`；
3. `docker-compose.yml` 将宿主机 `./fonts` 目录挂载至容器 `/usr/share/fonts/truetype/custom`；
4. 容器入口命令已配置启动自检刷新：
   ```sh
   fc-cache -f 2>/dev/null || true; exec uvicorn gateway.main:app --host 0.0.0.0 --port 5221
   ```
   启动时会自动扫描挂载目录并重建字体缓存。

---

## 三、缺少字体时的降级方案与排版差异说明

如果未向本目录放入上述中文字体文件：
1. **降级字体**：Linux 容器底层将回退到系统自带的英文或通用开源字体（如 DejaVu Sans、GNU FreeFont 或 generic sans-serif / serif）；
2. **显示与排版差异**：
   - PDF 渲染引擎（PyMuPDF / ReportLab / LibreOffice）将使用默认降级字形；
   - 字符宽度与标准仿宋/宋体不同，可能引起段落行高不符 GB/T 9704-2012 规范、表格列宽溢出折行；
   - 极端情况下生僻字可能出现缺字方块（“口口口”）；
3. **解决建议**：生产部署时强烈建议将 Windows 系统自带的仿宋、宋体、黑体、楷体字体文件（位于 `C:\Windows\Fonts`）复制至本仓库 `fonts/` 目录下后启动容器。

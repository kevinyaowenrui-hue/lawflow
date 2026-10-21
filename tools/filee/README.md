# Filee 离线转换引擎 (可选扩展组件)

本目录为 **Filee (KnifeLemon/Filee)** 命令行转码引擎的存放位置。

### 为什么使用 Filee？
Filee 是开源、免 Office、全本地离线运行的 244 种全格式转换器。将 Filee 引入 LawFlow 后，律师在处理非标证据（如特殊 CAD 图纸、涉外 HWP 文档、老旧矢量图、冷门音视频录音）时，无需经过任何公网云端即可在本地极速转为法院审判标准格式。

### 部署方法（可选）：
1. 访问 Filee 开源发布页：https://github.com/KnifeLemon/Filee/releases
2. 下载 Windows 便携版：`Filee-<version>-win-Portable.zip`
3. 将解压后的 `Filee.exe`（以及关联文件）放入此 `tools/filee/` 目录中：
   ```text
   tools/
     └── filee/
           ├── Filee.exe   <--- 核心执行程序
           └── ...
   ```
4. LawFlow 编排网关会自动检测到 `Filee.exe`，并无缝切换至 **Filee 增强转码模式**。

> [!NOTE]
> **无需安装也能正常使用**：即使未下载 Filee，LawFlow 自带的 **“司法内置快速转换引擎”** 亦已默认支持常用诉讼格式（包括 iPhone HEIC/HEIF 照片、TIFF、微信截图、Word 文档、银行流水表格、证据多图合卷 A4 加盖贝茨码、音频标准流等）。

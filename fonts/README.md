# 法院公文标准字体挂载规范 (GB/T 9704-2012)

为确保 Linux 容器生成 Word (.docx) 和转 PDF 时完全杜绝中文乱码、方块“口口口”或排版走样问题，系统将本目录直接挂载至容器内部 `/usr/share/fonts/truetype/custom`。

---

## 推荐放置的标准中文字体文件

| 字体文件名称 | 字体全称 | 司法文书用途 |
| :--- | :--- | :--- |
| `simfang.ttf` / `fangsong_GB2312.ttf` | 仿宋 / 仿宋_GB2312 | 正文专用（三号字，固定行距28-30磅） |
| `FZXiaoBiaoSong-B05S.ttf` / `simhei.ttf` | 方正小标宋简体 / 黑体 | 裁判文书/起诉状大标题（二号字） |
| `simsun.ttc` / `simsun.ttf` | 宋体 | 表格表头、证据目录文字 |
| `simkai.ttf` / `kaiti_GB2312.ttf` | 楷体 / 楷体_GB2312 | 引用法条、文书签发及批注 |

---

## 字体刷新与容器自检脚本

在 Dockerfile 或容器启动后，容器内会自动执行：

```bash
# 刷新字体缓存
fc-cache -fv /usr/share/fonts/truetype/custom

# 验证字体识别
fc-list :lang=zh
```

在 Windows 宿主机本地开发时，Python 脚本将直接调用系统自带的 `C:\Windows\Fonts`，无需额外拷贝即可无缝渲染。

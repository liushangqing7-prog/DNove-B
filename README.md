# DNove-B

一个基于 **Python + PyQt6** 的小说创作辅助桌面应用（工作区管理、三栏写作 UI、设定卡、AI 调用、快照回滚等）。

## 运行

```bash
pip install PyQt6 PyYAML requests
python main.py
```

## 已实现能力（MVP）

- 工作区目录初始化、切换、实时写回、ZIP 导入导出、无权限时 SQLite 降级。
- 三栏布局：左侧大纲树（拖拽/右键）、中间编辑+预览+摘要、右侧草案区+设定库。
- 设定卡：`.char.md` / `.world.md` / `.outline.md` 的 YAML Front Matter 解析与搜索。
- AI 中心：OpenAI-compatible endpoint 配置、Prompt 模板、续写、草案分支、token/成本估算。
- 一句话创世：输入创意后 AI 生成 JSON，并自动创建小说项目和设定卡。
- 长篇记忆注入：最近 5 章摘要 + 当前章节开头参与 Prompt。
- 快照/差异：自动快照、快照列表、两版本 diff。
- 辅助能力：敏感词检测提示、专注写作状态统计。

> 说明：错别字检测与本地向量检索在当前版本保留接口与结构，建议按项目需求继续扩展。

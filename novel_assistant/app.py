from __future__ import annotations

import difflib
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QFrame,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .ai import AIClient, PROVIDER_PRESETS, load_prompt_template
from .cards import CardRepository
from .storage import WorkspaceStorage


SENSITIVE_WORDS = {"违禁词A": "替换词A", "违禁词B": "替换词B"}


@dataclass
class DraftItem:
    title: str
    content: str
    adopted: bool = False


class OneSentenceDialog(QDialog):
    def __init__(self, ai_client: AIClient, parent=None):
        super().__init__(parent)
        self.ai_client = ai_client
        self.setWindowTitle("一句话创世")
        self.prompt_edit = QLineEdit()
        self.output_edit = QPlainTextEdit()
        gen_btn = QPushButton("生成")
        ok_btn = QPushButton("确认创建")
        gen_btn.clicked.connect(self.generate)
        ok_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("输入脑洞："))
        layout.addWidget(self.prompt_edit)
        layout.addWidget(gen_btn)
        layout.addWidget(self.output_edit)
        layout.addWidget(ok_btn)

    def generate(self):
        prompt = self.prompt_edit.text().strip()
        if not prompt:
            return
        system = "你是小说策划助手，返回结构化 JSON。"
        user = (
            f"基于一句话创意生成 JSON：{prompt}。字段包含 title/style/conflict/roles/milestones。"
        )
        try:
            r = self.ai_client.completion(system, user, stream=False)
            text = self.ai_client.extract_content(r)
            self.output_edit.setPlainText(text)
        except Exception as e:
            self.output_edit.setPlainText(f"生成失败：{e}")

    def get_payload(self) -> dict:
        try:
            return json.loads(self.output_edit.toPlainText())
        except Exception:
            return {}


class SettingsDialog(QDialog):
    def __init__(self, ai_client: AIClient, parent=None):
        super().__init__(parent)
        self.ai_client = ai_client
        self.setWindowTitle("AI 设置")
        self.provider = QLineEdit(ai_client.config.provider)
        self.endpoint = QLineEdit(ai_client.config.endpoint)
        self.api_key = QLineEdit(ai_client.config.api_key)
        self.model = QLineEdit(ai_client.config.model)
        self.temp = QLineEdit(str(ai_client.config.temperature))
        self.budget = QLineEdit(str(ai_client.config.monthly_budget))

        form = QFormLayout(self)
        form.addRow("Provider", self.provider)
        form.addRow("Endpoint", self.endpoint)
        form.addRow("API Key", self.api_key)
        form.addRow("Model", self.model)
        form.addRow("Temperature", self.temp)
        form.addRow("Monthly Budget", self.budget)
        preset_row = QWidget()
        preset_layout = QHBoxLayout(preset_row)
        preset_layout.setContentsMargins(0, 0, 0, 0)
        deepseek_btn = QPushButton("DeepSeek 推荐配置")
        openai_btn = QPushButton("OpenAI 推荐配置")
        deepseek_btn.clicked.connect(lambda: self.apply_preset("deepseek"))
        openai_btn.clicked.connect(lambda: self.apply_preset("openai"))
        preset_layout.addWidget(deepseek_btn)
        preset_layout.addWidget(openai_btn)
        form.addRow("快速配置", preset_row)
        save_btn = QPushButton("保存")
        save_btn.clicked.connect(self.save)
        form.addRow(save_btn)

    def apply_preset(self, provider: str):
        preset = PROVIDER_PRESETS.get(provider)
        if not preset:
            return
        self.provider.setText(provider)
        self.endpoint.setText(preset["endpoint"])
        self.model.setText(preset["model"])

    def save(self):
        c = self.ai_client.config
        c.provider = self.provider.text().strip()
        c.endpoint = self.endpoint.text().strip()
        c.api_key = self.api_key.text().strip()
        c.model = self.model.text().strip()
        try:
            c.temperature = float(self.temp.text().strip() or 0.8)
            c.monthly_budget = float(self.budget.text().strip() or 20.0)
        except ValueError:
            QMessageBox.warning(self, "参数错误", "Temperature 或 Monthly Budget 格式不正确")
            return
        self.ai_client.apply_provider_preset(c, force=False)
        self.ai_client.save_config()
        self.accept()


class SnapshotDialog(QDialog):
    def __init__(self, snapshots: List[Path], parent=None):
        super().__init__(parent)
        self.setWindowTitle("快照与回滚")
        self.list_widget = QListWidget()
        for p in snapshots:
            self.list_widget.addItem(str(p))
        self.diff_view = QPlainTextEdit()
        self.diff_view.setReadOnly(True)
        diff_btn = QPushButton("对比前后两个快照")
        diff_btn.clicked.connect(self.compute_diff)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list_widget)
        layout.addWidget(diff_btn)
        layout.addWidget(self.diff_view)

    def compute_diff(self):
        items = self.list_widget.selectedItems()
        if len(items) != 2:
            return
        a = Path(items[0].text()).read_text(encoding="utf-8").splitlines()
        b = Path(items[1].text()).read_text(encoding="utf-8").splitlines()
        diff = difflib.unified_diff(a, b, lineterm="")
        self.diff_view.setPlainText("\n".join(diff))


class NovelAssistantWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DNove-B Novel Assistant")
        self.resize(1500, 900)

        self.storage = WorkspaceStorage()
        self.ai_client = AIClient(Path.home() / ".dnove" / "config.json")
        self.card_repo: Optional[CardRepository] = None
        self.current_chapter: Optional[Path] = None
        self.drafts: List[DraftItem] = []
        self.chapter_summaries: List[str] = []

        self._build_ui()
        self._apply_visual_theme()
        self._build_menu()
        self.open_workspace(initial=True)

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["大纲树"])
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.tree_menu)
        self.tree.itemClicked.connect(self.load_chapter_from_tree)
        splitter.addWidget(self.tree)

        center = QWidget()
        cv = QVBoxLayout(center)
        self.editor = QTextEdit()
        self.preview = QTextBrowser()
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setPlaceholderText("章节摘要（用于长篇记忆注入）")
        self.editor.textChanged.connect(self.on_editor_changed)
        self.editor.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.editor.customContextMenuRequested.connect(self.editor_menu)
        cv.addWidget(self.editor)
        cv.addWidget(self.preview)
        cv.addWidget(QLabel("章节摘要"))
        cv.addWidget(self.summary_edit)
        splitter.addWidget(center)

        right = QWidget()
        rv = QVBoxLayout(right)
        stats_frame = QFrame()
        stats_frame.setObjectName("statsPanel")
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(12, 12, 12, 12)
        stats_layout.setSpacing(6)
        stats_layout.addWidget(QLabel("写作驾驶舱"))
        self.stat_words = QLabel("字数：0")
        self.stat_paragraphs = QLabel("段落：0")
        self.stat_read = QLabel("阅读时长：1 分钟")
        self.stat_drafts = QLabel("草案数量：0")
        for label in [self.stat_words, self.stat_paragraphs, self.stat_read, self.stat_drafts]:
            stats_layout.addWidget(label)

        self.draft_list = QListWidget()
        self.cards_tab = QTabWidget()
        self.card_view = QPlainTextEdit()
        self.card_view.setReadOnly(True)
        self.cards_tab.addTab(self.card_view, "设定库")
        adopt_btn = QPushButton("采用选中草案")
        discard_btn = QPushButton("丢弃选中草案")
        adopt_btn.clicked.connect(self.adopt_selected_draft)
        discard_btn.clicked.connect(self.discard_selected_draft)

        rv.addWidget(stats_frame)
        rv.addWidget(QLabel("AI 草案区"))
        rv.addWidget(self.draft_list)
        rv.addWidget(adopt_btn)
        rv.addWidget(discard_btn)
        rv.addWidget(self.cards_tab)
        splitter.addWidget(right)

        splitter.setSizes([280, 820, 380])
        self.setCentralWidget(splitter)

        status = QStatusBar()
        self.setStatusBar(status)
        self.update_status()

    def _apply_visual_theme(self):
        self.setStyleSheet(
            """
            QMainWindow {
                background-color: #f5f7fb;
            }
            QTreeWidget, QTextEdit, QTextBrowser, QListWidget, QPlainTextEdit {
                background: #ffffff;
                border: 1px solid #d8deea;
                border-radius: 8px;
                padding: 6px;
                selection-background-color: #cfe5ff;
            }
            QPushButton {
                background-color: #2f6feb;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1f5bd1;
            }
            QPushButton:pressed {
                background-color: #184bad;
            }
            QTabWidget::pane {
                border: 1px solid #d8deea;
                border-radius: 8px;
                background: #ffffff;
            }
            #statsPanel {
                background: #ffffff;
                border: 1px solid #d8deea;
                border-radius: 10px;
            }
            QMenuBar {
                background-color: #eaf1fe;
            }
            QStatusBar {
                background: #eaf1fe;
                border-top: 1px solid #cdd9ef;
            }
            """
        )

    def _build_menu(self):
        menu = self.menuBar()

        file_menu = menu.addMenu("文件")
        open_ws = QAction("打开工作区", self)
        open_ws.triggered.connect(lambda: self.open_workspace(initial=False))
        export_zip = QAction("导出工作区 ZIP", self)
        export_zip.triggered.connect(self.export_workspace_zip)
        import_zip = QAction("导入 ZIP 到工作区", self)
        import_zip.triggered.connect(self.import_workspace_zip)
        create_world = QAction("一句话创世", self)
        create_world.triggered.connect(self.create_project_from_idea)
        snapshots = QAction("快照时间线", self)
        snapshots.triggered.connect(self.show_snapshots)

        for a in [open_ws, export_zip, import_zip, create_world, snapshots]:
            file_menu.addAction(a)

        ai_menu = menu.addMenu("AI")
        ai_settings = QAction("AI 设置", self)
        ai_settings.triggered.connect(self.show_settings)
        ai_expand = QAction("AI 续写/扩写", self)
        ai_expand.triggered.connect(self.ai_expand)
        ai_menu.addAction(ai_settings)
        ai_menu.addAction(ai_expand)

    def open_workspace(self, initial: bool):
        if initial:
            path = QFileDialog.getExistingDirectory(self, "选择工作区")
        else:
            path = QFileDialog.getExistingDirectory(self, "切换工作区")
        if not path:
            return
        paths = self.storage.open_workspace(path)
        self.card_repo = CardRepository(paths.cards)
        self.reload_workspace_data()

    def reload_workspace_data(self):
        self.tree.clear()
        if not self.storage.paths:
            return
        chapter_root = QTreeWidgetItem(["章节"])
        self.tree.addTopLevelItem(chapter_root)
        for ch in self.storage.list_files(self.storage.paths.chapters, ".md"):
            item = QTreeWidgetItem([ch.stem])
            item.setData(0, Qt.ItemDataRole.UserRole, str(ch))
            chapter_root.addChild(item)
        chapter_root.setExpanded(True)

        cards = self.card_repo.list_cards() if self.card_repo else []
        card_text = "\n\n".join([f"# {c.path.name}\n{c.body}" for c in cards])
        self.card_view.setPlainText(card_text)

    def tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        add_vol = menu.addAction("新增卷")
        add_ch = menu.addAction("新增章节")
        rename = menu.addAction("重命名")
        delete = menu.addAction("删除")
        act = menu.exec(self.tree.mapToGlobal(pos))
        if act == add_vol:
            name, ok = QInputDialog.getText(self, "卷", "卷名")
            if ok and name:
                self.tree.addTopLevelItem(QTreeWidgetItem([name]))
        elif act == add_ch and self.storage.paths:
            name, ok = QInputDialog.getText(self, "章节", "章节名")
            if ok and name:
                file = self.storage.paths.chapters / f"{name}.md"
                self.storage.write_text(file, f"# {name}\n")
                self.reload_workspace_data()
        elif act == rename and item:
            name, ok = QInputDialog.getText(self, "重命名", "新名字", text=item.text(0))
            if ok and name:
                item.setText(0, name)
        elif act == delete and item:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            if path and Path(path).exists():
                Path(path).unlink()
                self.reload_workspace_data()

    def load_chapter_from_tree(self, item: QTreeWidgetItem):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return
        self.current_chapter = Path(path)
        self.editor.setPlainText(self.storage.read_text(self.current_chapter))

    def on_editor_changed(self):
        text = self.editor.toPlainText()
        self.preview.setPlainText(text)
        if self.current_chapter:
            self.storage.write_text(self.current_chapter, text)
            self.auto_snapshot("autosave")
        self.update_status()
        self.highlight_sensitive(text)

    def editor_menu(self, pos):
        menu = self.editor.createStandardContextMenu()
        query_setting = QAction("查询设定", self)
        ai_fill = QAction("AI 生成补充设定", self)
        update_state = QAction("更新角色状态", self)
        query_setting.triggered.connect(self.query_setting)
        ai_fill.triggered.connect(self.ai_generate_setting)
        update_state.triggered.connect(self.update_character_state)
        menu.addAction(query_setting)
        menu.addAction(ai_fill)
        menu.addAction(update_state)
        menu.exec(self.editor.mapToGlobal(pos))

    def query_setting(self):
        selected = self.editor.textCursor().selectedText().strip()
        if not selected or not self.card_repo:
            return
        results = self.card_repo.search(selected)
        text = "\n\n".join([f"{r.path.name}\n{r.body[:500]}" for r in results]) or "未找到"
        QMessageBox.information(self, "查询设定", text)

    def ai_generate_setting(self):
        selected = self.editor.textCursor().selectedText().strip()
        if not selected:
            return
        try:
            r = self.ai_client.completion("你是设定补全助手", f"根据文本补充设定：{selected}", stream=False)
            content = self.ai_client.extract_content(r)
            self.push_draft("设定提案", content)
        except Exception as e:
            QMessageBox.warning(self, "AI 错误", str(e))

    def update_character_state(self):
        if not self.card_repo:
            return
        name, ok = QInputDialog.getText(self, "角色", "角色文件名（不含后缀）")
        if not ok or not name:
            return
        card_path = self.storage.paths.cards / f"{name}.char.md"
        if not card_path.exists():
            QMessageBox.warning(self, "错误", "角色卡不存在")
            return
        from .cards import parse_front_matter, dump_front_matter

        content = card_path.read_text(encoding="utf-8")
        meta, body = parse_front_matter(content)
        state, ok = QInputDialog.getText(self, "状态", "当前状态")
        if not ok:
            return
        meta["current_state"] = state
        card_path.write_text(dump_front_matter(meta, body), encoding="utf-8")
        self.reload_workspace_data()

    def ai_expand(self):
        selected = self.editor.textCursor().selectedText().strip() or self.editor.toPlainText()[:600]
        recent = "\n".join(self.chapter_summaries[-5:])
        variables = {
            "selectedText": selected,
            "recentSummary": recent,
            "characters": self.card_view.toPlainText()[:1500],
        }
        prompt = load_prompt_template(Path("prompts"), "default_expand", variables)
        prefix = f"最近摘要:\n{recent}\n\n当前开头:\n{self.editor.toPlainText()[:500]}"
        try:
            full = self.ai_client.completion("你是长篇小说续写助手", prefix + "\n\n" + prompt, stream=False)
            content = self.ai_client.extract_content(full)
            self.push_draft("续写分支1", content)
            self.push_draft("续写分支2", content + "\n\n（分支2建议）")
            self.push_draft("续写分支3", content + "\n\n（分支3建议）")
            usage = full.get("usage", {})
            in_t = int(usage.get("prompt_tokens", 0))
            out_t = int(usage.get("completion_tokens", 0))
            cost = self.ai_client.estimate_cost(in_t, out_t)
            self.statusBar().showMessage(f"Tokens: {in_t}/{out_t} 预估费用: ${cost:.4f}")
        except Exception as e:
            QMessageBox.warning(self, "AI 请求失败", str(e))

    def push_draft(self, title: str, content: str):
        self.drafts.append(DraftItem(title, content))
        item = QListWidgetItem(f"{title} | {datetime.now().strftime('%H:%M:%S')}")
        self.draft_list.addItem(item)
        self.update_status()

    def adopt_selected_draft(self):
        idx = self.draft_list.currentRow()
        if idx < 0:
            return
        draft = self.drafts[idx]
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            cursor.insertText(draft.content)
        else:
            self.editor.insertPlainText("\n" + draft.content)
        draft.adopted = True
        self.auto_snapshot("adopt_draft")

    def discard_selected_draft(self):
        idx = self.draft_list.currentRow()
        if idx < 0:
            return
        self.drafts.pop(idx)
        self.draft_list.takeItem(idx)
        self.update_status()

    def update_status(self):
        text = self.editor.toPlainText()
        words = len(text.replace("\n", ""))
        paragraphs = len([p for p in text.split("\n") if p.strip()])
        read_min = max(1, words // 500)
        self.statusBar().showMessage(
            f"字数:{words} 段落:{paragraphs} 预计阅读:{read_min}分钟 | Ctrl+S 保存"
        )
        self.stat_words.setText(f"字数：{words}")
        self.stat_paragraphs.setText(f"段落：{paragraphs}")
        self.stat_read.setText(f"阅读时长：{read_min} 分钟")
        self.stat_drafts.setText(f"草案数量：{len(self.drafts)}")

    def highlight_sensitive(self, text: str):
        found = [w for w in SENSITIVE_WORDS if w in text]
        if found:
            self.statusBar().showMessage(
                f"检测到敏感词: {','.join(found)} 建议替换 -> {','.join(SENSITIVE_WORDS[w] for w in found)}"
            )

    def export_workspace_zip(self):
        if not self.storage.paths:
            return
        file, _ = QFileDialog.getSaveFileName(self, "导出 ZIP", filter="Zip (*.zip)")
        if file:
            self.storage.export_zip(file)

    def import_workspace_zip(self):
        zip_file, _ = QFileDialog.getOpenFileName(self, "导入 ZIP", filter="Zip (*.zip)")
        if not zip_file:
            return
        dest = QFileDialog.getExistingDirectory(self, "选择恢复目录")
        if not dest:
            return
        self.storage.import_zip(zip_file, dest)
        self.reload_workspace_data()

    def auto_snapshot(self, label: str):
        if not self.storage.paths:
            return
        payload = {
            "chapter": str(self.current_chapter) if self.current_chapter else "",
            "content": self.editor.toPlainText(),
            "summary": self.summary_edit.toPlainText(),
            "cards": self.card_view.toPlainText(),
            "ts": datetime.utcnow().isoformat(),
        }
        self.storage.create_snapshot(label, payload)

    def show_snapshots(self):
        snaps = self.storage.list_snapshots()
        dlg = SnapshotDialog(snaps, self)
        dlg.exec()

    def create_project_from_idea(self):
        dlg = OneSentenceDialog(self.ai_client, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.get_payload()
        if not payload:
            QMessageBox.warning(self, "无效数据", "JSON 解析失败")
            return

        if not self.storage.paths:
            return
        title = payload.get("title", "新小说")
        project_dir = self.storage.paths.root / title
        project_dir.mkdir(parents=True, exist_ok=True)

        novel_json = {
            "title": title,
            "style": payload.get("style", ""),
            "conflict": payload.get("conflict", ""),
            "roles": payload.get("roles", []),
            "milestones": payload.get("milestones", []),
            "status": "draft",
        }
        (project_dir / "novel.json").write_text(
            json.dumps(novel_json, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        cards_dir = project_dir / "cards"
        cards_dir.mkdir(exist_ok=True)
        for i, role in enumerate(payload.get("roles", []), start=1):
            role_file = cards_dir / f"role_{i}.char.md"
            role_file.write_text(
                f"---\nname: {role.get('name', f'角色{i}')}\nstatus: draft\n---\n{role}",
                encoding="utf-8",
            )
        world_file = cards_dir / "world.world.md"
        world_file.write_text(
            f"---\nstatus: draft\n---\n{payload.get('style', '')}\n{payload.get('conflict', '')}",
            encoding="utf-8",
        )
        QMessageBox.information(self, "创建完成", f"已创建项目: {project_dir}")

    def show_settings(self):
        dlg = SettingsDialog(self.ai_client, self)
        dlg.exec()


def run():
    app = QApplication(sys.argv)
    w = NovelAssistantWindow()
    w.show()
    sys.exit(app.exec())

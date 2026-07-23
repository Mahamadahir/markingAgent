import sys
from pathlib import Path

from .app_service import AppService, normalise_action
from .config import (
    DEFAULT_AZURE_API_VERSION,
    DEFAULT_AZURE_ENDPOINT,
    DEFAULT_DB_PATH,
    DEFAULT_EXAM_NAME,
    DEFAULT_MODEL_ENV,
    DEFAULT_OCR_MODE,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_PROVIDER,
    DEFAULT_SUBMISSIONS_PATH,
    PROVIDER_CHOICES,
    default_model_for_provider,
    provider_settings,
)
from .pdf_extract import OCR_MODES
from .grading import LOW_CONFIDENCE_THRESHOLD, render_evaluation
from .state import APPROVED, OVERRIDDEN


def run():
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDialogButtonBox,
            QFileDialog,
            QFrame,
            QGridLayout,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QListWidget,
            QListWidgetItem,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QSplitter,
            QStackedWidget,
            QTableWidget,
            QTableWidgetItem,
            QTextEdit,
            QVBoxLayout,
            QWidget,
        )
    except ImportError as error:
        raise RuntimeError("Desktop UI requires PySide6. Run: pip install -r requirements.txt") from error

    class FilePicker(QWidget):
        def __init__(self, label, placeholder, mode="file"):
            super().__init__()
            self.mode = mode
            self.input = QLineEdit()
            self.input.setPlaceholderText(placeholder)
            self.button = QPushButton("Choose")
            layout = QGridLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.addWidget(QLabel(label), 0, 0, 1, 2)
            layout.addWidget(self.input, 1, 0)
            layout.addWidget(self.button, 1, 1)
            self.button.clicked.connect(self.choose_file)

        def choose_file(self):
            if self.mode == "directory":
                path = QFileDialog.getExistingDirectory(self, "Choose folder")
            else:
                path, _ = QFileDialog.getOpenFileName(self, "Choose file")
            if path:
                self.input.setText(path)

        def text(self):
            return self.input.text().strip()

        def set_text(self, value):
            self.input.setText(str(value))

    class MainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("GradeAudit AI Assistant")
            self.resize(1280, 820)
            self.service = AppService(DEFAULT_DB_PATH, DEFAULT_OUTPUT_PATH)
            self.exam_items = []
            self.current_item = None
            self.current_evaluation = None

            self.stack = QStackedWidget()
            self.nav = QListWidget()
            self.nav.setFixedWidth(240)
            self.nav.addItems(["Project Setup", "Extraction Review", "Grading Workspace", "Results", "Analytics"])
            self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)

            root = QWidget()
            root_layout = QHBoxLayout(root)
            root_layout.setContentsMargins(0, 0, 0, 0)
            root_layout.addWidget(self.nav)
            root_layout.addWidget(self.stack, 1)

            self.setup_screen()
            self.extraction_screen()
            self.grading_screen()
            self.results_screen()
            self.analytics_screen()

            self.setCentralWidget(root)
            self.nav.setCurrentRow(0)
            self.apply_theme()

        def closeEvent(self, event):
            self.service.close()
            super().closeEvent(event)

        def setup_screen(self):
            screen = QWidget()
            layout = QVBoxLayout(screen)
            layout.setContentsMargins(20, 20, 20, 20)
            layout.setSpacing(12)

            title = QLabel("Project Setup")
            title.setObjectName("title")
            layout.addWidget(title)

            self.exam_name = QLineEdit(DEFAULT_EXAM_NAME)
            self.mark_scheme_pdf = FilePicker("Mark scheme PDF", "data/input/mark_scheme.pdf")
            self.question_paper_pdf = FilePicker("Question paper PDF reference", "data/input/question_paper.pdf")
            self.submissions_path = FilePicker("Student response PDFs folder", str(DEFAULT_SUBMISSIONS_PATH), mode="directory")
            self.mark_scheme_text = FilePicker("Extracted mark scheme text", "data/extracted/mark_scheme.txt")
            self.ocr_mode = QComboBox()
            self.ocr_mode.addItems(OCR_MODES)
            self.ocr_mode.setCurrentText(DEFAULT_OCR_MODE)
            self.database_path = QLineEdit(str(DEFAULT_DB_PATH))
            self.output_path = QLineEdit(str(DEFAULT_OUTPUT_PATH))

            self.model_name = QComboBox()
            self.model_name.setEditable(True)
            self.model_name.setCurrentText(DEFAULT_MODEL_ENV)

            self.fetch_models_button = QPushButton("Fetch models")
            self.fetch_models_button.clicked.connect(self.fetch_models)

            self.provider_select = QComboBox()
            self.provider_select.addItems(PROVIDER_CHOICES)
            self.provider_select.setCurrentText(DEFAULT_PROVIDER)
            self.provider_select.currentTextChanged.connect(self.on_provider_changed)

            self.api_key_input = QLineEdit()
            self.api_key_input.setEchoMode(QLineEdit.Password)
            self.api_key_input.setPlaceholderText("Leave blank to use environment variable")

            self.consensus_toggle = QCheckBox("Multi-model consensus (grade with the models selected below)")
            self.consensus_toggle.toggled.connect(self.on_consensus_toggled)
            self.consensus_models = QListWidget()
            self.consensus_models.setSelectionMode(QListWidget.ExtendedSelection)
            self.consensus_models.setMaximumHeight(110)

            self.azure_endpoint = QLineEdit(DEFAULT_AZURE_ENDPOINT)
            self.azure_endpoint.setPlaceholderText("https://my-resource.openai.azure.com")
            self.azure_api_version = QLineEdit(DEFAULT_AZURE_API_VERSION)

            exam_card = QFrame()
            exam_layout = QGridLayout(exam_card)
            exam_layout.addWidget(QLabel("Exam name"), 0, 0)
            exam_layout.addWidget(self.exam_name, 1, 0)
            layout.addWidget(self.card(exam_card))

            self.submissions_path.set_text(DEFAULT_SUBMISSIONS_PATH)
            self.mark_scheme_text.set_text("data/extracted/mark_scheme.txt")

            for widget in [self.mark_scheme_pdf, self.question_paper_pdf, self.submissions_path, self.mark_scheme_text]:
                layout.addWidget(self.card(widget))

            ocr_card = QFrame()
            ocr_layout = QGridLayout(ocr_card)
            ocr_layout.addWidget(QLabel("Mark scheme OCR"), 0, 0)
            ocr_layout.addWidget(self.ocr_mode, 1, 0)
            ocr_layout.addWidget(
                QLabel("never: embedded text only  •  auto: OCR blank pages  •  always: OCR every page"), 1, 1
            )
            layout.addWidget(self.card(ocr_card))

            provider_card = QFrame()
            provider_layout = QGridLayout(provider_card)
            provider_layout.addWidget(QLabel("LLM provider"), 0, 0)
            provider_layout.addWidget(self.provider_select, 1, 0)
            provider_layout.addWidget(QLabel("Model / deployment"), 0, 1)
            provider_layout.addWidget(self.model_name, 1, 1)
            provider_layout.addWidget(self.fetch_models_button, 1, 2)
            provider_layout.addWidget(QLabel("API key"), 2, 0, 1, 3)
            provider_layout.addWidget(self.api_key_input, 3, 0, 1, 3)
            self.azure_endpoint_label = QLabel("Azure endpoint")
            self.azure_api_version_label = QLabel("Azure API version")
            provider_layout.addWidget(self.azure_endpoint_label, 4, 0)
            provider_layout.addWidget(self.azure_endpoint, 5, 0)
            provider_layout.addWidget(self.azure_api_version_label, 4, 1)
            provider_layout.addWidget(self.azure_api_version, 5, 1)
            provider_layout.addWidget(self.consensus_toggle, 6, 0, 1, 3)
            provider_layout.addWidget(self.consensus_models, 7, 0, 1, 3)
            layout.addWidget(self.card(provider_card))
            self.on_provider_changed(DEFAULT_PROVIDER)
            self.on_consensus_toggled(False)

            paths_card = QFrame()
            paths_layout = QGridLayout(paths_card)
            paths_layout.addWidget(QLabel("SQLite state"), 0, 0)
            paths_layout.addWidget(self.database_path, 1, 0)
            paths_layout.addWidget(QLabel("CSV export"), 2, 0)
            paths_layout.addWidget(self.output_path, 3, 0)
            layout.addWidget(self.card(paths_card))

            actions = QHBoxLayout()
            extract_button = QPushButton("Extract Mark Scheme")
            topics_button = QPushButton("Label Topics")
            edit_topics_button = QPushButton("Edit Topics")
            load_button = QPushButton("Load Project")
            extract_button.clicked.connect(self.extract_project_pdfs)
            topics_button.clicked.connect(self.label_topics)
            edit_topics_button.clicked.connect(self.edit_topics)
            load_button.clicked.connect(self.load_project)
            actions.addStretch()
            actions.addWidget(extract_button)
            actions.addWidget(topics_button)
            actions.addWidget(edit_topics_button)
            actions.addWidget(load_button)
            layout.addLayout(actions)
            layout.addStretch()
            self.stack.addWidget(screen)

        def extraction_screen(self):
            screen = QWidget()
            layout = QVBoxLayout(screen)
            layout.setContentsMargins(20, 20, 20, 20)
            title = QLabel("Extraction Review")
            title.setObjectName("title")
            layout.addWidget(title)

            splitter = QSplitter(Qt.Horizontal)
            self.extracted_document_list = QListWidget()
            self.extracted_text = QTextEdit()
            self.pdf_preview_note = QTextEdit()
            self.pdf_preview_note.setReadOnly(True)
            self.pdf_preview_note.setText("Question paper and student scripts stay as PDFs. Only the mark scheme is converted to text here.")
            splitter.addWidget(self.extracted_document_list)
            splitter.addWidget(self.extracted_text)
            splitter.addWidget(self.pdf_preview_note)
            splitter.setSizes([220, 650, 330])
            layout.addWidget(splitter, 1)

            save_button = QPushButton("Save Extracted Text")
            save_button.clicked.connect(self.save_extracted_text)
            layout.addWidget(save_button, alignment=Qt.AlignRight)
            self.extracted_document_list.currentRowChanged.connect(self.load_extracted_document)
            self.stack.addWidget(screen)

        def grading_screen(self):
            screen = QWidget()
            layout = QVBoxLayout(screen)
            layout.setContentsMargins(20, 20, 20, 20)
            title = QLabel("Grading Workspace")
            title.setObjectName("title")
            layout.addWidget(title)

            splitter = QSplitter(Qt.Horizontal)
            self.item_list = QListWidget()
            self.item_list.currentRowChanged.connect(self.select_exam_item)

            centre = QWidget()
            centre_layout = QVBoxLayout(centre)
            self.student_answer = QTextEdit()
            self.student_answer.setReadOnly(True)
            self.ai_evaluation = QTextEdit()
            self.ai_evaluation.setReadOnly(True)
            centre_layout.addWidget(QLabel("Student Response PDF"))
            centre_layout.addWidget(self.student_answer, 1)
            centre_layout.addWidget(QLabel("Provisional AI Evaluation"))
            centre_layout.addWidget(self.ai_evaluation, 1)

            inspector = QWidget()
            inspector_layout = QVBoxLayout(inspector)
            self.score_input = QLineEdit()
            self.notes_input = QTextEdit()
            grade_button = QPushButton("Run AI Evaluation")
            approve_button = QPushButton("Approve")
            override_button = QPushButton("Override")
            grade_button.clicked.connect(self.run_ai_evaluation)
            approve_button.clicked.connect(lambda: self.save_decision(APPROVED))
            override_button.clicked.connect(lambda: self.save_decision(OVERRIDDEN))
            inspector_layout.addWidget(QLabel("Final Score"))
            inspector_layout.addWidget(self.score_input)
            inspector_layout.addWidget(QLabel("Notes"))
            inspector_layout.addWidget(self.notes_input, 1)
            inspector_layout.addWidget(grade_button)
            inspector_layout.addWidget(approve_button)
            inspector_layout.addWidget(override_button)

            splitter.addWidget(self.item_list)
            splitter.addWidget(centre)
            splitter.addWidget(inspector)
            splitter.setSizes([260, 720, 300])
            layout.addWidget(splitter, 1)
            self.stack.addWidget(screen)

        def results_screen(self):
            screen = QWidget()
            layout = QVBoxLayout(screen)
            layout.setContentsMargins(20, 20, 20, 20)
            header = QHBoxLayout()
            title = QLabel("Results")
            title.setObjectName("title")
            refresh_button = QPushButton("Refresh")
            export_button = QPushButton("Export CSV")
            refresh_button.clicked.connect(self.refresh_results)
            export_button.clicked.connect(self.export_csv)
            header.addWidget(title)
            header.addStretch()
            header.addWidget(refresh_button)
            header.addWidget(export_button)
            layout.addLayout(header)

            self.results_table = QTableWidget(0, 7)
            self.results_table.setHorizontalHeaderLabels(["Exam", "Student", "Question", "Status", "Action", "Score", "Notes"])
            self.results_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            layout.addWidget(self.results_table, 1)
            self.stack.addWidget(screen)

        def analytics_screen(self):
            screen = QWidget()
            layout = QVBoxLayout(screen)
            layout.setContentsMargins(20, 20, 20, 20)
            header = QHBoxLayout()
            title = QLabel("Analytics")
            title.setObjectName("title")
            refresh_button = QPushButton("Refresh")
            refresh_button.clicked.connect(self.refresh_analytics)
            header.addWidget(title)
            header.addStretch()
            header.addWidget(refresh_button)
            layout.addLayout(header)

            self.question_stats_table = self.stats_table(["Question", "Topic", "Graded", "Average %"])
            self.topic_stats_table = self.stats_table(["Topic", "Graded", "Average %"])
            self.student_stats_table = self.stats_table(["Student", "Questions", "Score", "Percent"])
            layout.addWidget(QLabel("By question"))
            layout.addWidget(self.question_stats_table, 1)
            layout.addWidget(QLabel("By topic"))
            layout.addWidget(self.topic_stats_table, 1)
            layout.addWidget(QLabel("Student totals"))
            layout.addWidget(self.student_stats_table, 1)
            self.stack.addWidget(screen)

        def stats_table(self, headers):
            table = QTableWidget(0, len(headers))
            table.setHorizontalHeaderLabels(headers)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            return table

        def refresh_analytics(self):
            data = self.service.analytics()
            hardest = {stat["question_id"] for stat in data["hardest"]}
            self.fill_table(
                self.question_stats_table,
                [
                    [stat["question_id"], stat["topic"] or "-", str(stat["count"]), f"{stat['average_percent']}"]
                    for stat in data["questions"]
                ],
                flag_rows=[stat["question_id"] in hardest for stat in data["questions"]],
            )
            self.fill_table(
                self.topic_stats_table,
                [[stat["topic"], str(stat["count"]), f"{stat['average_percent']}"] for stat in data["topics"]],
            )
            self.fill_table(
                self.student_stats_table,
                [
                    [stat["student_id"], str(stat["questions"]), f"{stat['awarded']}/{stat['available']}", f"{stat['percent']}"]
                    for stat in data["students"]
                ],
            )

        def fill_table(self, table, rows, flag_rows=None):
            table.setRowCount(len(rows))
            for row_index, values in enumerate(rows):
                for column, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if flag_rows and flag_rows[row_index]:
                        item.setForeground(Qt.red)
                    table.setItem(row_index, column, item)

        def card(self, widget):
            frame = QFrame()
            frame.setObjectName("card")
            layout = QVBoxLayout(frame)
            layout.addWidget(widget)
            return frame

        def extract_project_pdfs(self):
            try:
                if not self.mark_scheme_pdf.text():
                    QMessageBox.warning(self, "Missing mark scheme", "Choose a mark scheme PDF first.")
                    return
                output = self.mark_scheme_text.text() or "data/extracted/mark_scheme.txt"
                self.service.extract_pdf(self.mark_scheme_pdf.text(), output, ocr_mode=self.ocr_mode.currentText())
                self.add_extracted_document(output)
                QMessageBox.information(self, "Extraction complete", "Mark scheme text extraction finished. Question papers remain as PDF references.")
            except Exception as error:
                self.show_error(error)

        def label_topics(self):
            try:
                if not self.mark_scheme_text.text():
                    QMessageBox.warning(self, "Missing mark scheme", "Extract or choose the mark scheme text first.")
                    return
                self.service.set_exam(
                    exam_name=self.exam_name.text().strip() or DEFAULT_EXAM_NAME,
                    mark_scheme_path=self.mark_scheme_text.text(),
                )
                topics = self.service.extract_topics(self.current_provider_settings(), self.mark_scheme_text.text())
                if not topics:
                    QMessageBox.information(self, "No topics", "No question headings found to label.")
                    return
                summary = "\n".join(f"{question_id}: {topic}" for question_id, topic in sorted(topics.items()))
                QMessageBox.information(self, "Topics labelled", summary)
            except Exception as error:
                self.show_error(error)

        def edit_topics(self):
            try:
                if not self.mark_scheme_text.text():
                    QMessageBox.warning(self, "Missing mark scheme", "Extract or choose the mark scheme text first.")
                    return
                self.service.set_exam(
                    exam_name=self.exam_name.text().strip() or DEFAULT_EXAM_NAME,
                    mark_scheme_path=self.mark_scheme_text.text(),
                )
                rows = self.service.topics_for_editing(self.mark_scheme_text.text())
                if not rows:
                    QMessageBox.information(self, "No questions", "No question headings found in the mark scheme.")
                    return
                topics = self.prompt_topic_edits(rows)
                if topics is None:
                    return
                self.service.save_question_topics(topics)
                QMessageBox.information(self, "Topics saved", "Topic edits saved.")
            except Exception as error:
                self.show_error(error)

        def prompt_topic_edits(self, rows):
            dialog = QDialog(self)
            dialog.setWindowTitle("Edit Topics")
            dialog.resize(480, 360)
            layout = QVBoxLayout(dialog)
            table = QTableWidget(len(rows), 2)
            table.setHorizontalHeaderLabels(["Question", "Topic"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            for row, (question_id, topic) in enumerate(rows):
                identifier = QTableWidgetItem(question_id)
                identifier.setFlags(identifier.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, 0, identifier)
                table.setItem(row, 1, QTableWidgetItem(topic))
            layout.addWidget(table)
            buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
            buttons.accepted.connect(dialog.accept)
            buttons.rejected.connect(dialog.reject)
            layout.addWidget(buttons)
            if dialog.exec() != QDialog.Accepted:
                return None
            return {
                table.item(row, 0).text(): table.item(row, 1).text().strip()
                for row in range(table.rowCount())
            }

        def add_extracted_document(self, path):
            item = QListWidgetItem(str(path))
            item.setData(Qt.UserRole, str(path))
            self.extracted_document_list.addItem(item)

        def load_extracted_document(self, row):
            item = self.extracted_document_list.item(row)
            if not item:
                return
            path = Path(item.data(Qt.UserRole))
            if path.exists():
                self.extracted_text.setPlainText(path.read_text(encoding="utf-8"))

        def save_extracted_text(self):
            item = self.extracted_document_list.currentItem()
            if not item:
                return
            path = Path(item.data(Qt.UserRole))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(self.extracted_text.toPlainText(), encoding="utf-8")
            QMessageBox.information(self, "Saved", f"Saved {path}")

        def load_project(self):
            try:
                self.service.close()
                self.service = AppService(
                    self.database_path.text(),
                    self.output_path.text(),
                    exam_name=self.exam_name.text().strip() or DEFAULT_EXAM_NAME,
                )
                self.service.set_exam(
                    exam_name=self.exam_name.text().strip() or DEFAULT_EXAM_NAME,
                    mark_scheme_path=self.mark_scheme_text.text(),
                    question_paper_path=self.question_paper_pdf.text(),
                    students_path=self.submissions_path.text(),
                )
                self.apply_stored_provider()
                self.exam_items = self.service.load_exam_items(
                    self.submissions_path.text(),
                    self.mark_scheme_text.text(),
                )
                self.item_list.clear()
                for item in self.exam_items:
                    self.item_list.addItem(self.item_label(item))
                if Path(self.mark_scheme_text.text()).exists():
                    self.add_extracted_document(self.mark_scheme_text.text())
                self.refresh_results()
                self.nav.setCurrentRow(2)
            except Exception as error:
                self.show_error(error)

        def select_exam_item(self, row):
            if row < 0 or row >= len(self.exam_items):
                return
            self.current_item = self.exam_items[row]
            self.current_evaluation = self.service.get_saved_evaluation(
                self.current_item["student_id"],
                self.current_item["question_id"],
            )
            self.student_answer.setPlainText(self.current_item["pdf_path"])
            self.ai_evaluation.setPlainText("")
            self.score_input.clear()
            self.notes_input.clear()
            if self.current_evaluation:
                self.render_current_evaluation()

        def on_provider_changed(self, provider):
            is_azure = provider == "azure"
            self.azure_endpoint.setVisible(is_azure)
            self.azure_api_version.setVisible(is_azure)
            self.azure_endpoint_label.setVisible(is_azure)
            self.azure_api_version_label.setVisible(is_azure)
            if not self.model_name.currentText().strip():
                self.model_name.setCurrentText(default_model_for_provider(provider))

        def on_consensus_toggled(self, checked):
            self.consensus_models.setVisible(checked)

        def fetch_models(self):
            try:
                models = self.service.list_models(self.current_provider_settings())
            except Exception as error:
                self.show_error(error)
                return
            if not models:
                QMessageBox.information(
                    self,
                    "No models listed",
                    "This provider does not list models for the given key "
                    "(Azure exposes deployments, not base models). Enter the model or deployment name manually.",
                )
                return
            current = self.model_name.currentText()
            self.model_name.clear()
            self.model_name.addItems(models)
            if current:
                self.model_name.setCurrentText(current)
            self.consensus_models.clear()
            self.consensus_models.addItems(models)

        def item_label(self, item):
            confidence = item.get("confidence")
            confidence_text = "" if confidence is None else f" | {confidence:.0%}"
            flag = " REVIEW" if item.get("flagged") else ""
            return f"{item['student_id']} | {item['question_id']} | {item['status']}{confidence_text}{flag}"

        def apply_stored_provider(self):
            stored = self.service.stored_provider()
            if not stored:
                return
            self.provider_select.setCurrentText(stored["provider"])
            if stored.get("model"):
                self.model_name.setCurrentText(stored["model"])

        def current_provider_settings(self, model=None):
            return provider_settings(
                model or self.model_name.currentText().strip() or default_model_for_provider(self.provider_select.currentText()),
                provider=self.provider_select.currentText(),
                api_key=self.api_key_input.text().strip(),
                azure_endpoint=self.azure_endpoint.text().strip(),
                azure_api_version=self.azure_api_version.text().strip() or DEFAULT_AZURE_API_VERSION,
            )

        def consensus_settings(self):
            models = [item.text() for item in self.consensus_models.selectedItems()]
            return [self.current_provider_settings(model=model) for model in models]

        def run_ai_evaluation(self):
            if not self.current_item:
                return
            try:
                if self.consensus_toggle.isChecked():
                    settings_list = self.consensus_settings()
                    if len(settings_list) < 2:
                        QMessageBox.warning(self, "Select models", "Choose at least two models for consensus grading.")
                        return
                    self.current_evaluation = self.service.grade_item_with_models(
                        settings_list, self.mark_scheme_text.text(), self.current_item
                    )
                else:
                    self.current_evaluation = self.service.grade_item(
                        self.current_provider_settings(), self.mark_scheme_text.text(), self.current_item
                    )
                self.render_current_evaluation()
                self.refresh_results()
            except Exception as error:
                self.show_error(error)

        def render_current_evaluation(self):
            self.ai_evaluation.setPlainText(render_evaluation(self.current_evaluation))
            self.score_input.setText(str(self.current_evaluation["proposed_marks_awarded"]))

        def save_decision(self, action):
            if not self.current_item or not self.current_evaluation:
                QMessageBox.warning(self, "No evaluation", "Run or select an AI evaluation first.")
                return
            try:
                action = normalise_action(action)
                notes = self.notes_input.toPlainText().strip()
                if action == OVERRIDDEN and not notes:
                    QMessageBox.warning(self, "Override reason required", "Enter notes before overriding.")
                    return
                if action == APPROVED and not notes:
                    notes = "Approved AI assessment."
                self.service.save_decision(
                    self.current_item["student_id"],
                    self.current_item["question_id"],
                    self.current_evaluation,
                    action,
                    self.score_input.text(),
                    notes,
                )
                self.load_project()
                self.nav.setCurrentRow(2)
            except Exception as error:
                self.show_error(error)

        def refresh_results(self):
            records = self.service.records(final_only=False)
            self.results_table.setRowCount(len(records))
            for row, record in enumerate(records):
                values = [
                    record.get("exam_name", ""),
                    record["student_id"],
                    record["question_id"],
                    record["status"],
                    record["human_action"] or "",
                    record["final_score"] or "",
                    record["notes"] or "",
                ]
                for column, value in enumerate(values):
                    self.results_table.setItem(row, column, QTableWidgetItem(value))

        def export_csv(self):
            try:
                count = self.service.export_csv(self.output_path.text())
                QMessageBox.information(self, "Export complete", f"Exported {count} finalised record(s).")
            except Exception as error:
                self.show_error(error)

        def show_error(self, error):
            QMessageBox.critical(self, "GradeAudit", str(error))

        def apply_theme(self):
            self.setStyleSheet(
                """
                QWidget { background: #f9f9ff; color: #181c23; font-family: Inter, Arial, sans-serif; font-size: 13px; }
                QListWidget { background: #f1f3fe; border: 0; padding: 8px; }
                QListWidget::item { padding: 8px; border-radius: 4px; }
                QListWidget::item:selected { background: #d8e2ff; color: #001a41; }
                QFrame#card, QTextEdit, QLineEdit, QTableWidget { background: #ffffff; border: 1px solid #c1c6d7; border-radius: 4px; }
                QTextEdit, QLineEdit { padding: 8px; }
                QPushButton { background: #0058bc; color: #ffffff; border: 0; border-radius: 4px; padding: 8px 12px; }
                QPushButton:hover { background: #0070eb; }
                QLabel#title { font-size: 18px; font-weight: 600; padding-bottom: 8px; }
                QHeaderView::section { background: #e6e8f3; padding: 8px; border: 0; border-right: 1px solid #c1c6d7; }
                """
            )

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(run())

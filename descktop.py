import sys
import json
import subprocess
import os
import threading
import queue
import time
import io
import contextlib
import traceback
import tempfile
from datetime import datetime
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton,
    QLabel, QGroupBox, QFormLayout, QScrollArea, QCheckBox,
    QDialog, QTextEdit, QHBoxLayout, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPalette, QColor, QIcon, QPixmap

# Path to your scraper file
PYTHON_PATH = sys.executable
SCRAPER_PATH = "scraping.py"  # Make sure this file exists in the same directory

class ScraperWorker(QThread):
    """Worker thread to run the scraper"""
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)
    
    def __init__(self, email, password, pages, auto_bypass):
        super().__init__()
        self.email = email
        self.password = password
        self.pages = pages
        self.auto_bypass = auto_bypass
        self.process = None
    
    def run(self):
        try:
            self.log_signal.emit("🚀 Starting Google Pay Scraper...")
            self.log_signal.emit(f"📧 Email: {self.email}")
            self.log_signal.emit(f"🔐 Password: {'*' * len(self.password)}")
            self.log_signal.emit(f"📄 Pages: {self.pages}")
            self.log_signal.emit(f"🤖 Auto-bypass: {self.auto_bypass}")
            self.log_signal.emit("-" * 50)
            
            # Prefer importing and running the scraper in-process. This
            # makes bundling into a single exe (PyInstaller) work correctly
            # because spawning the embedded interpreter is fragile.

            try:
                import scraping
            except Exception as exc:
                # Log full traceback to a temp file so we can inspect runtime errors inside the frozen exe
                try:
                    log_dir = tempfile.gettempdir()
                    log_path = os.path.join(log_dir, "desktop_scraper_error.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                        traceback.print_exc(file=f)
                except Exception:
                    pass
                self.finished_signal.emit(False, "Scraper is not available.")
                return
            if hasattr(scraping, 'run_scraper'):
                class _Redirector:
                    def write(inner_self, s):
                        if s and s.strip():
                            for ln in s.rstrip().splitlines():
                                self.log_signal.emit(ln)
                    def flush(inner_self):
                        pass
                with contextlib.redirect_stdout(_Redirector()), contextlib.redirect_stderr(_Redirector()):
                    try:
                        scraping.run_scraper(self.email, self.password, self.pages, self.auto_bypass)
                        self.log_signal.emit("✅ Scraper completed successfully!")
                        self.finished_signal.emit(True, "Completed successfully")
                        return
                    except SystemExit as se:
                        code = getattr(se, 'code', 1) or 0
                        if code == 0:
                            self.log_signal.emit("✅ Scraper completed!")
                            self.finished_signal.emit(True, "Completed successfully")
                            return
                        else:
                            self.finished_signal.emit(False, f"Exit code: {code}")
                            return
                    except Exception:
                        try:
                            log_dir = tempfile.gettempdir()
                            log_path = os.path.join(log_dir, "desktop_scraper_error.log")
                            with open(log_path, "a", encoding="utf-8") as f:
                                f.write(f"\n--- {datetime.now().isoformat()} IN-PROCESS RUN ERROR ---\n")
                                traceback.print_exc(file=f)
                        except Exception:
                            pass
                        self.finished_signal.emit(False, "Scraper failed to run.")
                        return
            else:
                self.finished_signal.emit(False, "Scraper is not available.")
                return


            # Fallback: run scraper as an external process (legacy behavior)
            if not os.path.exists(SCRAPER_PATH):
                self.finished_signal.emit(False, "Scraper is not available.")
                return

            cmd = [
                PYTHON_PATH, SCRAPER_PATH,
                "--email", self.email,
                "--password", self.password,
                "--pages", str(self.pages)
            ]
            if self.auto_bypass:
                cmd.append("--auto-bypass")

            try:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                while True:
                    line = self.process.stdout.readline()
                    if not line and self.process.poll() is not None:
                        break
                    if line:
                        self.log_signal.emit(line.strip())
                exit_code = self.process.returncode
                if exit_code == 0:
                    self.log_signal.emit("✅ Scraper completed successfully!")
                    self.finished_signal.emit(True, "Completed successfully")
                else:
                    self.finished_signal.emit(False, f"Scraper failed to run.")
            except Exception:
                try:
                    log_dir = tempfile.gettempdir()
                    log_path = os.path.join(log_dir, "desktop_scraper_error.log")
                    with open(log_path, "a", encoding="utf-8") as f:
                        f.write(f"\n--- {datetime.now().isoformat()} SUBPROCESS RUN ERROR ---\n")
                        traceback.print_exc(file=f)
                except Exception:
                    pass
                self.finished_signal.emit(False, "Scraper failed to run.")

        except Exception as e:
            # Log unexpected errors
            try:
                log_dir = tempfile.gettempdir()
                log_path = os.path.join(log_dir, "desktop_scraper_error.log")
                with open(log_path, "a", encoding="utf-8") as f:
                    f.write(f"\n--- {datetime.now().isoformat()} WORKER UNEXPECTED ERROR ---\n")
                    traceback.print_exc(file=f)
            except Exception:
                pass
            try:
                self.log_signal.emit("💥 Error: An unexpected error occurred while running the scraper.")
            except Exception:
                pass
            self.finished_signal.emit(False, "Scraper failed to run.")
    
    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.log_signal.emit("🛑 Scraper process terminated by user")

class LogDialog(QDialog):
    """Dialog to show scraper logs"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scraper Status - Live Monitoring")
        self.resize(900, 700)
        
        # Set modern styling
        self.setStyleSheet("""
            QDialog {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2c3e50, stop: 1 #34495e);
                color: white;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 2px solid #3498db;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                selection-background-color: #3498db;
            }
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #e74c3c, stop: 1 #c0392b);
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                min-width: 100px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #c0392b, stop: 1 #a93226);
            }
            QPushButton:disabled {
                background-color: #7f8c8d;
                color: #bdc3c7;
            }
            QPushButton#closeBtn {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3498db, stop: 1 #2980b9);
            }
            QPushButton#closeBtn:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2980b9, stop: 1 #1f4e79);
            }
        """)
        
        # Layout
        layout = QVBoxLayout(self)
        
        # Header
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(52, 152, 219, 0.1);
                border-radius: 8px;
                padding: 10px;
                margin-bottom: 10px;
            }
            QLabel {
                color: #3498db;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_label = QLabel("📊 Real-time Scraper Monitoring")
        header_layout.addWidget(header_label)
        layout.addWidget(header_frame)
        
        # Log display
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # Status bar
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(46, 204, 113, 0.1);
                border-radius: 8px;
                padding: 8px;
                margin: 5px 0px;
            }
            QLabel {
                color: #2ecc71;
                font-size: 12px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        self.status_label = QLabel("⚡ Ready to start...")
        status_layout.addWidget(self.status_label)
        layout.addWidget(status_frame)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.stop_button = QPushButton("🛑 Stop Process")
        self.close_button = QPushButton("✅ Close")
        self.close_button.setObjectName("closeBtn")
        
        self.stop_button.clicked.connect(self.stop_scraper)
        self.close_button.clicked.connect(self.accept)
        
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.close_button)
        layout.addLayout(button_layout)
        
        self.worker = None
        
    def start_scraper(self, email, password, pages, auto_bypass):
        """Start the scraper worker"""
        self.status_label.setText("🔄 Scraper is running...")
        self.worker = ScraperWorker(email, password, pages, auto_bypass)
        self.worker.log_signal.connect(self.add_log)
        self.worker.finished_signal.connect(self.scraper_finished)
        self.worker.start()
        
    def add_log(self, message):
        """Add log message to display"""
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
        

    def scraper_finished(self, success, message):
        """Called when scraper finishes"""
        if success:
            self.add_log("🎉 All operations completed successfully!")
            self.status_label.setText("✅ Completed successfully")
            self.status_label.parent().setStyleSheet("""
                QFrame {
                    background-color: rgba(46, 204, 113, 0.2);
                    border: 2px solid #2ecc71;
                    border-radius: 8px;
                    padding: 8px;
                    margin: 5px 0px;
                }
                QLabel { color: #2ecc71; font-weight: bold; }
            """)
        else:
            # Only show a simple message if scraper is unavailable
            if message == "Scraper is not available.":
                self.add_log("⚠️ Scraper is not available on this system.")
                self.status_label.setText("⚠️ Scraper unavailable")
            else:
                self.add_log("❌ Scraper failed to run.")
                self.status_label.setText("❌ Process failed")
            self.status_label.parent().setStyleSheet("""
                QFrame {
                    background-color: rgba(231, 76, 60, 0.2);
                    border: 2px solid #e74c3c;
                    border-radius: 8px;
                    padding: 8px;
                    margin: 5px 0px;
                }
                QLabel { color: #e74c3c; font-weight: bold; }
            """)
        self.stop_button.setEnabled(False)
        
    def stop_scraper(self):
        """Stop the scraper"""
        if self.worker:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self.status_label.setText("🛑 Stopping process...")

class FormWidget(QGroupBox):
    """Single form widget for email/password input"""
    def __init__(self, form_id, parent=None):
        super().__init__()
        self.form_id = form_id
        self.parent_widget = parent
        
        # Remove default title and set custom styling
        self.setTitle("")
        self.setStyleSheet("""
            QGroupBox {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(255, 255, 255, 0.95),
                    stop: 1 rgba(248, 249, 250, 0.95));
                border: 2px solid #3498db;
                border-radius: 15px;
                margin: 10px 5px;
                padding-top: 20px;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            
            QLabel {
                color: #2c3e50;
                font-size: 14px;
                font-weight: 600;
                margin: 5px 0px;
            }
            
            QLineEdit {
                background-color: #ffffff;
                color: #000000;
                border: 2px solid #bdc3c7;
                border-radius: 8px;
                padding: 12px 15px;
                font-size: 14px;
                font-family: 'Segoe UI', Arial, sans-serif;
                selection-background-color: #3498db;
                selection-color: white;
            }
            
            QLineEdit:focus {
                border: 2px solid #3498db;
                background-color: #f8f9fa;
                outline: none;
            }
            
            QLineEdit:hover {
                border-color: #52a3db;
            }
            
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #3498db, stop: 1 #2980b9);
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 20px;
                font-size: 16px;
                font-weight: bold;
                min-height: 20px;
            }
            
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2980b9, stop: 1 #1f4e79);
                transform: translateY(-1px);
            }
            
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1f4e79, stop: 1 #174a6b);
                transform: translateY(1px);
            }
            
            QPushButton#removeBtn {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #e74c3c, stop: 1 #c0392b);
                margin-top: 10px;
            }
            
            QPushButton#removeBtn:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #c0392b, stop: 1 #a93226);
            }
            
            QCheckBox {
                color: #34495e;
                font-size: 13px;
                spacing: 8px;
                margin: 10px 0px;
            }
            
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 2px solid #bdc3c7;
                background-color: white;
            }
            
            QCheckBox::indicator:checked {
                background-color: #3498db;
                border-color: #3498db;
                image: none;
            }
            
            QCheckBox::indicator:checked:after {
                content: "✓";
                color: white;
                font-weight: bold;
            }
        """)

        # Header for form
        header_layout = QHBoxLayout()
        form_title = QLabel(f"Account Configuration #{form_id}")
        form_title.setStyleSheet("""
            QLabel {
                color: #3498db;
                font-size: 18px;
                font-weight: bold;
                margin: 0px 0px 15px 0px;
                padding: 10px;
                background-color: rgba(52, 152, 219, 0.1);
                border-radius: 8px;
            }
        """)
        header_layout.addWidget(form_title)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.addLayout(header_layout)

        # Form layout
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setContentsMargins(20, 10, 20, 20)

        # Email input
        email_label = QLabel("📧 Email Address:")
        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter your email address (e.g., user@gmail.com)")
        form_layout.addRow(email_label, self.email_input)

        # Password input
        password_label = QLabel("🔐 Password:")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        form_layout.addRow(password_label, self.password_input)

        # Pages input
        pages_label = QLabel("📄 Number of Pages:")
        self.pages_input = QLineEdit()
        self.pages_input.setPlaceholderText("Number of pages to scrape (default: 1)")
        self.pages_input.setText("1")
        form_layout.addRow(pages_label, self.pages_input)

        # Auto-bypass checkbox with better styling
        self.auto_bypass_chk = QCheckBox(
            "🤖 Enable Auto-bypass: Automatically handle passkey prompts and click \"Try another way\" → \"Enter your password\""
        )
        self.auto_bypass_chk.setChecked(True)
        form_layout.addRow(self.auto_bypass_chk)

        main_layout.addLayout(form_layout)

        # Buttons layout
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(10)
        buttons_layout.setContentsMargins(20, 0, 20, 20)

        # Submit button
        self.submit_btn = QPushButton("🚀 Start Scraping")
        self.submit_btn.clicked.connect(self.submit_form)

        # Remove button
        self.remove_btn = QPushButton("🗑️ Remove Account")
        self.remove_btn.setObjectName("removeBtn")
        self.remove_btn.clicked.connect(self.remove_form)

        buttons_layout.addWidget(self.submit_btn, 2)
        buttons_layout.addWidget(self.remove_btn, 1)
        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

    def submit_form(self):
        """Submit the form and start scraping"""
        # Get form data
        email = self.email_input.text().strip()
        password = self.password_input.text().strip()
        pages_text = self.pages_input.text().strip()
        auto_bypass = self.auto_bypass_chk.isChecked()

        # Validate input
        if not email or not password:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Input Validation Error")
            msg.setText("Missing Required Information")
            msg.setInformativeText("Please enter both email address and password to continue.")
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #ecf0f1;
                    color: #2c3e50;
                }
                QMessageBox QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
            """)
            msg.exec()
            return

        try:
            pages = int(pages_text) if pages_text else 1
            if pages <= 0:
                pages = 1
        except ValueError:
            pages = 1

        # Show log dialog and start scraper
        log_dialog = LogDialog(self)
        log_dialog.start_scraper(email, password, pages, auto_bypass)
        log_dialog.exec()

    def remove_form(self):
        """Remove this form"""
        if self.parent_widget:
            self.parent_widget.remove_form(self)

class MainApp(QWidget):
    """Main application window"""
    def __init__(self):
        super().__init__()
        self.forms = []
        self.form_counter = 0
        self.init_ui()

    def init_ui(self):
        """Initialize the UI"""
        self.setWindowTitle("🚀 Google Pay Scraper - Professional Edition")
        self.resize(800, 900)
        
        # Set professional gradient background
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #2c3e50,
                    stop: 0.5 #34495e,
                    stop: 1 #2c3e50);
                color: white;
                font-family: 'Segoe UI', 'Roboto', Arial, sans-serif;
            }
            
            QScrollArea {
                border: none;
                background: transparent;
            }
            
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            
            QScrollBar:vertical {
                background-color: rgba(127, 140, 141, 0.3);
                width: 12px;
                border-radius: 6px;
            }
            
            QScrollBar::handle:vertical {
                background-color: rgba(52, 152, 219, 0.8);
                border-radius: 6px;
                min-height: 20px;
            }
            
            QScrollBar::handle:vertical:hover {
                background-color: #3498db;
            }
        """)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # Professional header
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(52, 152, 219, 0.2),
                    stop: 0.5 rgba(155, 89, 182, 0.2),
                    stop: 1 rgba(52, 152, 219, 0.2));
                border: 2px solid rgba(52, 152, 219, 0.5);
                border-radius: 15px;
                margin-bottom: 20px;
                padding: 20px;
            }
        """)
        
        header_layout = QVBoxLayout(header_frame)
        
        title_label = QLabel("Welcome Again")
        title_label.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))
        title_label.setStyleSheet("""
            QLabel {
                color: qlineargradient(x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 #3498db,
                    stop: 0.5 #9b59b6,
                    stop: 1 #3498db);
                text-align: center;
                margin: 10px 0px;
            }
        """)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle_label = QLabel("Professional Google Pay Data Extraction Tool")
        subtitle_label.setFont(QFont("Segoe UI", 14, QFont.Weight.Normal))
        subtitle_label.setStyleSheet("""
            QLabel {
                color: #bdc3c7;
                text-align: center;
                margin: 5px 0px 15px 0px;
                font-style: italic;
            }
        """)
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        main_layout.addWidget(header_frame)

        # Scroll area for forms
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)

        # Container for forms
        self.container = QWidget()
        self.forms_layout = QVBoxLayout(self.container)
        self.forms_layout.setSpacing(15)

        self.scroll_area.setWidget(self.container)
        main_layout.addWidget(self.scroll_area)

        # Add button with professional styling
        self.add_btn = QPushButton("➕ Add New Account Configuration")
        self.add_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #27ae60, stop: 1 #2ecc71);
                color: white;
                border: none;
                border-radius: 12px;
                padding: 18px 30px;
                font-size: 16px;
                font-weight: bold;
                margin: 15px 50px;
                min-height: 25px;
            }
            QPushButton:hover {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #2ecc71, stop: 1 #27ae60);
                transform: translateY(-2px);
            }
            QPushButton:pressed {
                background: qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1,
                    stop: 0 #1e8449, stop: 1 #239b56);
                transform: translateY(0px);
            }
        """)
        self.add_btn.clicked.connect(self.add_form)
        main_layout.addWidget(self.add_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Add first form
        self.add_form()

    def add_form(self):
        """Add a new form"""
        self.form_counter += 1
        form = FormWidget(self.form_counter, self)
        self.forms.append(form)
        self.forms_layout.addWidget(form)

    def remove_form(self, form):
        """Remove a form"""
        if len(self.forms) > 1:  # Keep at least one form
            self.forms.remove(form)
            self.forms_layout.removeWidget(form)
            form.deleteLater()
        else:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Information)
            msg.setWindowTitle("Configuration Limit")
            msg.setText("Minimum Configuration Required")
            msg.setInformativeText("At least one account configuration must remain active.")
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: #ecf0f1;
                    color: #2c3e50;
                }
                QMessageBox QPushButton {
                    background-color: #3498db;
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 8px 16px;
                    font-weight: bold;
                }
            """)
            msg.exec()

def main():
    """Main function"""
    app = QApplication(sys.argv)
    
    # Set application properties
    app.setApplicationName("Google Pay Scraper Professional")
    app.setApplicationVersion("2.0")
    app.setStyle('Fusion')
    
    # Create and show main window
    window = MainApp()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
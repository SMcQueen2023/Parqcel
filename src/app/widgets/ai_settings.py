from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QMessageBox,
)
import os
import json
import logging

try:
    import keyring
except Exception:
    keyring = None
logger = logging.getLogger(__name__)


from ai.config import load_config


class AISettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Settings")
        self.resize(500, 200)

        cfg = load_config()

        layout = QVBoxLayout(self)

        # import backend factory lazily to avoid heavy ML imports during module import
        try:
            from ai.backends import create_backend

            backend = create_backend(cfg)
        except Exception as e:
            QMessageBox.critical(self, "Test Failed", f"Could not create backend: {e}")
            return

        # attempt a small ping; disable button while running and ensure re-enabled
        self.test_btn.setEnabled(False)
        try:
            import time
            start = time.perf_counter()
            ok = False
            if hasattr(backend, "test_connection"):
                ok = backend.test_connection()
            else:
                # fallback: call generate_text with a ping prompt
                resp = backend.generate_text("ping")
                ok = resp is not None
            elapsed = time.perf_counter() - start
            if ok:
                QMessageBox.information(self, "Test Succeeded", f"Connection OK (latency {elapsed:.2f}s)")
            else:
                QMessageBox.warning(self, "Test Result", "Backend did not indicate success")
        except Exception as e:
            QMessageBox.critical(self, "Test Failed", f"Error during test: {e}")
        finally:
            self.test_btn.setEnabled(True)
            keyring_msg = "Keyring available: keys will be stored securely."
        else:
            keyring_msg = "Keyring unavailable: API keys will not be saved; install 'keyring' to persist."
        self.keyring_label = QLabel(keyring_msg)
        layout.addWidget(self.keyring_label)

        base_layout = QHBoxLayout()
        base_layout.addWidget(QLabel("OpenAI API Base (optional):"))
        self.base_input = QLineEdit()
        self.base_input.setText(cfg.get("openai_api_base", ""))
        base_layout.addWidget(self.base_input)
        layout.addLayout(base_layout)

        hf_layout = QHBoxLayout()
        hf_layout.addWidget(QLabel("HF Model (hf provider):"))
        self.hf_input = QLineEdit()
        self.hf_input.setPlaceholderText("gpt2")
        self.hf_input.setText(cfg.get("hf_model", ""))
        hf_layout.addWidget(self.hf_input)
        layout.addLayout(hf_layout)

        btn_layout = QHBoxLayout()
        self.test_btn = QPushButton("Test Connection")
        self.save_btn = QPushButton("Save")
        self.close_btn = QPushButton("Close")
        btn_layout.addWidget(self.test_btn)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

        self.test_btn.clicked.connect(self._on_test)
        self.save_btn.clicked.connect(self._on_save)
        self.close_btn.clicked.connect(self.accept)

    def _current_config(self):
        return {
            "provider": self.provider.currentText(),
            "openai_api_base": self.base_input.text().strip() or None,
            "hf_model": self.hf_input.text().strip() or None,
        }

    def _on_save(self):
        cfg = self._current_config()
        # save config file to user home
        cfg_dir = os.path.join(os.path.expanduser("~"), ".parqcel")
        os.makedirs(cfg_dir, exist_ok=True)
        cfg_path = os.path.join(cfg_dir, "config.json")
        # write non-secret fields to config
        save_cfg = {k: v for k, v in cfg.items() if k != "openai_api_key"}
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(save_cfg, f, indent=2)
        # store key in keyring if available
        key = self.key_input.text().strip()
        if key:
            if keyring is not None:
                try:
                    keyring.set_password("parqcel", "openai_api_key", key)
                except Exception:
                    QMessageBox.warning(self, "Keyring Error", "Failed to store API key in OS keyring. It will not be saved.")
            else:
                # Do NOT write API keys to plaintext config as a fallback.
                # Instead, warn the user and ask them to install `keyring`.
                QMessageBox.warning(
                    self,
                    "Keyring Missing",
                    "OS keyring is not available. API keys will NOT be saved. Install the 'keyring' package for secure storage.",
                )
        QMessageBox.information(self, "Saved", f"Configuration saved to {cfg_path}")

    def _on_test(self):
        # build config dictionary including key from UI or keyring
        cfg = self._current_config()
        key = self.key_input.text().strip()
        if key:
            cfg["openai_api_key"] = key
        else:
            if keyring is not None:
                try:
                    stored = keyring.get_password("parqcel", "openai_api_key")
                    if stored:
                        cfg["openai_api_key"] = stored
                except Exception:
                    # If keyring read fails, ignore and continue without key
                    logger.exception("Failed to read API key from keyring during test")

        try:
            self.test_btn.setEnabled(False)
            # import backend factory lazily to avoid heavy ML imports during module import
            from ai.backends import create_backend

            backend = create_backend(cfg)
        except Exception as e:
            QMessageBox.critical(self, "Test Failed", f"Could not create backend: {e}")
            return

        # attempt a small ping
        try:
            import time
            start = time.perf_counter()
            ok = False
            if hasattr(backend, "test_connection"):
                ok = backend.test_connection()
            else:
                # fallback: call generate_text with a ping prompt
                resp = backend.generate_text("ping")
                ok = resp is not None
            elapsed = time.perf_counter() - start
            if ok:
                QMessageBox.information(self, "Test Succeeded", f"Connection OK (latency {elapsed:.2f}s)")
            else:
                QMessageBox.warning(self, "Test Result", "Backend did not indicate success")
        except Exception as e:
            QMessageBox.critical(self, "Test Failed", f"Error during test: {e}")
        finally:
            self.test_btn.setEnabled(True)

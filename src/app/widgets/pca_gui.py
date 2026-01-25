from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QSpinBox,
    QWidget,
)
from PyQt6.QtCore import Qt


class PCADialog(QDialog):
    def __init__(self, column_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dimensionality Reduction (PCA/UMAP)")
        self.resize(560, 420)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select feature columns (check items):"))
        self.list_widget = QListWidget()
        for col in column_names:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)
        layout.addWidget(self.list_widget)

        opts = QWidget()
        opts_layout = QHBoxLayout(opts)

        opts_layout.addWidget(QLabel("Method:"))
        self.method_combo = QComboBox()
        self.method_combo.addItems(["PCA", "UMAP (if available)"])
        opts_layout.addWidget(self.method_combo)

        opts_layout.addWidget(QLabel("Components:"))
        self.components_spin = QSpinBox()
        self.components_spin.setRange(2, 3)
        self.components_spin.setValue(2)
        opts_layout.addWidget(self.components_spin)

        opts_layout.addWidget(QLabel("Color by (optional):"))
        self.color_combo = QComboBox()
        self.color_combo.addItem("(None)")
        opts_layout.addWidget(self.color_combo)

        opts_layout.addWidget(QLabel("Sample (max rows, 0=all):"))
        self.sample_spin = QSpinBox()
        self.sample_spin.setRange(0, 10000000)
        self.sample_spin.setValue(10000)
        opts_layout.addWidget(self.sample_spin)

        layout.addWidget(opts)

        btn_layout = QHBoxLayout()
        ok = QPushButton("Run")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btn_layout.addWidget(ok)
        btn_layout.addWidget(cancel)
        layout.addLayout(btn_layout)

    def set_color_choices(self, names):
        self.color_combo.clear()
        self.color_combo.addItem("(None)")
        for n in names:
            self.color_combo.addItem(n)

    def get_selected_columns(self):
        cols = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cols.append(item.text())
        return cols

    def get_options(self):
        method = self.method_combo.currentText()
        n_components = int(self.components_spin.value())
        color_by = self.color_combo.currentText()
        if color_by == "(None)":
            color_by = None
        sample = int(self.sample_spin.value())
        return {
            "method": method,
            "n_components": n_components,
            "color_by": color_by,
            "sample": sample,
        }

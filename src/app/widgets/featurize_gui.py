from PyQt6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QComboBox,
    QCheckBox,
    QSpinBox,
    QWidget,
)
from PyQt6.QtCore import Qt


class FeaturizeDialog(QDialog):
    def __init__(self, column_names, numeric_cols, categorical_cols, text_cols, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Featurize Columns")
        self.resize(500, 400)

        self.column_names = column_names
        self.numeric_cols = set(numeric_cols)
        self.categorical_cols = set(categorical_cols)
        self.text_cols = set(text_cols)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select columns to featurize (check items):"))
        self.list_widget = QListWidget()
        for col in column_names:
            item = QListWidgetItem(col)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            # default: check if column is numeric/categorical/text
            if col in self.numeric_cols or col in self.categorical_cols or col in self.text_cols:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Options
        opts = QWidget()
        opts_layout = QHBoxLayout(opts)

        opts_layout.addWidget(QLabel("Scale numeric:"))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["standard", "minmax", "none"])
        opts_layout.addWidget(self.scale_combo)

        self.one_hot_checkbox = QCheckBox("One-hot encode categorical")
        self.one_hot_checkbox.setChecked(True)
        opts_layout.addWidget(self.one_hot_checkbox)

        opts_layout.addWidget(QLabel("TF-IDF max features:"))
        self.tfidf_spin = QSpinBox()
        self.tfidf_spin.setRange(10, 5000)
        self.tfidf_spin.setValue(200)
        opts_layout.addWidget(self.tfidf_spin)

        layout.addWidget(opts)

        # Buttons
        btns = QHBoxLayout()
        ok = QPushButton("Featurize and Add")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def get_selected_columns(self):
        cols = []
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                cols.append(item.text())
        return cols

    def get_options(self):
        scale = self.scale_combo.currentText()
        if scale == "none":
            scale = None
        one_hot = self.one_hot_checkbox.isChecked()
        tfidf_max = int(self.tfidf_spin.value())
        return {
            "scale_numeric": scale,
            "one_hot": one_hot,
            "tfidf_max_features": tfidf_max,
        }

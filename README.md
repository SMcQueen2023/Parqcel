# Parqcel

![Parqcel logo](src/parqcel/assets/parqcel_icon.png)

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A modern, fast, and feature-rich desktop application for viewing, editing, and analyzing **Parquet**, **CSV**, and **Excel** files. Built with PyQt6 and powered by Polars for lightning-fast data processing.

## 🎯 What is Parqcel?

Parqcel is a professional-grade data exploration and manipulation tool designed for data engineers, analysts, and scientists who work with tabular data. It combines the speed of Polars with an intuitive GUI to provide a seamless experience for:

- **Viewing** large datasets with efficient pagination (no memory overload)
- **Editing** data inline with full undo/redo support
- **Analyzing** with column statistics, filtering, and sorting
- **Transforming** with feature engineering and dimensionality reduction
- **Automating** with an optional AI assistant for Polars code generation

Whether you're exploring a multi-gigabyte Parquet file, cleaning CSV data, or performing exploratory data analysis, Parqcel provides a powerful yet user-friendly interface.

---

## ✨ Key Features

### 📁 File Operations
- **Multi-format support**: Open Parquet, CSV, and Excel files
- **Fast pagination**: Handle large datasets efficiently with configurable page sizes
- **Save as Parquet**: Export your modified data to high-performance Parquet format
- **Drag & drop**: Quick file loading via drag-and-drop interface

### ✏️ Editing Capabilities
- **Inline cell editing**: Click any cell to edit values directly
- **Full undo/redo**: Navigate through edit history with Ctrl+Z/Ctrl+Y
- **Add columns**: Create new calculated or static columns
- **Type conversion**: Convert columns between string, integer, float, datetime, and boolean types
- **Multi-sort**: Sort by multiple columns with custom ascending/descending order

### 📊 Data Analysis
- **Column statistics**: Automatic computation of:
  - Count, nulls, unique values
  - Min, max, mean, median, std deviation
  - Type-specific metrics (e.g., string lengths, date ranges)
- **Quick filters**: Right-click column headers for instant filtering:
  - Equals, not equals, contains (strings)
  - Greater than, less than, between (numbers)
  - Date range filters (datetime)
  - Is null / is not null
- **Advanced filtering**: Chain multiple filters for complex queries

### 🧪 Data Science Features (ML Extras)
- **Automated featurization**:
  - Numeric features: scaling, normalization
  - Categorical features: one-hot encoding, label encoding
  - Text features: TF-IDF vectorization, character n-grams
- **Dimensionality reduction**:
  - PCA (Principal Component Analysis)
  - UMAP (Uniform Manifold Approximation and Projection)
  - Interactive Plotly visualizations
  - Export embeddings to CSV or HTML

### 🤖 AI Assistant (AI Extras)
- **Natural language queries**: Ask for data transformations in plain English
- **Polars code generation**: Get syntactically correct Polars expressions
- **Safe execution**: AST-based code validation ensures only safe operations
- **Multiple backends**:
  - OpenAI (GPT models)
  - HuggingFace (local or hosted transformers)
  - Dummy mode (offline testing)
- **Prompt-based**: Operates on your natural-language request; dataframe schema is not automatically included in prompts

### 🔒 Security & Safety
- **Secure code execution**: AI-generated code validated before running
- **Credential management**: API keys stored in OS keyring (not plaintext)
- **Privacy considerations**: Your prompts are sent to the configured AI provider; the app does not automatically add table data or perform redaction, so avoid including sensitive data in prompts and review your provider's data policies
- **Comprehensive validation**: See [SECURITY.md](SECURITY.md) for details

---

## 📋 System Requirements

- **Operating System**: Windows, macOS, or Linux
- **Memory**: 4GB minimum, 8GB+ recommended for large files
- **Display**: 1280x720 minimum resolution

For Windows installer users, Python is not required on the target machine.
Python 3.11+ is only required for source, `pip`, and packaging workflows.

---

## 🚀 Installation

### For Most Windows Users

The primary distribution path for Parqcel is the standalone Windows installer.

1. Download `Parqcel-Installer.exe` from the latest Windows release.
2. Double-click the installer.
3. Keep the default install location unless you have a specific reason to change it.
4. Optionally enable the Desktop shortcut checkbox.
5. Finish setup and launch Parqcel from the Start Menu or Desktop shortcut.

What this gives you:

- No Python installation required
- No terminal usage during setup
- Normal Windows app shortcuts and uninstall entry

### Windows Desktop Installer for Releases

The Windows installer is built from a standalone desktop bundle instead of running `pip install` on the target machine.

- No Python installation is required on the end-user device.
- No terminal is required during installation.
- Start Menu and optional Desktop shortcuts are created by the installer.
- The packaged feature set is determined by the desktop build profile.

Recommended release shape:

- Build the desktop installer with the `base` profile for mainstream non-technical users.
- Keep `pip install` for technical users and advanced AI workflows.
- Use the `ml` profile only when you want featurization and dimensionality reduction included in the desktop app.

#### Build the standalone Windows installer

```powershell
py -3 -m pip install .[desktop-build]
pwsh -File .\scripts\build_windows_desktop.ps1 -Clean -Installer
```

If you want ML features in the desktop app, install them into the build environment before running the packaging script:

```powershell
py -3 -m pip install .[ml,desktop-build]
pwsh -File .\scripts\build_windows_desktop.ps1 -Clean -Profile ml -Installer
```

The packaging script produces a standalone app in `dist\Parqcel` and, when Inno Setup is available, an installer in `installer\dist\Parqcel-Installer.exe`. The default `base` profile explicitly excludes ML and AI stacks so the desktop build stays small and predictable even when your local Python environment has extra packages installed.

### For Technical Users (Python / Source)

```bash
# Clone the repository
git clone https://github.com/SMcQueen2023/Parqcel.git
cd Parqcel

# Install base package
pip install .

# Run the application
parqcel
```

### Python Installation Options

Use the Python installation path if you want source-based development, scripting, automation, or access to the heavier optional dependency stacks.

Parqcel offers modular Python installation based on your needs:

| Need | Command |
|------|---------|
| Core desktop app only | `pip install .` |
| Core app + ML tooling | `pip install .[ml]` |
| Core app + hosted AI backends | `pip install .[ai-openai]` |
| Core app + local AI backends | `pip install .[ai-local]` |
| Core app + ML + hosted AI | `pip install .[ml,ai-openai]` |
| Core app + ML + local AI | `pip install .[ml,ai-local]` |
| Everything | `pip install .[ai]` |

#### 1. **Base Installation** (GUI only)
```bash
pip install .
```
Includes: PyQt6, Polars, basic viewing/editing features

#### 2. **Data Science Package** (with ML features)
```bash
pip install .[ml]
```
Adds: numpy, scikit-learn, plotly, umap-learn  
Enables: Featurization, PCA/UMAP, dimensionality reduction

#### 3. **OpenAI Support Add-on**
```bash
pip install .[ai-openai]
```
Adds: OpenAI API client, keyring  
Enables: Hosted AI backends without downloading local transformer models

Recommended when you want the assistant backed by OpenAI but do not want the local transformer stack. Combine with `.[ml]` if you also want featurization and dimensionality reduction.

#### 4. **Local AI Add-on**
```bash
pip install .[ai-local]
```
Adds: sentence-transformers, faiss-cpu, langchain, transformers  
Enables: Local embedding and Hugging Face based AI workflows

Recommended when you want local or Hugging Face driven AI features without pulling in the hosted OpenAI client.

#### 5. **AI Assistant Package** (full features)
```bash
pip install .[ai]
```
Adds: All ML dependencies + hosted and local AI backends  
Enables: AI-powered code generation, embeddings, NLP features

#### 6. **Development Package**
```bash
pip install .[dev]
```
Adds: pytest, pytest-qt, black, ruff, mypy  
Enables: Running tests, linting, type checking

#### 7. **Desktop Packaging Tools**
```bash
pip install .[desktop-build]
```
Adds: PyInstaller  
Enables: Building a standalone Windows desktop app and installer
### Installing from PyPI (Technical Users)
```bash
pip install parqcel          # Base
pip install parqcel[ml]      # With ML
pip install parqcel[ai-openai]  # OpenAI integration only
pip install parqcel[ai-local]   # Local AI integration only
pip install parqcel[ai]      # With AI
pip install parqcel[dev]     # Dev tools
```

---

## 🎮 Usage

### Launching the GUI

```bash
# Method 1: Direct command
parqcel

# Method 2: Python module
python -m parqcel

# Method 3: From source
cd /path/to/Parqcel
python src/main.py
```

### Command-Line Interface (CLI)

Parqcel includes a headless CLI for automation and scripting:

#### Featurize a Dataset
```bash
parqcel-cli featurize input.parquet -o features.parquet
```
Generates numeric feature matrix from mixed-type data.

#### Compute PCA Embeddings
```bash
parqcel-cli pca input.csv --components 3 -o embeddings.csv
```
Reduces dimensionality and saves principal components.

#### Query the AI Assistant
```bash
parqcel-cli assistant "Filter rows where age > 30 and sort by name"
```
Get Polars code suggestions without launching the GUI.

---

## 🔧 Configuration

### AI Assistant Setup (Optional)

To enable AI features, configure your preferred backend:

#### Option 1: GUI Settings Dialog
1. Launch Parqcel
2. Go to **Settings → AI Settings**
3. Select provider (OpenAI or HuggingFace)
4. Enter API key (stored securely in OS keyring)
5. Test connection

#### Option 2: Environment Variables
```bash
# Set provider
export PARQCEL_AI_PROVIDER=openai

# OpenAI configuration
export PARQCEL_OPENAI_API_KEY=sk-...
export PARQCEL_OPENAI_API_BASE=https://api.openai.com/v1  # optional: for proxies or custom endpoints

# HuggingFace configuration
export PARQCEL_HF_MODEL=gpt2  # or any HF model name
```

#### Option 3: Config File
Config stored at: `~/.parqcel/config.json` (auto-created by GUI)

```json
{
  "provider": "openai",
  "openai_api_base": "https://api.openai.com/v1",
  "hf_model": "gpt2"
}
```

**Note**: API keys are **never** written to config files. They're stored in your system's secure keyring.

#### Available Backends
- **`openai`**: OpenAI GPT models (requires API key)
- **`hf`**: HuggingFace transformers (local or cloud)
- **`dummy`**: Offline mode for testing (returns placeholder code)

---

## 📖 User Guide

### Basic Workflow

1. **Open a file**: File → Open, or drag & drop
2. **Explore data**: Navigate pages, view statistics
3. **Filter/Sort**: Right-click column headers for quick operations
4. **Edit cells**: Double-click to edit, Ctrl+Z to undo
5. **Transform**: Use AI assistant or manual operations
6. **Export**: File → Save As Parquet

### Tips for Large Files

- Use **pagination** to avoid loading entire file into memory
- Apply **filters early** to reduce working set size
- **Save intermediate results** to Parquet for faster reloading
- See [PERFORMANCE.md](PERFORMANCE.md) for optimization strategies

### AI Assistant Best Practices

- **Be specific**: "Filter rows where price > 100" works better than "filter by price"
- **Review code**: Always check generated code before executing
- **Test on samples**: Try transformations on filtered subsets first
- **Iterative refinement**: If code doesn't work, rephrase your query

---

## 🧪 Testing

### Running Tests

```bash
# Install dev dependencies
pip install .[dev]

# Run all tests
pytest -q

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_validator.py

# Run with coverage
pytest --cov=src tests/
```

### Test Structure

```
tests/
├── test_validator.py      # AI code validation
├── test_featurize.py      # Feature engineering
├── test_parsers.py        # Data type conversion
├── test_filtering.py      # Filtering logic
└── test_stats.py          # Statistics computation
```

---

## 🛠️ Development

### Setting Up Development Environment

```bash
# Clone repo
git clone https://github.com/SMcQueen2023/Parqcel.git
cd Parqcel

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install with all dev dependencies
pip install -e .[dev]

# Install pre-commit hooks (optional)
pip install pre-commit
pre-commit install
```

### Code Quality

#### Formatting
```bash
black src/ tests/          # Auto-format code
ruff check src/ tests/     # Lint and check style
```

#### Type Checking
```bash
mypy src/                  # Static type analysis
```

#### Security Scanning
```bash
bandit -r src/             # Security vulnerability scan
ruff check src/ --select S # Security-focused linting
```

### Project Structure

```
Parqcel/
├── src/
│   ├── parqcel/          # Main package
│   │   ├── __main__.py   # Entry point
│   │   └── assets/       # Icons and resources
│   ├── app/              # GUI components
│   │   ├── main_window.py
│   │   └── widgets/      # UI dialogs and panels
│   ├── models/           # Data models (Polars integration)
│   ├── logic/            # Business logic
│   │   ├── stats.py      # Statistics computation
│   │   ├── filters.py    # Filtering operations
│   │   └── parsers.py    # Type conversion
│   ├── ds/               # Data science features
│   │   ├── featurize.py  # Feature engineering
│   │   └── dimensionality.py  # PCA/UMAP
│   ├── ai/               # AI assistant
│   │   ├── assistant.py  # Main assistant logic
│   │   ├── backends.py   # Provider implementations
│   │   ├── validator.py  # Code safety validation
│   │   └── config.py     # Configuration management
│   ├── cli.py            # CLI entry point
│   └── main.py           # GUI entry point
├── tests/                # Test suite
├── docs/                 # Documentation
├── pyproject.toml        # Project metadata & dependencies
├── README.md             # This file
├── CHANGELOG.md          # Version history
├── SECURITY.md           # Security documentation
├── PERFORMANCE.md        # Performance guide
└── CONTRIBUTING.md       # Contribution guidelines
```

---

## 🔒 Security

Parqcel takes security seriously, especially for the AI assistant feature which executes code.

### Key Security Features

- **AST-based code validation**: Only safe Polars operations allowed
- **No arbitrary imports**: Import statements are blocked
- **No system access**: File I/O and network operations prohibited
- **Sandboxed execution**: Only `df` and `pl` variables accessible
- **Credential protection**: API keys stored in OS keyring, never in logs

### Security Best Practices

⚠️ **Do NOT use AI features on sensitive data**:
- Personal Identifiable Information (PII)
- Financial records
- Healthcare data (PHI)
- Trade secrets or confidential data

✅ **Safe usage**:
- Review all AI-generated code before execution
- Test on sample/synthetic data first
- Use read-only API keys when possible
- Rotate API keys periodically

For detailed security information, see [SECURITY.md](SECURITY.md).

---

## 🐛 Troubleshooting

### Common Issues

#### Installation Problems

**Issue**: `pip install` fails with compilation errors  
**Solution**: Ensure you have Python 3.11+ and update pip: `pip install --upgrade pip`

**Issue**: PyQt6 installation fails  
**Solution**: Some systems require system packages:
```bash
# Ubuntu/Debian
sudo apt-get install python3-pyqt6

# macOS
brew install pyqt6
```

#### Runtime Issues

**Issue**: Application won't launch  
**Solution**: Check Python version: `python --version` (must be 3.11+)

**Issue**: Large file crashes the app  
**Solution**: 
- Increase pagination size: adjust page size in settings
- Filter data before loading
- See [PERFORMANCE.md](PERFORMANCE.md) for optimization tips

**Issue**: AI assistant not working  
**Solution**:
1. Verify API key is set (Settings → AI Settings)
2. Check internet connection
3. Test with dummy backend first: `export PARQCEL_AI_PROVIDER=dummy`

#### Data Issues

**Issue**: Date columns not parsing correctly  
**Solution**: The parser tries multiple formats. If it fails:
- Ensure dates are in ISO 8601 format (YYYY-MM-DD)
- Or use type conversion dialog to specify custom format

**Issue**: Excel file not loading  
**Solution**: Ensure you have openpyxl installed: `pip install openpyxl`

### Getting Help

- **GitHub Issues**: [Report bugs or request features](https://github.com/SMcQueen2023/Parqcel/issues)
- **Discussions**: [Ask questions or share ideas](https://github.com/SMcQueen2023/Parqcel/discussions)
- **Security**: See [SECURITY.md](SECURITY.md) for vulnerability reporting

---

## 📊 Performance

Parqcel is optimized for real-world datasets, but performance depends on file size and operations:

| File Size | Memory Usage | Load Time | Notes |
|-----------|--------------|-----------|-------|
| < 100 MB  | ~2x file size | < 1s | Excellent performance |
| 100 MB - 1 GB | ~3x file size | 1-5s | Good, use pagination |
| 1 - 10 GB   | ~3-5x file size | 5-30s | Recommended: filter early |
| > 10 GB   | Variable | 30s+ | May require optimization |

**Performance Tips**:
- Use Parquet format (10-100x faster than CSV)
- Apply filters before expensive operations
- Limit undo history for large files
- Use CLI for batch processing

For detailed performance analysis and optimization strategies, see [PERFORMANCE.md](PERFORMANCE.md).

---

## 🗺️ Roadmap

### Current Version (0.1.0)
- ✅ Parquet/CSV/Excel support
- ✅ Inline editing with undo/redo
- ✅ Column statistics and filtering
- ✅ Featurization and PCA/UMAP
- ✅ AI assistant with safe execution

### Planned Features
- [ ] **Multi-tab interface**: Work with multiple files simultaneously
- [ ] **SQL query support**: Write SQL against loaded dataframes
- [ ] **Plot builder**: Create custom visualizations
- [ ] **Macro system**: Record and replay operation sequences
- [ ] **Plugin architecture**: Extend with custom transformations
- [ ] **Collaborative features**: Share configs and transformations
- [ ] **Cloud integration**: Direct S3/Azure/GCS file access
- [ ] **Real-time streaming**: Monitor and analyze live data feeds

### Under Consideration
- Database connectivity (PostgreSQL, MySQL, SQLite)
- Jupyter notebook export
- Automated data profiling and quality reports
- Integration with dbt, Airflow, and other data tools

See [CHANGELOG.md](CHANGELOG.md) for version history.

---

## 🤝 Contributing

Contributions are welcome! Whether you're fixing bugs, adding features, or improving documentation, your help makes Parqcel better.

### How to Contribute

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Make** your changes
4. **Test** thoroughly: `pytest -v`
5. **Format** code: `black .` and `ruff check .`
6. **Commit**: `git commit -m "Add amazing feature"`
7. **Push**: `git push origin feature/amazing-feature`
8. **Open** a Pull Request

### Contribution Guidelines

- Follow existing code style (Black formatting, Ruff linting)
- Add tests for new features
- Update documentation as needed
- Keep PRs focused and atomic
- For major changes, open an issue first to discuss

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**Scott McQueen** — Data Engineer

- GitHub: [@SMcQueen2023](https://github.com/SMcQueen2023)
- Project: [Parqcel](https://github.com/SMcQueen2023/Parqcel)

---

## 🙏 Acknowledgments

Built with these excellent open-source projects:

- **[Polars](https://pola.rs/)**: Lightning-fast DataFrame library
- **[PyQt6](https://www.riverbankcomputing.com/software/pyqt/)**: Cross-platform GUI framework
- **[scikit-learn](https://scikit-learn.org/)**: Machine learning and featurization
- **[Plotly](https://plotly.com/)**: Interactive visualizations
- **[UMAP](https://umap-learn.readthedocs.io/)**: Dimensionality reduction
- **[OpenAI](https://openai.com/)**: AI assistant backend
- **[HuggingFace](https://huggingface.co/)**: Transformers and model hosting

---

## 📚 Additional Resources

- **[SECURITY.md](SECURITY.md)**: Comprehensive security documentation
- **[PERFORMANCE.md](PERFORMANCE.md)**: Performance optimization guide
- **[CONTRIBUTING.md](CONTRIBUTING.md)**: Contribution guidelines
- **[CHANGELOG.md](CHANGELOG.md)**: Version history and release notes

---

**Made with ❤️ for the data community**

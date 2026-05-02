# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-05-01

### Added
- Reusable background task runner for long-running UI actions
- Focused regression tests for undo/redo, async UI flows, and AI backend/settings behavior

### Changed
- Split optional AI dependencies into hosted and local install extras
- Updated README install guidance for standalone Windows release artifacts and current AI scope
- Refreshed Windows installer branding and release documentation

### Fixed
- Restored undo/redo support for dropped columns via centralized model reset handling
- Moved featurization, dimensionality reduction, assistant suggestions, and AI connection tests off the UI thread
- Removed a PyInstaller exclusion that blocked the ML desktop build profile

### Added
- Comprehensive README documentation with installation, usage, and contribution guidelines (PR #58)
- SECURITY.md and PERFORMANCE.md documentation (PR #57)

### Changed
- Extracted AST validation to dedicated module for better code organization (PR #57)
- Improved exception handling and datetime parsing robustness (PR #57)

## [0.1.0] - 2026-01-25

### Added
- **AI Assistant Integration** (PRs #49, #50)
  - Configurable AI backends (OpenAI, Anthropic, Ollama)
  - Natural language to Polars code generation
  - Context-aware suggestions and code completions
- **Data Science Features** (PRs #47, #48, #50)
  - Column featurization for machine learning workflows
  - Principal Component Analysis (PCA) support
  - UMAP dimensionality reduction
  - Analysis tools for data exploration
- **Installer Support** (PR #51)
  - Inno Setup installer script for Windows distribution
  - Centralized temporary file management
  - Hardened AI assistant response handling

### Improved
- **Code Quality** (PRs #43, #55)
  - Applied Black formatting and Ruff linting
  - Added comprehensive test coverage
  - Implemented CI/CD workflows with GitHub Actions
- **Type Safety and Error Handling** (PR #46)
  - Robust datetime parsing with format detection
  - Safer type conversions with error handling
  - Improved logging throughout the application
- **Date/Time Processing** (PRs #38, #45)
  - Vectorized parsing with Python fallback
  - Automatic format detection for dates
  - String formatted dates to datetime conversion
  - Fixed datetime to string conversion and back

### Fixed
- Fixed EGL/GL library installation in CI workflow (PR #55)
- Removed unnecessary scikit-learn from base requirements (PR #55)
- Fixed NumPy installation order in CI (PR #55)
- Fixed headless Qt configuration for testing (PR #55)
- Removed committed bytecode (.pyc files) and updated .gitignore (PR #42)

## [0.0.9] - 2026-01-23

### Added
- **Testing Infrastructure** (PRs #39, #40, #41)
  - pytest configuration and test suite
  - Comprehensive test coverage for parsers and filters
  - GitHub Actions CI/CD pipeline
- **Parsing and Filtering Logic** (PRs #40, #41)
  - Centralized date/time parsing in `logic.parsers`
  - Pure filter logic module in `logic.filtering`
  - Improved code modularity and testability

### Improved
- **Code Formatting** (PR #43)
  - Applied Ruff fixes across codebase
  - Applied Black formatting for consistency
- **Documentation** (PR #39)
  - Added logging configuration
  - Improved inline documentation

### Fixed
- Fixed CI workflow to install system packages (libegl1) before Python setup (PR #44)
- Fixed stats.py with robust version for bytes formatting and datetime operations (PR #44)

## [0.0.8] - 2026-01-22

### Added
- **Type Conversion** (PR #37)
  - Convert columns between string, integer, float, datetime, and boolean types
  - Type conversion UI dialogs
- **Date Range Filters** (PR #37)
  - Date range filtering for datetime columns
  - First/last page navigation controls
- **Advanced Date/Time Parsing** (PR #38)
  - Automatic date format detection
  - Vectorized parsing with fallback to Python
  - Support for multiple date formats
  - Added dedicated `date_formats` module

### Improved
- **UI/UX Enhancements** (PRs #37, #38)
  - Improved pagination controls with first/last page buttons
  - Better date range filter dialogs with clearer labels
  - Enhanced UI styling and layout
- **Error Handling** (PRs #35, #36)
  - Improved filtering error messages
  - Surface save errors to user
  - Validate column names before adding
  - Better UI error handling and user feedback

### Fixed
- Fixed filter application to properly update data model (PR #36)
- Fixed column name validation when adding new columns (PR #36)

## [0.0.7] - 2025-05-23

### Improved
- **Statistics Display** (PR #32)
  - Refactored stats.py for modular and robust statistics generation
  - More meaningful column statistics
  - Clearer code structure for developer understanding
  - Enriched column statistics with additional metrics

### Changed
- **UI Labels** (PRs #33, #34)
  - Changed footer "Rows" field to "Total Rows" for clarity
  - More accurate and descriptive field labels

### Fixed
- Fixed crash when editing Date and Datetime columns in grid (PR #31)
- Fixed `PolarsTableModel` to handle date/datetime edits safely

## [0.0.6] - 2025-05-21

### Added
- **Multi-Column Sorting** (PR #30)
  - Sort by multiple columns simultaneously
  - UI dialog for configuring sort order
  - Custom ascending/descending order per column
  - Full integration with table model

## [0.0.5] - 2025-05-16

### Improved
- **Code Organization** (PR #29)
  - Refactored edit_dialog.py into separate GUI and controller modules
  - Split into `edit_menu_gui.py` and `edit_menu_controller.py`
  - Improved modularity and maintainability

## [0.0.4] - 2025-05-14

### Added
- **Enhanced Filtering** (PR #27)
  - Date and datetime column filtering support
  - Filter operators for temporal data

### Fixed
- Fixed unintended filter dialog popup when clicking outside column context menu (PR #28)
- Fixed equality filter for string columns (PR #27)
- Fixed string column filtering logic

## [0.0.3] - 2025-05-09

### Fixed
- Fixed date and datetime selector UI controls (PR #26)
- Fixed date and datetime column adder function (PR #25)
- Fixed footer dataframe statistics display (PR #24)
- Fixed page jump issue during navigation (PR #23)

## [0.0.2] - 2025-05-08

### Improved
- **Major Refactoring** (PR #22)
  - Reorganized code into separate files
  - Better code organization for maintainability
  - Improved reusability of components
  - Fixed filter implementation

## [0.0.1] - 2025-05-06

### Added
- **Edit Functionality** (PR #20)
  - "Edit" button for data modification
  - "Add column" functionality
  - Support for creating new calculated or static columns

### Improved
- **Statistics Window** (PR #19)
  - Made statistics window scrollable for better UX
  - Added string column statistics (PR #18)
  - Count, unique values, most common, etc.

### Fixed
- Fixed page navigation buttons crash when no data loaded (PR #21)

## [0.0.0] - 2025-05-04

### Added
- **Core Application Features**
  - Initial Parqcel desktop application (PR #4)
  - Parquet, CSV, and Excel file viewing
  - Fast pagination with configurable page sizes
  - Basic inline cell editing
  - Column statistics generation
  - Drag and drop file loading

### Improved
- **Refactoring** (PR #17)
  - Refactored code into separate files
  - Better project structure

## Pre-release - 2025-04-29 to 2025-05-02

### Added
- Column filters for text and numeric columns (PR #15)
- Adjusted chunk size to 10000 rows for better performance (PR #14)
- MIT License (PR #10)
- GitHub Actions Python package workflow (PR #9)
- Initial requirements.txt (PR #5)
- Development and testing files (PR #4)

### Changed
- Updated README.md documentation (PRs #2, #6, #7, #12, #16)
- Updated run_parqcel.bat script (PRs #1, #8)

### Fixed
- Fixed typo in Parqcel window header (PR #13)
- Deleted GitHub package due to configuration issues (PR #11)
- Deleted build directory (PR #3)

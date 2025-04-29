# Parqcel
Parqcel is a desktop application built with PyQt6 and Polars that allows users to open, view, edit, and analyze large Parquet files using a spreadsheet-like interface. It features fast pagination, inline cell editing, undo/redo functionality, and descriptive statistics for data columns.

# 🚀 Features
- Open Parquet Files: Load .parquet files into a fast, editable grid powered by Polars.

- Efficient Pagination: Navigate large datasets with chunked pagination (default 500 rows per page).

- Inline Editing: Edit cell values directly in the table. Type conversions are handled intelligently.

- Undo/Redo: Revert or reapply changes using the undo/redo buttons.

- Column Statistics: Generate summary statistics for selected columns (numeric or categorical).

- Jump to Page: Jump to a specific page in the dataset using the input field.

- Column Dropping and Sorting: Right-click column headers to sort or drop columns.

- Save As: Save the current state of the data to a new Parquet file.

# 🖥️ UI Overview
- Main Table View: Displays paginated rows from the current dataset.

- Pagination Controls: Buttons to go forward, backward, or jump to a specific page.

- Undo/Redo Buttons: Quickly revert or reapply changes.

- Statistics Panel: Displays row count, total columns, and column type distribution.

- Context Menu: Right-click a column header to sort (asc/desc) or drop that column.

## Menu Bar:

- File > Open File: Load a Parquet file.

- File > Save As: Save your changes to a new file.

- File > Generate Statistics: Show descriptive statistics of the current column.

# 📦 Installation

**1. Clone this repository:**

git clone https://github.com/SMcQueen2023/parqcel.git
- cd parqcel

**2. Create a virtual environment (optional but recommended)**

- python -m venv venv
- source venv/bin/activate
- **On Windows:** venv\Scripts\activate

**3. Install dependencies**

- pip install -r requirements.txt

**4. Run the app**

- python main.py

# 🧩 Dependencies
- PyQt6
- Polars
- Install them with:
  
pip install pyqt6 polars

# 📝 Notes
- Update the "run_parqcel.bat" file to your local folder path to make launching the app easier.
- This app uses polars under the hood, offering significantly faster performance than traditional pandas for large files.
- Edits are made in-memory and not saved until you explicitly use the Save As function.

# 🧑‍💻 Author
**Scott McQueen**

Data Engineer | Builder of Parqcel

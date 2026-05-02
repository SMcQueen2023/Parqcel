# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files

project_root = Path(SPECPATH)
src_dir = project_root / "src"
icon_path = src_dir / "parqcel" / "assets" / "parqcel_icon.ico"
build_profile = os.environ.get("PARQCEL_BUILD_PROFILE", "base").lower()

common_excludes = [
    "PyQt5",
    "PySide2",
    "PySide6",
    "tkinter",
    "pytest",
    "pytest_qt",
    "mypy",
    "mypy_extensions",
    "black",
    "ruff",
    "IPython",
    "jupyter_client",
    "jupyter_core",
    "nbformat",
    "pip",
    "setuptools",
    "pkg_resources",
    "wheel",
    "distutils",
    "jaraco",
    "more_itertools",
    "zipp",
]
ai_excludes = [
    "openai",
    "keyring",
    "sentence_transformers",
    "faiss",
    "langchain",
    "transformers",
    "torch",
]

if build_profile == "base":
    profile_excludes = [
        "numpy",
        "scipy",
        "sklearn",
        "plotly",
        "umap",
        "matplotlib",
        "pandas",
        "numba",
        "llvmlite",
    ]
elif build_profile == "ml":
    profile_excludes = []
else:
    raise SystemExit(
        f"Unsupported PARQCEL_BUILD_PROFILE '{build_profile}'. Expected 'base' or 'ml'."
    )

datas = []
datas += collect_data_files("parqcel.assets", include_py_files=False)
datas += collect_data_files("ai", includes=["prompts.json"], include_py_files=False)

a = Analysis(
    ["src/main.py"],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=common_excludes + profile_excludes + ai_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Parqcel",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=str(icon_path),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Parqcel",
)

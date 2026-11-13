"""Conservative desktop working-memory suggestions without optional packages."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
import sys

MIB = 1024 * 1024
GIB = 1024 * MIB
FALLBACK_WORKING_BYTES = 512 * MIB
MAX_AUTOMATIC_WORKING_BYTES = 4 * GIB


def _windows_available_memory() -> int:
    if sys.platform != "win32":
        raise OSError("Windows memory information is unavailable on this platform")

    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("length", ctypes.c_uint32),
            ("load", ctypes.c_uint32),
            ("total_physical", ctypes.c_uint64),
            ("available_physical", ctypes.c_uint64),
            ("total_pagefile", ctypes.c_uint64),
            ("available_pagefile", ctypes.c_uint64),
            ("total_virtual", ctypes.c_uint64),
            ("available_virtual", ctypes.c_uint64),
            ("available_extended_virtual", ctypes.c_uint64),
        ]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
    kernel.GlobalMemoryStatusEx.restype = ctypes.c_int
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(status.available_physical)


def _linux_available_memory() -> int:
    # MemAvailable includes reclaimable cache, unlike MemFree. Do not substitute
    # total installed RAM, which ignores the editor and other running programs.
    for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
        fields = line.split()
        if fields and fields[0] == "MemAvailable:":
            if len(fields) != 3 or fields[2] != "kB":
                raise ValueError("Unrecognized MemAvailable format")
            return int(fields[1]) * 1024
    raise ValueError("MemAvailable was not reported")


def available_memory_bytes() -> int | None:
    """Return available physical RAM when measurable, otherwise None.

    This is a system snapshot, not a reservation or a process/container limit.
    Native engine allocations can exceed a caller's working-memory estimate.
    """
    try:
        if sys.platform == "win32":
            available = _windows_available_memory()
        elif sys.platform.startswith("linux"):
            available = _linux_available_memory()
        else:
            available = int(os.sysconf("SC_AVPHYS_PAGES")) * int(
                os.sysconf("SC_PAGE_SIZE")
            )
    except (AttributeError, OSError, TypeError, ValueError, OverflowError):
        return None
    return available if available > 0 else None


def recommended_working_budget() -> int:
    """Suggest one quarter of available RAM, capped at 4 GiB.

    The input frame and history already occupy RAM when the GUI calls this.
    Unknown availability keeps the previous 512 MiB conservative default.
    """
    available = available_memory_bytes()
    if available is None:
        return FALLBACK_WORKING_BYTES
    budget = min(MAX_AUTOMATIC_WORKING_BYTES, available // 4)
    return max(1, (budget // MIB) * MIB if budget >= MIB else budget)

import pytest

from parqcel.core import resource_limits as limits


@pytest.mark.parametrize(
    "available, expected",
    [
        (None, 512 * limits.MIB),
        (2 * limits.GIB, 512 * limits.MIB),
        (8 * limits.GIB, 2 * limits.GIB),
        (64 * limits.GIB, 4 * limits.GIB),
        (256 * limits.MIB, 64 * limits.MIB),
    ],
)
def test_automatic_budget_uses_available_memory_and_leaves_headroom(
    monkeypatch, available, expected
):
    monkeypatch.setattr(limits, "available_memory_bytes", lambda: available)
    assert limits.recommended_working_budget() == expected


def test_linux_probe_uses_available_memory_instead_of_total_or_free(monkeypatch):
    monkeypatch.setattr(limits.sys, "platform", "linux")
    monkeypatch.setattr(
        limits.Path,
        "read_text",
        lambda *a, **k: "MemTotal: 16000000 kB\nMemFree: 100 kB\nMemAvailable: 2048000 kB\n",
    )
    assert limits.available_memory_bytes() == 2048000 * 1024


@pytest.mark.parametrize(
    "content",
    ["", "MemAvailable: wrong kB", "MemAvailable: 42 MB", "MemAvailable: -1 kB"],
)
def test_unavailable_or_invalid_memory_information_falls_back(monkeypatch, content):
    monkeypatch.setattr(limits.sys, "platform", "linux")
    monkeypatch.setattr(limits.Path, "read_text", lambda *a, **k: content)
    assert limits.available_memory_bytes() is None
    assert limits.recommended_working_budget() == limits.FALLBACK_WORKING_BYTES


def test_windows_probe_failure_is_optional(monkeypatch):
    monkeypatch.setattr(limits.sys, "platform", "win32")

    def fail():
        raise OSError("system information unavailable")

    monkeypatch.setattr(limits, "_windows_available_memory", fail)
    assert limits.available_memory_bytes() is None
    assert limits.recommended_working_budget() == limits.FALLBACK_WORKING_BYTES

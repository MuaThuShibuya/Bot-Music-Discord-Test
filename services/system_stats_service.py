from __future__ import annotations

import os
import resource
import shutil
import sys
import time
from dataclasses import dataclass


PROCESS_STARTED_MONOTONIC = time.monotonic()


@dataclass(frozen=True)
class SystemStats:
    bot_uptime_seconds: int
    vps_uptime_seconds: int | None
    ram_used_bytes: int | None
    ram_total_bytes: int | None
    process_memory_bytes: int | None
    disk_used_bytes: int
    disk_total_bytes: int
    disk_free_bytes: int


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "Không xác định"
    remaining = max(0, int(seconds))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes, seconds = divmod(remaining, 60)
    parts = []
    if days:
        parts.append(f"{days} ngày")
    if hours:
        parts.append(f"{hours} giờ")
    if minutes:
        parts.append(f"{minutes} phút")
    if seconds or not parts:
        parts.append(f"{seconds} giây")
    return " ".join(parts)


def format_bytes(value: int | None) -> str:
    if value is None:
        return "Không xác định"
    size = float(max(0, value))
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        if size < 1024 or unit == units[-1]:
            precision = 0 if unit == "B" else 2
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def format_usage(used: int | None, total: int | None) -> str:
    if used is None or total is None or total <= 0:
        return "Không xác định"
    percent = used / total * 100
    return f"{format_bytes(used)} / {format_bytes(total)} ({percent:.1f}%)"


def _read_vps_uptime() -> int | None:
    try:
        with open("/proc/uptime", encoding="utf-8") as file:
            return int(float(file.read().split()[0]))
    except (OSError, ValueError, IndexError):
        clock_id = getattr(time, "CLOCK_BOOTTIME", None)
        if clock_id is None:
            return None
        try:
            return int(time.clock_gettime(clock_id))
        except (OSError, ValueError):
            return None


def _read_ram_usage() -> tuple[int | None, int | None]:
    try:
        values = {}
        with open("/proc/meminfo", encoding="utf-8") as file:
            for line in file:
                key, raw_value = line.split(":", 1)
                values[key] = int(raw_value.strip().split()[0]) * 1024
        total = values["MemTotal"]
        available = values.get("MemAvailable", values.get("MemFree", 0))
        return max(0, total - available), total
    except (OSError, ValueError, KeyError):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            total_pages = os.sysconf("SC_PHYS_PAGES")
            available_pages = os.sysconf("SC_AVPHYS_PAGES")
            total = page_size * total_pages
            return total - (page_size * available_pages), total
        except (OSError, ValueError, TypeError):
            return None, None


def _read_process_memory() -> int | None:
    try:
        with open("/proc/self/status", encoding="utf-8") as file:
            for line in file:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass

    try:
        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(max_rss if sys.platform == "darwin" else max_rss * 1024)
    except (OSError, ValueError):
        return None


def collect_system_stats(disk_path: str = "/") -> SystemStats:
    ram_used, ram_total = _read_ram_usage()
    disk = shutil.disk_usage(disk_path)
    return SystemStats(
        bot_uptime_seconds=int(time.monotonic() - PROCESS_STARTED_MONOTONIC),
        vps_uptime_seconds=_read_vps_uptime(),
        ram_used_bytes=ram_used,
        ram_total_bytes=ram_total,
        process_memory_bytes=_read_process_memory(),
        disk_used_bytes=disk.used,
        disk_total_bytes=disk.total,
        disk_free_bytes=disk.free,
    )

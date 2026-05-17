#!/usr/bin/env python3
"""
B-log-strategies/lib/log_parse.py

Shared log-parsing utilities: Open5GS log regex, severity levels,
variable-token patterns, and template normalisation.
"""
import re

LOG_RE = re.compile(
    r'^(?P<date>\d{2}/\d{2})\s+'
    r'(?P<time>\d{2}:\d{2}:\d{2}\.\d+):\s+'
    r'\[(?P<component>[^\]]+)\]\s+'
    r'(?P<level>\w+):\s*'
    r'(?P<message>.*)',
    re.DOTALL,
)

LEVEL_ORDER = {
    "DEBUG": 0, "INFO": 1,
    "WARNING": 2, "WARN": 2,
    "ERROR": 3, "CRITICAL": 4, "FATAL": 4,
}

_VAR_PATS = [
    re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
               re.IGNORECASE),              # UUID
    re.compile(r'\d+\.\d+\.\d+\.\d+(:\d+)?'),  # IP(:port)
    re.compile(r'0x[0-9a-fA-F]+'),         # hex literal
    re.compile(r'imsi-\S+'),               # IMSI
    re.compile(r'suci-\S+'),               # SUCI
    re.compile(r'\bsupi-\S+'),             # SUPI
    re.compile(r'\(\.\./[^)]+\)'),         # (src/file.c:N)
    re.compile(r'\b\d{2}/\d{2}\b'),        # date MM/DD
    re.compile(r'\d{2}:\d{2}:\d{2}\.\d+'), # time HH:MM:SS.mmm
    re.compile(r'\b\d+\b'),                # standalone integer
]


def make_template(msg: str) -> str:
    t = msg
    for pat in _VAR_PATS:
        t = pat.sub('<*>', t)
    return re.sub(r'(<\*>\s*)+', '<*> ', t).strip()

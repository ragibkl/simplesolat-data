"""Shared utilities for fetch scripts."""

import calendar
import json
import os


def month_complete(path, year, month):
    """Check if existing prayer time file has complete month of data.

    Returns False if file doesn't exist or has fewer days than expected.
    Used by fetch scripts to detect partial months and re-fetch them.
    """
    if not os.path.exists(path):
        return False
    expected_days = calendar.monthrange(int(year), int(month))[1]
    try:
        with open(path) as f:
            data = json.load(f)
        return len(data) >= expected_days
    except (json.JSONDecodeError, IOError):
        return False

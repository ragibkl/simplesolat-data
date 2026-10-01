"""Shared utilities for fetch scripts."""

import calendar
import json
import os


def month_complete(path, year, month, require_field=None):
    """Check if existing prayer time file has complete month of data.

    Returns False if file doesn't exist or has fewer days than expected, or
    if require_field is given and missing from the records (so files written
    before a field was added get re-fetched).
    Used by fetch scripts to detect partial months and re-fetch them.
    """
    if not os.path.exists(path):
        return False
    expected_days = calendar.monthrange(int(year), int(month))[1]
    try:
        with open(path) as f:
            data = json.load(f)
        if require_field and not all(require_field in r for r in data):
            return False
        return len(data) >= expected_days
    except (json.JSONDecodeError, IOError):
        return False

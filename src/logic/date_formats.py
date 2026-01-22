"""Common date and datetime format lists used across the app.

Add formats here when you encounter new date/datetime string patterns.
"""

DATE_FORMATS = [
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d/%m/%Y",
    "%d/%m/%y",
    # Add more date-only patterns as needed
]

DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%m/%d/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %H:%M:%S",
    "%m/%d/%y %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M",
    "%d-%m-%y %H:%M:%S",
    "%d-%m-%y %H:%M",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%y %H:%M:%S",
    "%d/%m/%y %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%.f",
    # Add more datetime patterns as needed
]

# Optional: quick regex hints that can be used to pre-classify strings.
# Keep these conservative (not too greedy) and add more if needed.
DATE_REGEX_HINTS = [
    r"^\d{4}-\d{2}-\d{2}$",          # 2024-01-31
    r"^\d{1,2}/\d{1,2}/\d{2,4}$",   # 1/31/24 or 01/31/2024
    r"^\d{1,2}-\d{1,2}-\d{2,4}$",   # 31-01-2024
]

DATETIME_REGEX_HINTS = [
    r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(:\d{2})?(\.\d+)?$",
    r"^\d{1,2}/\d{1,2}/\d{2,4} \d{2}:\d{2}(:\d{2})?$",
]

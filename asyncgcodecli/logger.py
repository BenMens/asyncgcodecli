"""Loger."""


# FATAL     Severe errors that cause premature termination.
#           Expect these to be immediately visible on a status console.
# ERROR     Other runtime errors or unexpected conditions. Expect these
#           to be immediately visible on a status console.
# WARNING   Use of deprecated APIs, poor use of API, 'almost' errors,
#           other runtime situations that are undesirable or unexpected,
#           but not necessarily "wrong". Expect these to be immediately
#           visible on a status console.
# INFO      Interesting runtime events (startup/shutdown). Expect these
#           to be immediately visible on a console, so be conservative
#           and keep to a minimum.
# DEBUG     detailed information on the flow through the system.
#           Expect these to be written to logs only.
# TRACE     more detailed information. Expect these to be written
#           to logs only.

NONE = 0
FATAL = 1
ERROR = 2
WARNING = 3
INFO = 4
DEBUG = 5
TRACE = 6

__log_level = TRACE


__default_layout = {
    "level_name": "UNKNOWN",
    "format_string": "{color}{level_name:10} {msg}",
    "color": "\033[32m"
}


__layout = {
    NONE: {
        "level_name": "NONE"
    },
    FATAL: {
        "level_name": "FATAL",
        "color": "\033[31m"
    },
    ERROR: {
        "level_name": "ERROR",
        "color": "\033[31m"
    },
    WARNING: {
        "level_name": "WARNING",
        "color": "\033[33m"
    },
    INFO: {
        "level_name": "INFO"
    },
    DEBUG: {
        "level_name": "DEBUG"
    },
    TRACE: {
        "level_name": "TRACE"
    }
}


def set_log_level(level):
    """Set log level."""
    global __log_level
    __log_level = level


def log(level, msg, format=None, end='\n'):
    """Log a message."""
    if __log_level >= level:
        layout = {}
        layout.update(__default_layout)
        if level in __layout:
            layout.update(__layout[level])
        msg = msg.format(format)
        msg = layout['format_string'].format(msg=msg, **layout)

        print(msg, end=end, flush=True)


def append(level, msg, format=None, end='\n'):
    """Append to log a message."""
    if __log_level >= level:
        msg = msg.format(format)

        print(msg, end=end, flush=True)

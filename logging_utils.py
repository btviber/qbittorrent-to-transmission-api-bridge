"""
Logging utilities for the qBittorrent to Transmission RPC bridge
"""

# Verbosity levels:
# 0 = Errors and warnings only
# 1 = RPC operations (client actions) (-v)
# 2 = Full debug (including qBittorrent API calls) (-vv)
VERBOSITY = 0


def set_verbosity(level: int):
    """Set the global verbosity level"""
    global VERBOSITY
    VERBOSITY = level


def log_error(message: str):
    """Always print errors"""
    print(f"[ERROR] {message}")


def log_warning(message: str):
    """Always print warnings"""
    print(f"[WARNING] {message}")


def log_info(message: str):
    """Print info messages at verbosity level 1+ (RPC operations)"""
    if VERBOSITY >= 1:
        print(message)


def log_debug(message: str):
    """Print debug messages at verbosity level 2+ (QBT API calls)"""
    if VERBOSITY >= 2:
        print(message)

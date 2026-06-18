import os
from v4.utils.logger import log

DOCS_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "docs")

def read_one_pager() -> str:
    """Read the Investor One-Pager from the docs folder."""
    return _read_doc("one-pager.md")

def read_instructions() -> str:
    """Read the AI Instructions file from the docs folder."""
    return _read_doc("instructions.md")

def read_memory_log(last_n_days: int = 7) -> str:
    """
    Read the Memory Log from the docs folder.
    Returns the last N days of entries for context.
    """
    content = _read_doc("memory-log.md")
    if not content:
        return ""
    
    # Return full log if small, otherwise last portion
    lines = content.split("\n")
    if len(lines) <= 50:
        return content
    
    # Return last 50 lines as recent context
    return "\n".join(lines[-50:])

def append_memory_log(entry: str, category: str = "NOTE") -> bool:
    """
    Append a dated entry to the Memory Log.
    Categories: TRADE, MARKET, DECISION, PORTFOLIO, NOTE
    """
    from datetime import datetime
    import pytz
    eastern = pytz.timezone("America/New_York")
    today = datetime.now(eastern).strftime("%Y-%m-%d")
    
    log_path = os.path.join(DOCS_PATH, "memory-log.md")
    try:
        with open(log_path, "a") as f:
            f.write(f"\n[{today}] {category} — {entry}\n")
        log(f"Memory log updated: [{today}] {category}")
        return True
    except Exception as e:
        log(f"Memory log write error: {e}")
        return False

def _read_doc(filename: str) -> str:
    path = os.path.join(DOCS_PATH, filename)
    try:
        with open(path, "r") as f:
            return f.read()
    except FileNotFoundError:
        log(f"Document not found: {path}")
        return ""
    except Exception as e:
        log(f"Document read error for {filename}: {e}")
        return ""

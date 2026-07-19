import json
from datetime import datetime

STATUS_FILE = "bot_status.json"

def update_status(
    status="RUNNING",
    mode="Paper Trading",
    version="V6",
    current_pair=None,
    open_trade=None,
    scan_count=0,
    uptime=None,
):
    data = {
        "status": status,
        "mode": mode,
        "version": version,
        "current_pair": current_pair,
        "open_trade": open_trade,
        "scan_count": scan_count,
        "uptime": uptime,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=4)


def read_status():
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return None

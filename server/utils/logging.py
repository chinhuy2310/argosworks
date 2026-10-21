import sys
import os
import csv
from datetime import datetime, date

SERVER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = os.path.dirname(SERVER_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")

def log_line(*parts):
    print("[" + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "]", *parts, file=sys.stderr)

def access_log(request_ip, action, status, extra=""):
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fname = os.path.join(LOG_DIR, "access_" + date.today().strftime("%Y%m%d") + ".csv")
        is_new = not os.path.exists(fname)
        with open(fname, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["시각", "IP", "동작", "상태", "비고"])
            w.writerow([datetime.now().strftime("%Y-%m-%d %H:%M:%S"), request_ip, action, status, extra])
    except Exception as e:
        log_line("access_log 기록 실패:", e)

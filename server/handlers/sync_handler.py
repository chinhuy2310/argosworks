from services.jira_client import sync_jira_cache
from utils.logging import access_log

# ---- /api/sync (POST) — 대시보드의 "⟳ Jira 동기화" 버튼 ----
def handle_sync(handler, raw_body, ip):
    j = handler.cfg.get("jira", {}) if handler.cfg else {}
    if not j.get("enabled"):
        access_log(ip, "sync", 400, "jira=disabled")
        handler._send_json(400, {"ok": False, "error": "Jira 연동이 비활성화되어 있습니다."})
        return
    cache = sync_jira_cache(handler.cfg)
    count = len(cache["records"] or [])
    try:
        from services.vector_store import trigger_async_vector_sync
        trigger_async_vector_sync(handler.cfg)
    except Exception:
        pass
    access_log(ip, "sync", 200, "jira=%d error=%s" % (count, cache["error"] or "-"))
    handler._send_json(200, {"ok": True, "syncedAt": cache["synced_at"], "count": count,
                           "error": cache["error"]})

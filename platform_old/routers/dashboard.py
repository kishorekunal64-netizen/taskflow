import threading
import logging

from fastapi import APIRouter, Request

from platform.result_cache import cache
from platform.models import DashboardResponse
from platform.db import get_conn

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _log_activity(user_id: str, action: str, ip: str) -> None:
    def _write():
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO user_activity (user_id, action, ip_address) VALUES (%s, %s, %s)",
                        (user_id, action, ip),
                    )
                conn.commit()
        except Exception as e:
            logger.error(f"activity log failed: {e}")

    threading.Thread(target=_write, daemon=True).start()


@router.get("/api/dashboard", response_model=DashboardResponse)
def get_dashboard(request: Request):
    snapshot = cache.snapshot()
    _log_activity(request.state.user_id, "dashboard_access", _get_client_ip(request))
    return DashboardResponse(**snapshot)

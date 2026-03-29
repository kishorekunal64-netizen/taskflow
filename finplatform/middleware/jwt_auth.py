from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
import jwt
import os

EXEMPT_PATHS = {
    ("/auth/login", "POST"),
    ("/health", "GET"),
    ("/api/dashboard", "GET"),
}


class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if (request.url.path, request.method) in EXEMPT_PATHS:
            return await call_next(request)

        token = _extract_bearer(request)
        if not token:
            return JSONResponse({"detail": "Not authenticated"}, status_code=401)

        try:
            payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=["HS256"])
            request.state.user_id = payload["user_id"]
            request.state.role = payload["role"]
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

        return await call_next(request)


def _extract_bearer(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[len("Bearer "):]
    return None

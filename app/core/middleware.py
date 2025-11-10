from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        client_host = request.client.host if request.client else None
        ip = request.headers.get("x-forwarded-for", client_host)
        request.state.ip = ip
        request.state.user_agent = request.headers.get("user-agent")
        response = await call_next(request)
        return response

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.observability import correlation_context, ensure_correlation_id


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        client_host = request.client.host if request.client else None
        ip = request.headers.get("x-forwarded-for", client_host)
        request.state.ip = ip
        request.state.user_agent = request.headers.get("user-agent")

        incoming_corr = request.headers.get("x-correlation-id")
        corr_id = ensure_correlation_id(incoming_corr or "http")

        # Propagate correlation id for downstream handlers
        request.state.correlation_id = corr_id

        # Ensure logging context is set for the duration of the request
        with correlation_context(corr_id):
            response = await call_next(request)
            if response is not None:
                response.headers["x-correlation-id"] = corr_id
            return response

from urllib.parse import urlsplit

from fastapi import Request, Response


async def check_request_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if (parsed.scheme, parsed.netloc) != (request.url.scheme, request.url.netloc):
                return Response(status_code=403, content="Nguồn yêu cầu không hợp lệ")
        elif request.headers.get("sec-fetch-site") == "cross-site":
            return Response(status_code=403, content="Nguồn yêu cầu không hợp lệ")
    return await call_next(request)

RETRYABLE_STATUSES = {408, 409, 425, 429}


def _status(exc: BaseException):
    code = getattr(exc, "status_code", None)
    if code is None:
        resp = getattr(exc, "response", None)
        code = getattr(resp, "status_code", None)
    return code


def is_retryable(exc: BaseException) -> bool:
    code = _status(exc)
    if isinstance(code, int):
        return code in RETRYABLE_STATUSES or code >= 500
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    name = type(exc).__name__
    return "Timeout" in name or "Connection" in name


def error_message(exc: BaseException, limit: int = 300) -> str:
    code = _status(exc)
    text = str(exc) or type(exc).__name__
    msg = f"HTTP {code}: {text}" if isinstance(code, int) else text
    return msg[:limit]

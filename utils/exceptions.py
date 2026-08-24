class AppException(Exception):
    def __init__(self, message: str, status_code: int = 400, headers: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.headers = headers
        super().__init__(message)


class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)


class UnauthorizedException(AppException):
    def __init__(self, message: str = "Could not validate credentials"):
        super().__init__(message, status_code=401, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenException(AppException):
    def __init__(self, message: str = "You don't have permission to access this resource"):
        super().__init__(message, status_code=403)


class ConflictException(AppException):
    def __init__(self, message: str = "Resource already exists"):
        super().__init__(message, status_code=409)
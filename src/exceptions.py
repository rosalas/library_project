class LibraryException(Exception):
    pass

class APIError(LibraryException):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code

class DataValidationError(LibraryException):
    pass

class CacheError(LibraryException):
    pass
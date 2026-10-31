"""Public, serializable errors. Never put credentials or raw upstream bodies here."""

class ProductError(Exception):
    def __init__(self, code: str, message: str, details=None, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.details = details or []
        self.retryable = retryable

    def as_dict(self):
        return {'code': self.code, 'message': str(self), 'details': self.details, 'retryable': self.retryable}

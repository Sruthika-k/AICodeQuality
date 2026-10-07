class QuotaExceeded(Exception):
    def __init__(self, message: str, retry_after: int = 0):
        super().__init__(message)
        self.retry_after = retry_after


class JobCancelled(Exception):
    """Raised when a background run is cancelled by the client."""

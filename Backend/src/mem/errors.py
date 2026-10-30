class MemoryError(Exception):
    """Safe, structured application error; never include memory contents."""

    def __init__(self, code: str, message: str = "", details: dict | None = None):
        self.code = code
        self.message = message or code
        self.details = details or {}
        super().__init__(f"{code}: {self.message}")

from filelock import FileLock, Timeout
from .errors import MemoryError

def acquire_lock(path):
    lock = FileLock(path, timeout=0)
    try: lock.acquire()
    except Timeout: raise MemoryError('STORE_BUSY','Another process owns this store') from None
    return lock

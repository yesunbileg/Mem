from pathlib import Path, PurePosixPath

from .errors import MemoryError


def resolve_safe_path(root: Path, relative_path: str, allowed_area: str) -> Path:
    parts = PurePosixPath(relative_path).parts
    if (
        not parts
        or PurePosixPath(relative_path).is_absolute()
        or ".." in parts
        or "\\" in relative_path
        or "\x00" in relative_path
        or ":" in relative_path
    ):
        raise MemoryError("VALIDATION_ERROR", "Unsafe relative path")
    root = Path(root).resolve()
    path = root.joinpath(*parts)
    area = root / allowed_area
    if not path.resolve().is_relative_to(
        area.resolve()
    ) or not area.resolve().is_relative_to(root):
        raise MemoryError("VALIDATION_ERROR", "Path outside allowed area")
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise MemoryError("VALIDATION_ERROR", "Symlink not supported")
    return path

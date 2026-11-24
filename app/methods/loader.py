from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.methods.schema import Method
from app.methods.taxonomy import RoadblockType

LIBRARY_DIR = Path(__file__).parent / "library"


class LibraryError(Exception):
    """A library file is invalid. The message always names the file."""


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        parts = []
        for err in exc.errors():
            where = ".".join(str(p) for p in err["loc"]) or "(root)"
            parts.append(f"{where}: {err['msg']}")
        return "; ".join(parts)
    return " ".join(str(exc).split())


def load_library(directory: Path | None = None) -> list[Method]:
    directory = directory or LIBRARY_DIR
    if not directory.is_dir():
        raise LibraryError(f"library folder not found: {directory}")
    methods: list[Method] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.yaml")):
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            method = Method.model_validate(raw)
        except (yaml.YAMLError, ValidationError) as exc:
            raise LibraryError(f"{path.name}: {_describe(exc)}") from exc
        if method.slug != path.stem:
            raise LibraryError(f"{path.name}: slug '{method.slug}' must match the file name")
        if method.slug in seen:
            raise LibraryError(f"{path.name}: duplicate slug '{method.slug}'")
        seen.add(method.slug)
        methods.append(method)
    return methods


@lru_cache
def get_library() -> tuple[Method, ...]:
    return tuple(load_library())


def get_method(slug: str) -> Method | None:
    return next((m for m in get_library() if m.slug == slug), None)


def methods_for(roadblock: RoadblockType) -> list[Method]:
    return [m for m in get_library() if roadblock in m.targets]

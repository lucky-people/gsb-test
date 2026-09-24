"""dirsync：纯标准库的目录快照 / 差异 / 同步工具。"""

from . import errors
from .apply import ApplyReport, apply, verify
from .diff import DiffResult, diff_manifests
from .errors import ApplyError, DirsyncError, ManifestError
from .manifest import Manifest, ManifestEntry, snapshot

__all__ = [
    "errors",
    "snapshot",
    "Manifest",
    "ManifestEntry",
    "diff_manifests",
    "DiffResult",
    "apply",
    "ApplyReport",
    "verify",
    "DirsyncError",
    "ManifestError",
    "ApplyError",
]

__version__ = "0.1.0"

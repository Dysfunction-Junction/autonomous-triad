#!/usr/bin/env python3
# Tags: docker, morphogenetic, verification
# Links: triad/docker_runner.py, triad/ts_verify/Dockerfile, triad/ts_verify/verify-ts
# Queries: "how is TypeScript verified in a container", "how is the exocortex-verify image tagged"
"""ts_verify: SH-0 TypeScript verification image (owner decision D12).

The engine can only verify Python by itself; most of the repo is TypeScript.
This module names, builds, and profiles the ``exocortex-verify`` image that
closes that gap:

* Image tag: ``exocortex-verify:<first 12 of sha256(pnpm-lock.yaml)>``.
  ``package.json``, lockfiles and ``tsconfig`` are already protected mutation
  targets, so no candidate can invalidate the image a run was built for.
* Build (host, network allowed at build time only): a staged context with the
  root manifests plus every workspace ``package.json`` (relative paths kept),
  then ``pnpm install --frozen-lockfile`` into ``/deps``.
* Run (no network, read-only root): ``/usr/local/bin/verify-ts`` copies
  ``/work`` to a 2g tmpfs, links each ``/deps/<pkg>/node_modules`` into place,
  then runs ``tsc --noEmit -p <pkg>`` and/or the named test files. ``/work``
  is never written, so the engine's unchanged-workspace check keeps passing.
* No image for the current lockfile hash: refuse to run (never pull).
"""

import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

TS_VERIFY_IMAGE_PREFIX = "exocortex-verify"
TS_VERIFY_TMPFS_SIZE = "2g"
VERIFY_TS_PATH = "/usr/local/bin/verify-ts"
MAX_TEST_FILES = 20

SOURCE_DIR = Path(__file__).resolve().parent
DOCKERFILE_NAME = "Dockerfile"
VERIFY_TS_NAME = "verify-ts"

_PKG_RE = re.compile(r"^(?:apps|packages)/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_TEST_COMPONENTS = {"test", "tests", "__tests__"}


def is_ts_verify_image(image: str) -> bool:
    """True for images this module owns (``exocortex-verify:<hash>``)."""
    return image.startswith(TS_VERIFY_IMAGE_PREFIX + ":")


def image_tag_for_lockfile(repo_root: str | Path) -> str:
    """Tag for the repo's current lockfile. Raises FileNotFoundError without one."""
    lockfile = Path(repo_root).resolve() / "pnpm-lock.yaml"
    if not lockfile.is_file():
        raise FileNotFoundError(f"no pnpm-lock.yaml under {Path(repo_root).resolve()}")
    digest = hashlib.sha256(lockfile.read_bytes()).hexdigest()[:12]
    return f"{TS_VERIFY_IMAGE_PREFIX}:{digest}"


def _validate_package(package: str, repo_root: Optional[Path] = None) -> str:
    pkg = (package or "").strip().replace("\\", "/")
    if not _PKG_RE.match(pkg):
        raise ValueError(f"package must look like apps/<ws> or packages/<ws>: {package!r}")
    if repo_root is not None:
        root = Path(repo_root).resolve()
        if not (root / pkg).is_dir() or not (root / pkg / "package.json").is_file():
            raise ValueError(f"package not in repo {root}: {pkg}")
    return pkg


def _looks_like_test(rel: str) -> bool:
    if ".test." in rel or ".spec." in rel:
        return True
    return any(part in _TEST_COMPONENTS for part in rel.split("/"))


def _validate_test_file(package: str, rel: str, repo_root: Optional[Path] = None) -> str:
    text = (rel or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or ".." in text.split("/"):
        raise ValueError(f"test file must be a repo-relative path without '..': {rel!r}")
    if not text.startswith(package + "/"):
        raise ValueError(f"test file is outside {package}: {rel!r}")
    if not _looks_like_test(text):
        raise ValueError(f"not recognisably a test file: {rel!r}")
    if repo_root is not None and not (Path(repo_root).resolve() / text).is_file():
        raise ValueError(f"test file missing from repo: {text}")
    return text


def ts_profile_argv(
    package: str,
    *,
    run_tsc: bool = False,
    test_files: Optional[List[str]] = None,
    repo_root: Optional[str | Path] = None,
) -> List[str]:
    """Trusted argv for a DockerRunner profile. Validates like verify-ts does.

    Raises ValueError on anything the in-image script would refuse, so a bad
    profile fails fast on the host instead of inside the container.
    """
    root = Path(repo_root).resolve() if repo_root is not None else None
    pkg = _validate_package(package, root)
    files = [_validate_test_file(pkg, f, root) for f in (test_files or [])]
    if len(files) > MAX_TEST_FILES:
        raise ValueError(f"too many test files (max {MAX_TEST_FILES})")
    if not run_tsc and not files:
        raise ValueError("nothing to do: pass run_tsc=True and/or test files")
    return [VERIFY_TS_PATH, pkg] + (["--tsc"] if run_tsc else []) + files


def workspace_package_jsons(repo_root: str | Path) -> List[str]:
    """Repo-relative workspace manifests (apps/*/ and packages/*/package.json)."""
    root = Path(repo_root).resolve()
    found: List[str] = []
    for top in ("apps", "packages"):
        base = root / top
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            manifest = child / "package.json"
            if child.is_dir() and not child.is_symlink() and manifest.is_file():
                found.append(f"{top}/{child.name}/package.json")
    return found


def _stage_build_context(repo_root: str | Path, dest: Path) -> None:
    root = Path(repo_root).resolve()
    for name in ("package.json", "pnpm-workspace.yaml", "pnpm-lock.yaml"):
        src = root / name
        if not src.is_file():
            raise FileNotFoundError(f"cannot stage verify-image context: missing {name} under {root}")
        shutil.copyfile(src, dest / name)
    for rel in workspace_package_jsons(root):
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, target)
    dockerfile = SOURCE_DIR / DOCKERFILE_NAME
    script = SOURCE_DIR / VERIFY_TS_NAME
    if not dockerfile.is_file() or not script.is_file():
        raise FileNotFoundError(f"verify-image sources missing under {SOURCE_DIR}")
    shutil.copyfile(dockerfile, dest / DOCKERFILE_NAME)
    # The script runs in a Linux container: force LF even if the checkout uses CRLF.
    raw = script.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    (dest / VERIFY_TS_NAME).write_bytes(raw)


def build_ts_verify_image(
    repo_root: str | Path,
    *,
    docker_bin: Optional[str] = None,
    timeout: int = 600,
) -> str:
    """Explicit host-side build step (network allowed here, nowhere else). Returns the tag.

    Raises FileNotFoundError when the repo cannot supply a staged context, and
    RuntimeError with the docker output tail when the build itself fails.
    """
    from triad.docker_runner import IsolationUnavailable

    root = Path(repo_root).resolve()
    tag = image_tag_for_lockfile(root)
    docker = docker_bin or shutil.which("docker") or "docker"
    with tempfile.TemporaryDirectory(prefix="exocortex-verify-") as td:
        context = Path(td)
        _stage_build_context(root, context)
        try:
            res = subprocess.run(
                [docker, "build", "-t", tag, str(context)],
                capture_output=True, text=True, timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise IsolationUnavailable(f"docker not usable for verify-image build: {e}")
    if res.returncode != 0:
        tail = ((res.stdout or "") + "\n" + (res.stderr or "")).strip().splitlines()[-15:]
        raise RuntimeError(f"verify-image build failed for {tag}:\n" + "\n".join(tail))
    return tag


def make_ts_verify_runner(
    repo_root: str | Path,
    profiles: Dict[str, List[str]],
    *,
    memory: str = "4g",
    cpus: str = "2",
    **kwargs,
) -> "object":
    """DockerRunner pinned to the repo's current verify-image tag with a 2g tmpfs.

    Callers must still call ``ensure_image()``, which refuses to pull a missing
    verify image (build it first with :func:`build_ts_verify_image`).
    """
    from triad.docker_runner import DockerRunner

    tag = image_tag_for_lockfile(repo_root)
    return DockerRunner(
        profiles,
        image=tag,
        memory=memory,
        cpus=cpus,
        tmpfs_size=TS_VERIFY_TMPFS_SIZE,
        **kwargs,
    )

"""Patch and path scope firewall for DNA-Lang Evolver."""
import fnmatch
import os
import re
from typing import Any, Dict, List, Set, Tuple


class ScopeViolation(Exception):
    """Raised when a patch violates declared contract boundaries."""


def normalize_patch_path(raw_path: str) -> str:
    """Normalize a path from a diff header and verify sanity."""
    clean = raw_path.strip()
    if clean.startswith("a/") or clean.startswith("b/"):
        clean = clean[2:]
    if clean.startswith("/"):
        raise ScopeViolation(f"PATH_NOT_NORMALIZED: Absolute path rejected: {raw_path}")
    if "\\" in clean:
        raise ScopeViolation(f"PATH_NOT_NORMALIZED: Windows backslash path rejected: {raw_path}")
    
    parts = clean.split("/")
    if ".." in parts or "." in parts:
        raise ScopeViolation(f"PATH_TRAVERSAL_DETECTED: Directory traversal rejected: {raw_path}")
    
    return clean


def parse_patch_files(patch_str: str) -> Set[str]:
    """Extract touched target file paths from a unified diff."""
    files: Set[str] = set()
    lines = patch_str.splitlines()

    for line in lines:
        if line.startswith("+++ "):
            # Example: +++ b/src/kernel/sparse_matvec.py or +++ src/kernel/sparse_matvec.py
            target = line[4:].strip()
            # If target is /dev/null (file deletion), check --- line instead
            if target == "/dev/null":
                continue
            normalized = normalize_patch_path(target)
            files.add(normalized)
        elif line.startswith("--- "):
            source = line[4:].strip()
            if source != "/dev/null":
                normalized = normalize_patch_path(source)
                files.add(normalized)
        elif "GIT binary patch" in line or "Binary files" in line:
            raise ScopeViolation("UNSUPPORTED_FILE_CHANGE: Binary diffs are strictly prohibited")
        elif "new file mode 120000" in line or "deleted file mode 120000" in line:
            raise ScopeViolation("UNSUPPORTED_FILE_CHANGE: Symlink changes are strictly prohibited")
        elif "Subproject commit" in line:
            raise ScopeViolation("UNSUPPORTED_FILE_CHANGE: Submodule changes are strictly prohibited")

    return files


def matches_glob_list(path: str, glob_list: List[str]) -> bool:
    """Check if path matches any glob pattern in glob_list."""
    for pattern in glob_list:
        if fnmatch.fnmatch(path, pattern):
            return True
        # Handle trailing /** patterns cleanly
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if path.startswith(prefix + "/") or path == prefix:
                return True
    return False


def validate_patch_scope(patch_str: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a candidate patch against the contract's scope rules.
    
    Enforces:
    1. Patch byte limit.
    2. Path normalization & traversal rejection.
    3. Maximum files changed budget.
    4. Mutable paths allowlist.
    5. Immutable paths denylist (firewall).
    """
    scope = contract.get("scope", {})
    max_patch_bytes = scope.get("max_patch_bytes", 32768)
    max_files_changed = scope.get("max_files_changed", 2)
    mutable_paths = scope.get("mutable_paths", [])
    immutable_paths = scope.get("immutable_paths", [])

    patch_bytes = len(patch_str.encode("utf-8"))
    if patch_bytes > max_patch_bytes:
        return {
            "allowed": False,
            "reason_code": "PATCH_BYTE_BUDGET_EXCEEDED",
            "message": f"Patch size ({patch_bytes} bytes) exceeds limit ({max_patch_bytes} bytes)",
            "details": {"patch_bytes": patch_bytes, "limit": max_patch_bytes}
        }

    try:
        touched_files = parse_patch_files(patch_str)
    except ScopeViolation as e:
        return {
            "allowed": False,
            "reason_code": str(e).split(":")[0],
            "message": str(e),
            "details": {}
        }

    if not touched_files:
        return {
            "allowed": False,
            "reason_code": "EMPTY_PATCH",
            "message": "No valid files found in patch diff",
            "details": {}
        }

    if len(touched_files) > max_files_changed:
        return {
            "allowed": False,
            "reason_code": "TOO_MANY_FILES_CHANGED",
            "message": f"Patch touches {len(touched_files)} files, exceeding budget of {max_files_changed}",
            "details": {"touched_files": list(touched_files), "limit": max_files_changed}
        }

    for file_path in touched_files:
        # Check immutable paths first (evaluator, policy, tests, etc.)
        if matches_glob_list(file_path, immutable_paths):
            return {
                "allowed": False,
                "reason_code": "IMMUTABLE_PATH_MODIFIED",
                "message": f"Access denied: '{file_path}' is protected by immutable_paths contract",
                "details": {"violated_path": file_path, "immutable_patterns": immutable_paths}
            }

        # Check mutable paths allowlist
        if not matches_glob_list(file_path, mutable_paths):
            return {
                "allowed": False,
                "reason_code": "PATH_OUTSIDE_MUTATION_SCOPE",
                "message": f"Access denied: '{file_path}' is not within mutable_paths",
                "details": {"violated_path": file_path, "allowed_patterns": mutable_paths}
            }

    return {
        "allowed": True,
        "reason_code": "SCOPE_VALID",
        "message": f"Patch touches {len(touched_files)} file(s) within allowed scope",
        "details": {
            "touched_files": sorted(list(touched_files)),
            "patch_bytes": patch_bytes
        }
    }

"""AST and Semantic Capability Firewall for DNA-Lang Evolver."""
import ast
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ASTValidationError(Exception):
    """Raised when an AST invariant or capability rule is violated."""


PROHIBITED_CALL_NAMES = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "open",
    "system",
    "popen",
    "run",
    "Popen",
    "socket",
    "connect",
    "get",
    "post",
    "getattr",
    "setattr",
    "globals",
    "locals",
}


def apply_unified_diff(original: str, patch: str) -> str:
    """Apply a unified diff string to an original text deterministically."""
    orig_lines = original.splitlines(keepends=True)
    patch_lines = patch.splitlines(keepends=True)

    result_lines = []
    orig_idx = 0
    p_idx = 0

    # Match hunk header: @@ -start,len +start,len @@
    hunk_regex = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

    while p_idx < len(patch_lines):
        line = patch_lines[p_idx]
        if line.startswith("---") or line.startswith("+++"):
            p_idx += 1
            continue

        match = hunk_regex.match(line)
        if match:
            old_start = int(match.group(1)) - 1
            old_len = int(match.group(2)) if match.group(2) is not None else 1
            p_idx += 1

            # Copy unchanged lines leading up to hunk
            while orig_idx < old_start and orig_idx < len(orig_lines):
                result_lines.append(orig_lines[orig_idx])
                orig_idx += 1

            hunk_orig_read = 0
            while p_idx < len(patch_lines) and not patch_lines[p_idx].startswith("@@"):
                h_line = patch_lines[p_idx]
                if h_line.startswith(" "):
                    result_lines.append(orig_lines[orig_idx])
                    orig_idx += 1
                    hunk_orig_read += 1
                elif h_line.startswith("+"):
                    result_lines.append(h_line[1:])
                elif h_line.startswith("-"):
                    orig_idx += 1
                    hunk_orig_read += 1
                elif h_line.startswith("\\"):
                    # \ No newline at end of file
                    pass
                p_idx += 1
            continue
        p_idx += 1

    # Copy any remaining original lines
    while orig_idx < len(orig_lines):
        result_lines.append(orig_lines[orig_idx])
        orig_idx += 1

    return "".join(result_lines)


class CapabilityVisitor(ast.NodeVisitor):
    """Inspects AST for forbidden imports, dangerous calls, reflection, or OS accesses."""

    def __init__(self, allowed_imports: Set[str]):
        self.allowed_imports = allowed_imports
        self.violations: List[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            base_mod = alias.name.split(".")[0]
            if base_mod not in self.allowed_imports:
                self.violations.append(f"PROHIBITED_CAPABILITY:new_import '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        base_mod = mod.split(".")[0]
        if base_mod not in self.allowed_imports:
            self.violations.append(f"PROHIBITED_CAPABILITY:new_import_from '{mod}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        func = node.func
        func_name = None

        if isinstance(func, ast.Name):
            func_name = func.id
        elif isinstance(func, ast.Attribute):
            func_name = func.attr

        if func_name and func_name in PROHIBITED_CALL_NAMES:
            self.violations.append(f"PROHIBITED_CALL:{func_name}")

        self.generic_visit(node)


def extract_top_level_symbols(tree: ast.AST) -> Dict[str, ast.AST]:
    """Map top-level symbol names to their AST nodes."""
    symbols = {}
    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols[target.id] = node
    return symbols


def extract_imports(tree: ast.AST) -> Set[str]:
    """Extract set of imported root module names."""
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
    return imports


def count_ast_nodes(node: ast.AST) -> int:
    """Recursively count all AST nodes in a subtree."""
    return sum(1 for _ in ast.walk(node))


def validate_ast(original_source: str, candidate_source: str, contract: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that candidate source code adheres to AST structural and capability rules."""
    mutation = contract.get("mutation", {})
    scope = contract.get("scope", {})
    allowed_symbols = set(mutation.get("allowed_symbols", []))
    max_ast_nodes_changed = scope.get("max_ast_nodes_changed", 80)

    # 1. Parse parent AST
    try:
        parent_tree = ast.parse(original_source)
    except SyntaxError as e:
        return {
            "allowed": False,
            "reason_code": "PARENT_SYNTAX_ERROR",
            "message": f"Parent source has syntax error: {e}",
            "details": {}
        }

    # 2. Parse candidate AST
    try:
        candidate_tree = ast.parse(candidate_source)
    except SyntaxError as e:
        return {
            "allowed": False,
            "reason_code": "SYNTAX_INVALID",
            "message": f"Candidate code has syntax error: {e}",
            "details": {"line": e.lineno, "offset": e.offset, "text": e.text}
        }

    parent_symbols = extract_top_level_symbols(parent_tree)
    candidate_symbols = extract_top_level_symbols(candidate_tree)
    parent_imports = extract_imports(parent_tree)

    # 3. Check for modified/added/deleted symbols
    changed_symbols = []
    total_changed_nodes = 0

    all_symbols = set(parent_symbols.keys()) | set(candidate_symbols.keys())
    for sym in all_symbols:
        p_node = parent_symbols.get(sym)
        c_node = candidate_symbols.get(sym)

        if p_node is None:
            # New symbol
            changed_symbols.append(sym)
            total_changed_nodes += count_ast_nodes(c_node)
        elif c_node is None:
            # Deleted symbol
            changed_symbols.append(sym)
            total_changed_nodes += count_ast_nodes(p_node)
        else:
            # Compare dumps of the subtrees
            p_dump = ast.dump(p_node, include_attributes=False)
            c_dump = ast.dump(c_node, include_attributes=False)
            if p_dump != c_dump:
                changed_symbols.append(sym)
                # Count nodes in the modified subtree
                diff_count = abs(count_ast_nodes(c_node) - count_ast_nodes(p_node)) + 1
                total_changed_nodes += diff_count

    # Enforce: only allowed symbols may change
    for sym in changed_symbols:
        if sym not in allowed_symbols:
            return {
                "allowed": False,
                "reason_code": "SYMBOL_OUTSIDE_ALLOWED_SCOPE",
                "message": f"Symbol '{sym}' was modified, but only {list(allowed_symbols)} are allowed",
                "details": {"violated_symbol": sym, "allowed_symbols": list(allowed_symbols)}
            }

    # Enforce: AST change budget
    if total_changed_nodes > max_ast_nodes_changed:
        return {
            "allowed": False,
            "reason_code": "AST_CHANGE_BUDGET_EXCEEDED",
            "message": f"Changed AST node count ({total_changed_nodes}) exceeds limit ({max_ast_nodes_changed})",
            "details": {"changed_nodes": total_changed_nodes, "limit": max_ast_nodes_changed}
        }

    # 4. Capability inspection (forbidden imports & calls)
    visitor = CapabilityVisitor(allowed_imports=parent_imports)
    visitor.visit(candidate_tree)

    if visitor.violations:
        first_violation = visitor.violations[0]
        code = first_violation.split(":")[0]
        return {
            "allowed": False,
            "reason_code": code,
            "message": f"Security capability violation: {first_violation}",
            "details": {"all_violations": visitor.violations}
        }

    return {
        "allowed": True,
        "reason_code": "AST_VALID",
        "message": f"AST modifications to {changed_symbols} verified within capability budget",
        "details": {
            "changed_symbols": changed_symbols,
            "total_changed_nodes": total_changed_nodes
        }
    }

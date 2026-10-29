"""Autonomous Agent Workspace Tools.

Provides safe, audited local tools for file inspection, surgical editing, and shell execution.
Follows the agy/Claude Code permission model:
- Read-only tools (read_file, list_dir, search_code) execute automatically within workspace bounds.
- Destructive tools (write_file, edit_file, run_command) require interactive user confirmation
  unless the session was started with --auto / -y.
- Workspace containment and secret leaks prevention are strictly enforced.
"""

import os
import re
import subprocess
import fnmatch
from pathlib import Path
from typing import Dict, Any, Optional

DENIED_SECRET_PATTERNS = {
    ".env", ".env.local", "id_rsa", "id_ed25519", "auth.json",
    "credentials.json", "service_account.json", "*.keystore", "*.pem", "*.key"
}


class ToolRegistry:
    def __init__(self, workspace_root: Optional[Path] = None, auto_approve: bool = False):
        self.workspace_root = Path(workspace_root or Path.cwd()).resolve()
        self.auto_approve = auto_approve

    def _resolve_path(self, path_str: str) -> Path:
        """Resolves path and enforces strict workspace containment."""
        p = Path(path_str)
        if not p.is_absolute():
            p = (self.workspace_root / p).resolve()
        else:
            p = p.resolve()

        # Workspace containment check
        try:
            p.relative_to(self.workspace_root)
        except ValueError:
            raise PermissionError(f"Access denied: path '{path_str}' escapes workspace boundary {self.workspace_root}")

        return p

    def _is_secret_file(self, path: Path) -> bool:
        """Deny-list check for sensitive security credentials."""
        name = path.name.lower()
        for pat in DENIED_SECRET_PATTERNS:
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    def _confirm(self, action_description: str) -> bool:
        """Prompt user for confirmation unless auto-approved."""
        if self.auto_approve:
            return True
        try:
            print(f"\n\033[1;33m[Permission Request]\033[0m {action_description}")
            choice = input("Authorize this action? [y/N]: ").strip().lower()
            return choice in ("y", "yes")
        except (KeyboardInterrupt, EOFError):
            print("\nAction declined by user.")
            return False

    def read_file(self, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Dict[str, Any]:
        """Read lines from a file with 1-based line numbers."""
        try:
            file_path = self._resolve_path(path)
        except PermissionError as pe:
            return {"error": str(pe)}

        if self._is_secret_file(file_path):
            return {"error": f"Security restriction: reading secret credential file '{file_path.name}' is prohibited."}

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}
        if file_path.is_dir():
            return {"error": f"Path is a directory, not a file: {file_path}"}

        try:
            with open(file_path, "r", encoding="utf-8", errors="strict") as f:
                lines = f.read().splitlines()

            total_lines = len(lines)
            s = max(1, start_line or 1)
            e = min(total_lines, end_line or total_lines)

            formatted = [f"{i}: {lines[i-1]}" for i in range(s, e + 1)]
            return {
                "path": str(file_path.relative_to(self.workspace_root)),
                "total_lines": total_lines,
                "showing_range": [s, e],
                "content": "\n".join(formatted),
            }
        except UnicodeDecodeError:
            return {"error": "Binary or non-UTF-8 file cannot be read as text."}
        except Exception as exc:
            return {"error": f"Failed to read file: {exc}"}

    def write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Create or completely overwrite a file."""
        try:
            file_path = self._resolve_path(path)
        except PermissionError as pe:
            return {"error": str(pe)}

        if self._is_secret_file(file_path):
            return {"error": f"Security restriction: modifying credential file '{file_path.name}' is prohibited."}

        action_msg = f"Write {len(content)} characters to {file_path.relative_to(self.workspace_root)}"
        if not self._confirm(action_msg):
            return {"error": "User rejected file write permission."}

        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            return {
                "status": "success",
                "path": str(file_path.relative_to(self.workspace_root)),
                "bytes_written": len(content.encode('utf-8'))
            }
        except Exception as exc:
            return {"error": f"Failed to write file: {exc}"}

    def edit_file(self, path: str, target: str, replacement: str, replace_all: bool = False) -> Dict[str, Any]:
        """Surgical replacement of exact matching string within a file."""
        try:
            file_path = self._resolve_path(path)
        except PermissionError as pe:
            return {"error": str(pe)}

        if self._is_secret_file(file_path):
            return {"error": f"Security restriction: editing credential file '{file_path.name}' is prohibited."}

        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        action_msg = f"Edit {file_path.relative_to(self.workspace_root)} (Replace {len(target)} chars with {len(replacement)} chars)"
        if not self._confirm(action_msg):
            return {"error": "User rejected file edit permission."}

        try:
            with open(file_path, "r", encoding="utf-8", newline="") as f:
                content = f.read()
        except UnicodeDecodeError:
            return {"error": "Refusing to edit binary or non-UTF-8 file."}
        except Exception as exc:
            return {"error": f"Failed to read file for editing: {exc}"}

        # Check match count
        count = content.count(target)
        if count == 0:
            return {"error": "Target string not found in file. Ensure exact character and whitespace match."}
        if count > 1 and not replace_all:
            return {"error": f"Target string appears {count} times in file. Ambiguous edit rejected to prevent corruption. Use replace_all=True if intentional."}

        updated = content.replace(target, replacement) if replace_all else content.replace(target, replacement, 1)

        try:
            with open(file_path, "w", encoding="utf-8", newline="") as f:
                f.write(updated)
            return {
                "status": "success",
                "path": str(file_path.relative_to(self.workspace_root)),
                "occurrences_replaced": count if replace_all else 1
            }
        except Exception as exc:
            return {"error": f"Failed to write edited file: {exc}"}

    def list_dir(self, path: str = ".", pattern: str = "*", recursive: bool = False) -> Dict[str, Any]:
        """List files and directories within a path."""
        try:
            target_dir = self._resolve_path(path)
        except PermissionError as pe:
            return {"error": str(pe)}

        if not target_dir.exists() or not target_dir.is_dir():
            return {"error": f"Directory not found: {target_dir}"}

        try:
            results = []
            if recursive:
                for root, dirs, files in os.walk(target_dir):
                    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__", "dist")]
                    for f in files:
                        if fnmatch.fnmatch(f, pattern):
                            full = Path(root) / f
                            results.append(str(full.relative_to(self.workspace_root)))
                            if len(results) >= 40:
                                break
                    if len(results) >= 40:
                        break
            else:
                for item in target_dir.iterdir():
                    if fnmatch.fnmatch(item.name, pattern):
                        kind = "dir" if item.is_dir() else "file"
                        results.append(f"[{kind}] {item.name}")
                        if len(results) >= 40:
                            break

            return {
                "path": str(target_dir.relative_to(self.workspace_root)) if target_dir != self.workspace_root else ".",
                "count": len(results),
                "items": results
            }
        except Exception as exc:
            return {"error": f"Failed to list directory: {exc}"}

    def search_code(self, pattern: str, path: str = ".") -> Dict[str, Any]:
        """Search for text across files in the workspace."""
        try:
            target_dir = self._resolve_path(path)
        except PermissionError as pe:
            return {"error": str(pe)}

        matches = []
        try:
            for root, dirs, files in os.walk(target_dir):
                dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__", "dist")]
                for f in files:
                    if f.endswith((".py", ".ts", ".js", ".json", ".md", ".yaml", ".yml", ".html", ".css", ".go", ".rs")):
                        full = Path(root) / f
                        if self._is_secret_file(full):
                            continue
                        try:
                            lines = full.read_text(encoding="utf-8", errors="ignore").splitlines()
                            for idx, line in enumerate(lines, 1):
                                if pattern.lower() in line.lower():
                                    rel = full.relative_to(self.workspace_root)
                                    matches.append(f"{rel}:{idx}: {line.strip()[:150]}")
                                    if len(matches) >= 30:
                                        break
                        except Exception:
                            pass
                    if len(matches) >= 30:
                        break
                if len(matches) >= 30:
                    break

            return {"pattern": pattern, "count": len(matches), "matches": matches}
        except Exception as exc:
            return {"error": f"Failed to search code: {exc}"}

    @staticmethod
    def _kill_tree(p: subprocess.Popen) -> None:
        """Kills the process and its full process tree cleanly across platforms."""
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
        else:
            try:
                import signal
                os.killpg(p.pid, signal.SIGKILL)
            except Exception:
                pass
        try:
            p.communicate(timeout=5)
        except Exception:
            pass

    def run_command(self, command: str) -> Dict[str, Any]:
        """Execute a shell command with a safety confirmation prompt and clean interrupt handling."""
        action_msg = f"Execute shell command: \033[1;36m{command}\033[0m"
        if not self._confirm(action_msg):
            return {"error": "User rejected command execution permission."}

        proc = None
        kw = {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}
        try:
            proc = subprocess.Popen(
                command,
                shell=True,  # nosec B602 - user-confirmed local tool, not an untrusted benchmark patch
                cwd=str(self.workspace_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                **kw
            )
            stdout, stderr = proc.communicate(timeout=120)
            return {
                "exit_code": proc.returncode,
                "stdout": stdout[:15000],
                "stderr": stderr[:5000],
            }
        except subprocess.TimeoutExpired:
            if proc:
                self._kill_tree(proc)
            return {"error": "Command timed out after 120 seconds."}
        except KeyboardInterrupt:
            if proc:
                self._kill_tree(proc)
            raise
        except Exception as exc:
            return {"error": f"Command execution failed: {exc}"}

    def consult_architect(self, query: str, context: Optional[str] = None) -> Dict[str, Any]:
        """Consults the Chief Architect (Claude 3.7 Sonnet / Codex) for big decisions, system architecture, or stubborn bug diagnoses."""
        # Comprehensive credential and secret token inspection
        combined = f"{query} {context or ''}"
        secret_patterns = [
            r"\bghp_[A-Za-z0-9]{36}\b",
            r"\bgithub_pat_[A-Za-z0-9_]{20,}\b",
            r"\bsk-[A-Za-z0-9_\-]{20,}",
            r"\bAKIA[0-9A-Z]{16}\b",
            r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        ]
        for pat in secret_patterns:
            if re.search(pat, combined):
                return {"error": "Security restriction: query/context contains sensitive credential tokens."}

        # Cap query and context to 20 KB
        capped_query = query[:20000]
        capped_context = context[:20000] if context else ""
        action_msg = (
            f"Consult Chief Architect (Claude 3.7 / Codex):\n"
            f"  Payload: {len(capped_query.encode('utf-8'))} bytes query, {len(capped_context.encode('utf-8'))} bytes context\n"
            f"  Preview: \033[1;35m{capped_query[:120]}\033[0m"
        )
        if not self._confirm(action_msg):
            return {"error": "User rejected architect consultation permission."}

        try:
            try:
                from triad.advisor_manager import query_configured_advisor
            except ImportError:
                from advisor_manager import query_configured_advisor

            advice = query_configured_advisor(
                advisor_name="claude",
                prompt=capped_query,
                context=capped_context,
                mode="architect",
                timeout=180
            )
            return {
                "advisor": "Chief Architect (Claude 3.7 / Codex)",
                "advice": advice
            }
        except Exception as exc:
            return {"error": f"Failed to consult Chief Architect: {exc}"}

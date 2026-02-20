import asyncio
import os
import re
import shutil
import signal
from datetime import UTC, datetime

from jarvis.observability.logger import get_logger
from jarvis.tools.base import Tool, ToolResult

# Version bump + changelog for self-modification commits
VERSION_FILE = "jarvis/version.py"
CHANGELOG_FILE = "CHANGELOG.md"

log = get_logger("tools.self_modify")

# Live code paths (in-container, ephemeral without backup)
LIVE_ROOTS = ["/app", "/frontend"]
# Persistent code paths (mounted volume, survives restarts)
BACKUP_ROOTS = {"/app": "/data/code/backend", "/frontend": "/data/code/frontend"}

# Paths JARVIS must NEVER modify (safety/logging — immutable)
FORBIDDEN_PATHS = [
    "/app/jarvis/safety/rules.py",
    "/app/jarvis/observability/logger.py",
    "/data/code/backend/jarvis/safety/rules.py",
    "/data/code/backend/jarvis/observability/logger.py",
]


def _backup_path(live_path: str) -> str | None:
    """Map a live path to its persistent backup path."""
    for live_root, backup_root in BACKUP_ROOTS.items():
        if live_path.startswith(live_root):
            return live_path.replace(live_root, backup_root, 1)
    return None


class SelfModifyTool(Tool):
    name = "self_modify"
    description = (
        "Read or modify JARVIS's own source code with version tracking and persistence. "
        "Changes are saved to both the live container AND /data/code/ (persists across restarts). "
        "Actions: 'read', 'write', 'list', 'diff', 'commit', 'push', 'log', 'revert', 'redeploy'."
    )
    timeout_seconds = 120

    def __init__(self, blob_storage=None):
        self.blob = blob_storage

    def _validate_path(self, path: str) -> tuple[bool, str]:
        """Check if path is within allowed roots and not forbidden."""
        real_path = os.path.realpath(path)
        if any(real_path == f or real_path.startswith(f + "/") for f in FORBIDDEN_PATHS):
            return False, f"Cannot modify protected file: {path} (immutable safety/logging)"
        all_roots = LIVE_ROOTS + list(BACKUP_ROOTS.values())
        if not any(real_path.startswith(root) for root in all_roots):
            return False, f"Path outside allowed roots: {path}"
        return True, ""

    async def execute(
        self,
        action: str = "list",
        path: str = "/app",
        content: str = None,
        message: str = None,
        remote: str = None,
        **kwargs,
    ) -> ToolResult:
        if action == "read":
            return await self._read(path)
        if action == "write":
            if content is None:
                return ToolResult(success=False, output="", error="'content' required for write action")
            return await self._write(path, content)
        if action == "list":
            return await self._list(path)
        if action == "diff":
            return await self._diff()
        if action == "commit":
            return await self._commit(message or "JARVIS self-modification")
        if action == "push":
            return await self._push(remote)
        if action == "log":
            return await self._log()
        if action == "revert":
            return await self._revert()
        if action == "redeploy":
            return await self._redeploy(message or "JARVIS self-modification redeploy")
        return ToolResult(
            success=False,
            output="",
            error=f"Unknown action: {action}. Use: read/write/list/diff/commit/push/log/revert/redeploy",
        )

    # ── Read ───────────────────────────────────────────────────────────────

    async def _read(self, path: str) -> ToolResult:
        ok, err = self._validate_path(path)
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            with open(path) as f:
                content = f.read()
            if len(content) > 50000:
                content = content[:50000] + "\n[...truncated...]"
            return ToolResult(success=True, output=content)
        except FileNotFoundError:
            return ToolResult(success=False, output="", error=f"File not found: {path}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Write (dual-write: live + persistent backup) ───────────────────────

    async def _write(self, path: str, content: str) -> ToolResult:
        ok, err = self._validate_path(path)
        if not ok:
            return ToolResult(success=False, output="", error=err)

        # Read old content for logging
        old_content = ""
        try:
            with open(path) as f:
                old_content = f.read()
        except FileNotFoundError:
            pass

        try:
            # Write to live path
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

            # Also write to persistent backup path
            backup = _backup_path(path)
            if backup:
                os.makedirs(os.path.dirname(backup), exist_ok=True)
                with open(backup, "w") as f:
                    f.write(content)

            # Log the modification
            if self.blob:
                self.blob.store(
                    event_type="self_modification",
                    content=f"Modified: {path}\nOld size: {len(old_content)} -> New size: {len(content)}",
                    metadata={
                        "file": path,
                        "backup": backup,
                        "old_size": len(old_content),
                        "new_size": len(content),
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            log.info("self_modify_write", path=path, backup=backup, old_size=len(old_content), new_size=len(content))
            return ToolResult(
                success=True,
                output=f"Written {len(content)} bytes to {path}" + (f" (backed up to {backup})" if backup else ""),
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── List ───────────────────────────────────────────────────────────────

    async def _list(self, path: str) -> ToolResult:
        ok, err = self._validate_path(path)
        if not ok:
            return ToolResult(success=False, output="", error=err)
        try:
            entries = []
            for entry in sorted(os.listdir(path)):
                entry_path = os.path.join(path, entry)
                is_dir = os.path.isdir(entry_path)
                if is_dir:
                    entries.append(f"[DIR]  {entry}/")
                else:
                    size = os.path.getsize(entry_path)
                    entries.append(f"{size:>8}B  {entry}")
            return ToolResult(success=True, output="\n".join(entries) if entries else "(empty)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Diff ───────────────────────────────────────────────────────────────

    async def _diff(self) -> ToolResult:
        """Show git diff in the persistent code backup."""
        try:
            cwd = "/data/code/backend"
            if not os.path.isdir(os.path.join(cwd, ".git")):
                return ToolResult(success=True, output="(no git repo in backup)")
            proc = await asyncio.create_subprocess_exec(
                "git",
                "diff",
                "--stat",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")
            if not output.strip():
                # Also show uncommitted files
                proc2 = await asyncio.create_subprocess_exec(
                    "git",
                    "status",
                    "--short",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=cwd,
                )
                stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=10)
                output = stdout2.decode("utf-8", errors="replace")
            return ToolResult(success=True, output=output.strip() or "(no changes)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Version bump + changelog (for commit) ──────────────────────────────

    def _get_current_version(self, cwd: str) -> str:
        """Read current version from jarvis/version.py or main.py fallback."""
        version_path = os.path.join(cwd, VERSION_FILE)
        main_path = os.path.join(cwd, "jarvis", "main.py")
        for path in [version_path, main_path]:
            if os.path.isfile(path):
                with open(path) as f:
                    content = f.read()
                m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if m:
                    return m.group(1)
        return "0.1.0"

    def _bump_patch(self, version: str) -> str:
        """Bump patch component: 0.2.0 -> 0.2.1."""
        parts = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", version)
        if parts:
            major, minor, patch, suffix = parts.groups()
            return f"{major}.{minor}.{int(patch) + 1}{suffix}"
        return version

    def _write_version(self, cwd: str, version: str) -> None:
        """Write version to jarvis/version.py."""
        path = os.path.join(cwd, VERSION_FILE)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        content = f'''"""Single source of truth for JARVIS version."""

__version__ = "{version}"
'''
        with open(path, "w") as f:
            f.write(content)

    def _append_changelog(self, cwd: str, version: str, message: str, files_changed: list[str]) -> None:
        """Append a changelog entry for this commit."""
        path = os.path.join(cwd, CHANGELOG_FILE)
        now = datetime.now(UTC).strftime("%Y-%m-%d")
        files_section = "\n".join(f"  - {f}" for f in sorted(files_changed)[:50])
        if len(files_changed) > 50:
            files_section += f"\n  - ... and {len(files_changed) - 50} more"
        entry = f"""
## [{version}] - {now}

**Commit:** {message}

### Files changed
{files_section}
"""
        if os.path.isfile(path):
            with open(path) as f:
                existing = f.read()
            # Ensure we have a header if file is empty or malformed
            if "## [" not in existing:
                existing = "# Changelog\n\nAll notable changes from JARVIS self-modifications.\n" + existing
            with open(path, "w") as f:
                f.write(existing.rstrip() + entry)
        else:
            with open(path, "w") as f:
                f.write("# Changelog\n\nAll notable changes from JARVIS self-modifications." + entry)

    async def _get_changed_files(self, cwd: str) -> list[str]:
        """Get list of staged/changed files for changelog."""
        try:
            out = await self._run_git(["diff", "--cached", "--name-only"], cwd)
            if out.strip():
                return [line.strip() for line in out.strip().split("\n") if line.strip()]
            out = await self._run_git(["status", "--short"], cwd)
            # Parse " M file" or "?? file" etc.
            files = []
            for line in out.strip().split("\n"):
                if len(line) >= 4:
                    files.append(line[3:].strip())
            return files
        except Exception:
            return []

    # ── Commit (to persistent backup repo) ─────────────────────────────────

    async def _commit(self, message: str) -> ToolResult:
        """Commit changes in the persistent /data/code/backend repo."""
        try:
            cwd = "/data/code/backend"
            if not os.path.isdir(cwd):
                return ToolResult(success=False, output="", error="No code backup directory")

            # Ensure git repo
            if not os.path.isdir(os.path.join(cwd, ".git")):
                await self._run_git(["init"], cwd)
                from jarvis.config import settings

                await self._run_git(["config", "user.name", settings.git_user_name], cwd)
                await self._run_git(["config", "user.email", settings.git_user_email], cwd)

            # Sync live code to backup before committing
            # (catches any files modified via code_exec or other tools)
            try:
                for src, dst in [
                    ("/app/", cwd + "/"),
                ]:
                    proc = await asyncio.create_subprocess_exec(
                        "rsync",
                        "-a",
                        "--exclude=.git",
                        "--exclude=__pycache__",
                        src,
                        dst,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
            except FileNotFoundError:
                # rsync not available, use cp
                pass

            await self._run_git(["add", "-A"], cwd)
            files_changed = await self._get_changed_files(cwd)

            # Auto-bump version and append changelog
            current = self._get_current_version(cwd)
            new_version = self._bump_patch(current)
            self._write_version(cwd, new_version)
            self._append_changelog(cwd, new_version, message, files_changed)

            # Sync version + changelog to live /app so running process reports correct version
            for f in [VERSION_FILE, CHANGELOG_FILE]:
                src = os.path.join(cwd, f)
                dst = os.path.join("/app", f)
                if os.path.isfile(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.copy2(src, dst)

            await self._run_git(["add", "-A"], cwd)
            commit_msg = f"v{new_version}: {message}"
            if files_changed:
                files_line = ", ".join(files_changed[:15])
                if len(files_changed) > 15:
                    files_line += f" (+{len(files_changed) - 15} more)"
                commit_msg += f"\n\nFiles changed: {files_line}"
            output = await self._run_git(["commit", "-m", commit_msg], cwd)

            if self.blob:
                self.blob.store(
                    event_type="self_modification_commit",
                    content=f"v{new_version}: {message}\n{output}",
                    metadata={"message": message, "version": new_version, "repo": cwd},
                )

            return ToolResult(success=True, output=f"Committed v{new_version}: {message}\n{output}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Push to GitHub ─────────────────────────────────────────────────────

    async def _push(self, remote: str = None) -> ToolResult:
        """Push committed changes to the remote git repository."""
        try:
            cwd = "/data/code/backend"

            # Check if remote exists
            remotes = await self._run_git(["remote", "-v"], cwd)
            if not remotes.strip():
                # Try env var first, then explicit parameter
                repo_url = remote or os.environ.get("GITHUB_REPO")
                if repo_url and "REPLACE" not in repo_url:
                    await self._run_git(["remote", "add", "origin", repo_url], cwd)
                    log.info("git_remote_added", url=repo_url)
                else:
                    return ToolResult(
                        success=False,
                        output="",
                        error="No remote configured. Set GITHUB_REPO in .env or use: self_modify action=push remote=https://github.com/user/repo.git",
                    )
            elif remote:
                # Update remote URL if explicitly given
                await self._run_git(["remote", "set-url", "origin", remote], cwd)

            # Push — try HEAD:main first (works regardless of local branch name)
            output = await self._run_git(["push", "-u", "origin", "HEAD:main"], cwd)

            # If rejected (non-fast-forward), try to pull --rebase then push
            if "rejected" in output.lower() or "non-fast-forward" in output.lower() or "fetch first" in output.lower():
                log.info("git_push_rejected_trying_pull", output=output[:200])

                # Ensure we have a local branch to rebase onto
                await self._run_git(["checkout", "-B", "main"], cwd)

                # Fetch and rebase
                await self._run_git(["fetch", "origin", "main"], cwd)
                rebase_output = await self._run_git(["rebase", "origin/main"], cwd)

                if "conflict" in rebase_output.lower():
                    # Abort rebase and force push instead
                    await self._run_git(["rebase", "--abort"], cwd)
                    log.warning("git_rebase_conflict_force_pushing")
                    output = await self._run_git(["push", "-u", "origin", "HEAD:main", "--force"], cwd)
                else:
                    # Rebase succeeded, try push again
                    output = await self._run_git(["push", "-u", "origin", "HEAD:main"], cwd)

            # If still failing (e.g. empty repo, first push), force push
            if "fatal" in output.lower() or "error" in output.lower():
                log.warning("git_push_fallback_force", output=output[:200])
                output = await self._run_git(["push", "-u", "origin", "HEAD:main", "--force"], cwd)

            if self.blob:
                self.blob.store(
                    event_type="git_push",
                    content=f"Pushed to remote\n{output}",
                    metadata={"remote": remote or "origin"},
                )

            return ToolResult(success=True, output=f"Push result:\n{output}")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Log (git history) ──────────────────────────────────────────────────

    async def _log(self) -> ToolResult:
        """Show recent git log from the persistent code repo."""
        try:
            cwd = "/data/code/backend"
            output = await self._run_git(["log", "--oneline", "--graph", "-20"], cwd)
            return ToolResult(success=True, output=output or "(no commits)")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Revert to previous commit ──────────────────────────────────────────

    async def _revert(self) -> ToolResult:
        """Revert to the previous commit (undo last self-modification)."""
        try:
            cwd = "/data/code/backend"

            # Get current and previous commit
            current = await self._run_git(["log", "--oneline", "-1"], cwd)
            output = await self._run_git(["reset", "--hard", "HEAD~1"], cwd)

            # Sync reverted code back to live
            try:
                proc = await asyncio.create_subprocess_exec(
                    "rsync",
                    "-a",
                    "--delete",
                    "--exclude=.git",
                    "--exclude=__pycache__",
                    cwd + "/",
                    "/app/",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            except FileNotFoundError:
                shutil.copytree(cwd, "/app", dirs_exist_ok=True)

            if self.blob:
                self.blob.store(
                    event_type="self_modification_revert",
                    content=f"Reverted from: {current}\n{output}",
                    metadata={"reverted_from": current.strip()},
                )

            return ToolResult(success=True, output=f"Reverted.\nWas: {current}\n{output}\nLive code updated.")
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Redeploy (commit + sync + graceful restart) ────────────────────────

    async def _redeploy(self, message: str) -> ToolResult:
        """Commit current changes, sync to live, and trigger a graceful process restart."""
        try:
            # 1. Commit
            commit_result = await self._commit(message)

            # 2. Sync backup -> live
            cwd = "/data/code/backend"
            try:
                proc = await asyncio.create_subprocess_exec(
                    "rsync",
                    "-a",
                    "--delete",
                    "--exclude=.git",
                    "--exclude=__pycache__",
                    cwd + "/",
                    "/app/",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()
            except FileNotFoundError:
                shutil.copytree(cwd, "/app", dirs_exist_ok=True)

            # 3. Validate the new code can at least import
            proc = await asyncio.create_subprocess_exec(
                "python",
                "-c",
                "import jarvis.main",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/app",
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            if proc.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                # Revert!
                await self._revert()
                return ToolResult(
                    success=False, output="", error=f"Code validation FAILED — auto-reverted.\nError: {error_msg[:500]}"
                )

            if self.blob:
                self.blob.store(
                    event_type="redeploy",
                    content=f"Redeploy: {message}\nValidation passed. Sending SIGHUP.",
                    metadata={"message": message},
                )

            # 4. Signal uvicorn to gracefully restart
            # SIGHUP tells uvicorn parent to restart workers
            log.info("redeploy_restart", message=message)
            os.kill(os.getpid(), signal.SIGHUP)

            return ToolResult(
                success=True, output=f"Redeploy initiated.\n{commit_result.output}\nCode validated. Restarting..."
            )
        except Exception as e:
            return ToolResult(success=False, output="", error=str(e))

    # ── Helper ─────────────────────────────────────────────────────────────

    async def _run_git(self, args: list[str], cwd: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        output = stdout.decode("utf-8", errors="replace")
        if stderr:
            output += "\n" + stderr.decode("utf-8", errors="replace")
        return output.strip()

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "action": {
                    "type": "string",
                    "description": "One of: read, write, list, diff, commit, push, log, revert, redeploy",
                    "enum": ["read", "write", "list", "diff", "commit", "push", "log", "revert", "redeploy"],
                },
                "path": {"type": "string", "description": "File or directory path (e.g. /app/jarvis/core/loop.py)"},
                "content": {"type": "string", "description": "File content (for 'write' action)"},
                "message": {"type": "string", "description": "Commit/redeploy message"},
                "remote": {
                    "type": "string",
                    "description": "Git remote URL (for 'push' action, e.g. https://github.com/user/jarvis.git)",
                },
            },
            "required": ["action"],
        }

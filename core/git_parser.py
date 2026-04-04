"""
Git log parser.

Changes in v1.3:
  - FIX P1: 5-field stdin lines with '|' in commit subject no longer misparsed.
    Detection now validates whether field[4] looks like an ISO date before
    assuming 6-field mode. Falls back to 5-field with message reconstructed
    from all remaining parts.
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Commit, FileChange

_SEP = "|||GITSTORY|||"
_FORMAT = f"%H{_SEP}%an{_SEP}%ae{_SEP}%at{_SEP}%aI{_SEP}%s"

# Matches ISO 8601 date with timezone: 2024-01-05T14:30:00+05:30 or ...Z
_ISO_DATE_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:?\d{2}|Z)$"
)


def _parse_tz_offset(iso_date: str) -> Optional[float]:
    """Extract timezone offset in hours from ISO 8601 date string."""
    iso_date = iso_date.strip()
    if iso_date.endswith("Z"):
        return 0.0
    m = re.search(r"([+-])(\d{2}):?(\d{2})$", iso_date)
    if not m:
        return None
    sign = 1 if m.group(1) == "+" else -1
    return sign * (int(m.group(2)) + int(m.group(3)) / 60.0)


def _looks_like_iso_date(s: str) -> bool:
    """Return True if the string matches ISO 8601 datetime with timezone.

    This is the key discriminator between 5-field and 6-field stdin format.
    A commit message fragment like 'fix parser | guard' will NOT match this.
    """
    return bool(_ISO_DATE_PATTERN.match(s.strip()))


def _commit_sort_key(commit: Commit) -> tuple[datetime, str, int]:
    """Provide a total ordering for commits, even on equal timestamps."""
    return (commit.timestamp, commit.hash or "", commit.source_index)


class GitParser:
    """Parses a local git repository into a list of Commit objects."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / ".git").exists():
            if not (self.repo_path / "HEAD").exists():
                raise ValueError(f"Not a git repository: {self.repo_path}")

    @property
    def repo_name(self) -> str:
        return self.repo_path.name

    def parse(self, max_commits: Optional[int] = None) -> list[Commit]:
        """Parse git log → list of Commit objects, oldest-first."""
        raw_log = self._run_git_log(max_commits)
        raw_numstat = self._run_git_numstat(max_commits)
        raw_namestatus = self._run_git_name_status(max_commits)

        commits = self._parse_log_lines(raw_log)
        file_map = self._parse_numstat_lines(raw_numstat)
        status_map = self._parse_name_status_lines(raw_namestatus)

        for commit in commits:
            commit.file_changes = file_map.get(commit.hash, [])
            statuses = status_map.get(commit.hash, {})
            for fc in commit.file_changes:
                if fc.path in statuses:
                    fc.status = statuses[fc.path]

        return sorted(commits, key=_commit_sort_key)

    @classmethod
    def from_log_text(cls, log_text: str) -> list[Commit]:
        """Parse pre-formatted git log text from stdin.

        Supported formats:
            HASH|author|email|unix_timestamp|message               (5-field)
            HASH|author|email|unix_timestamp|iso_date|message      (6-field)

        FIX v1.3: When the subject itself contains '|', the parser now
        validates whether field[4] looks like an ISO 8601 date before
        assuming 6-field mode. If it doesn't match, ALL remaining fields
        after the timestamp are joined back into the message.

        Example that previously broke:
            abc123|alice|a@t.com|1704067200|fix parser | guard
        Now correctly parsed as message = "fix parser | guard"
        """
        commits: list[Commit] = []
        current: Optional[Commit] = None

        for source_index, raw_line in enumerate(log_text.strip().splitlines()):
            line = raw_line.strip()
            if not line:
                continue

            # Try numstat line first
            numstat_match = re.match(r"^(\d+|-)\t(\d+|-)\t(.+)$", line)
            if numstat_match and current is not None:
                adds = numstat_match.group(1)
                dels = numstat_match.group(2)
                path = numstat_match.group(3)
                current.file_changes.append(
                    FileChange(
                        path=path,
                        additions=int(adds) if adds != "-" else 0,
                        deletions=int(dels) if dels != "-" else 0,
                        status="U",
                    )
                )
                continue

            # Split into all pipe-delimited parts (no limit)
            raw_parts = line.split("|")

            # Need at least 5 parts: hash, author, email, timestamp, message
            if len(raw_parts) < 5:
                continue

            # Validate timestamp
            try:
                ts = int(raw_parts[3])
            except ValueError:
                continue

            # FIX P1: Determine if field[4] is an ISO date or part of the message.
            # Only treat as 6-field if field[4] strictly matches ISO 8601 with tz.
            if len(raw_parts) >= 6 and _looks_like_iso_date(raw_parts[4]):
                # 6-field: hash|author|email|ts|iso_date|message...
                tz_offset = _parse_tz_offset(raw_parts[4])
                message = "|".join(raw_parts[5:])  # rejoin if message had pipes
            else:
                # 5-field: hash|author|email|ts|message...
                tz_offset = None
                message = "|".join(raw_parts[4:])  # rejoin ALL remaining parts

            current = Commit(
                hash=raw_parts[0] or "",
                author=raw_parts[1],
                email=raw_parts[2],
                timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                message=message,
                author_tz_offset_hours=tz_offset,
                _source_index=source_index,
            )
            commits.append(current)

        return sorted(commits, key=_commit_sort_key)

    # ── Private ──────────────────────────────────────────────────

    def _run(self, args: list[str]) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo_path)] + args,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git command failed: {' '.join(args)}\n"
                f"{result.stderr.strip()}"
            )
        return result.stdout

    def _run_git_log(self, max_commits: Optional[int]) -> str:
        cmd = ["log", f"--pretty=format:{_FORMAT}"]
        if max_commits:
            cmd.append(f"-n{max_commits}")
        return self._run(cmd)

    def _run_git_numstat(self, max_commits: Optional[int]) -> str:
        cmd = ["log", "--pretty=format:%H", "--numstat"]
        if max_commits:
            cmd.append(f"-n{max_commits}")
        return self._run(cmd)

    def _run_git_name_status(self, max_commits: Optional[int]) -> str:
        cmd = ["log", "--pretty=format:%H", "--name-status"]
        if max_commits:
            cmd.append(f"-n{max_commits}")
        return self._run(cmd)

    def _parse_log_lines(self, raw: str) -> list[Commit]:
        commits: list[Commit] = []
        for source_index, line in enumerate(raw.strip().splitlines()):
            line = line.strip()
            if not line:
                continue
            parts = line.split(_SEP, 5)
            if len(parts) < 6:
                continue
            try:
                ts = int(parts[3])
            except ValueError:
                continue
            commits.append(
                Commit(
                    hash=parts[0] or "",
                    author=parts[1],
                    email=parts[2],
                    timestamp=datetime.fromtimestamp(ts, tz=timezone.utc),
                    message=parts[5],
                    author_tz_offset_hours=_parse_tz_offset(parts[4]),
                    _source_index=source_index,
                )
            )
        return commits

    def _parse_numstat_lines(self, raw: str) -> dict[str, list[FileChange]]:
        result: dict[str, list[FileChange]] = {}
        current_hash: Optional[str] = None
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^[0-9a-f]{40}$", line):
                current_hash = line
                result.setdefault(current_hash, [])
                continue
            if current_hash is None:
                continue
            parts = line.split("\t", 2)
            if len(parts) == 3:
                adds, dels, path = parts
                result[current_hash].append(
                    FileChange(
                        path=path,
                        additions=int(adds) if adds != "-" else 0,
                        deletions=int(dels) if dels != "-" else 0,
                        status="M",
                    )
                )
        return result

    def _parse_name_status_lines(
        self, raw: str
    ) -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}
        current_hash: Optional[str] = None
        for line in raw.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if re.match(r"^[0-9a-f]{40}$", line):
                current_hash = line
                result.setdefault(current_hash, {})
                continue
            if current_hash is None:
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                raw_status = parts[0].strip()
                status = raw_status[0] if raw_status else "M"
                path = parts[-1]
                result[current_hash][path] = status
        return result

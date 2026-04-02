"""
Tests for git_parser — timezone, stdin parsing, pipe-in-subject, edge cases.
"""

from __future__ import annotations

from core.git_parser import _parse_tz_offset, _looks_like_iso_date, GitParser


# ── Timezone Offset Parsing ──────────────────────────────────────

class TestTzOffsetParsing:
    def test_positive_offset(self):
        assert _parse_tz_offset("2024-01-05T14:30:00+05:30") == 5.5

    def test_negative_offset(self):
        assert _parse_tz_offset("2024-01-05T09:00:00-08:00") == -8.0

    def test_utc_z(self):
        assert _parse_tz_offset("2024-01-05T09:00:00Z") == 0.0

    def test_zero_offset(self):
        assert _parse_tz_offset("2024-01-05T09:00:00+00:00") == 0.0

    def test_no_offset_returns_none(self):
        assert _parse_tz_offset("2024-01-05T09:00:00") is None

    def test_compact_offset_no_colon(self):
        assert _parse_tz_offset("2024-01-05T09:00:00+0530") == 5.5

    def test_negative_half_hour(self):
        assert _parse_tz_offset("2024-01-05T09:00:00-09:30") == -9.5

    def test_empty_string(self):
        assert _parse_tz_offset("") is None

    def test_garbage_string(self):
        assert _parse_tz_offset("not a date at all") is None


# ── ISO Date Validation ──────────────────────────────────────────

class TestLooksLikeIsoDate:
    def test_valid_positive_tz(self):
        assert _looks_like_iso_date("2024-01-05T14:30:00+05:30") is True

    def test_valid_z(self):
        assert _looks_like_iso_date("2024-01-05T09:00:00Z") is True

    def test_valid_negative_tz(self):
        assert _looks_like_iso_date("2024-03-01T23:00:00-08:00") is True

    def test_plain_text_is_not_iso(self):
        assert _looks_like_iso_date("fix parser") is False

    def test_partial_date_is_not_iso(self):
        assert _looks_like_iso_date("2024-01-05") is False

    def test_word_is_not_iso(self):
        assert _looks_like_iso_date("guard") is False

    def test_unix_timestamp_is_not_iso(self):
        assert _looks_like_iso_date("1704067200") is False

    def test_date_without_tz_is_not_iso(self):
        assert _looks_like_iso_date("2024-01-05T09:00:00") is False

    def test_whitespace_is_not_iso(self):
        assert _looks_like_iso_date("  ") is False


# ── Basic Stdin Parsing ──────────────────────────────────────────

class TestFromLogTextBasic:
    def test_five_field_format(self):
        log = "abc123|alice|alice@test.com|1704067200|initial commit\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].author == "alice"
        assert commits[0].message == "initial commit"
        assert commits[0].author_tz_offset_hours is None

    def test_six_field_format_with_tz(self):
        log = "abc123|alice|a@t.com|1704067200|2024-01-01T12:00:00+05:30|initial commit\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].author_tz_offset_hours == 5.5
        assert commits[0].message == "initial commit"

    def test_numstat_lines_parsed(self):
        log = (
            "abc123|alice|alice@test.com|1704067200|init\n"
            "10\t0\tREADME.md\n"
            "50\t0\tsrc/app.py\n"
        )
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert len(commits[0].file_changes) == 2
        assert commits[0].file_changes[0].additions == 10
        assert commits[0].file_changes[1].path == "src/app.py"

    def test_oldest_first_ordering(self):
        log = (
            "bbb|bob|b@t.com|1704153600|second\n"
            "aaa|alice|a@t.com|1704067200|first\n"
        )
        commits = GitParser.from_log_text(log)
        assert commits[0].message == "first"
        assert commits[1].message == "second"

    def test_stdin_files_get_status_U(self):
        log = "abc123|alice|a@t.com|1704067200|init\n10\t0\tREADME.md\n"
        commits = GitParser.from_log_text(log)
        assert commits[0].file_changes[0].status == "U"


# ── Empty / Edge Cases ───────────────────────────────────────────

class TestFromLogTextEdgeCases:
    def test_empty_string(self):
        assert GitParser.from_log_text("") == []

    def test_whitespace_only(self):
        assert GitParser.from_log_text("   \n  \n") == []

    def test_invalid_timestamp(self):
        log = "abc123|alice|a@t.com|notanumber|some commit\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 0

    def test_too_few_fields(self):
        log = "abc123|alice|a@t.com\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 0

    def test_binary_numstat_dash(self):
        """Binary files show '-' for additions/deletions."""
        log = (
            "abc123|alice|a@t.com|1704067200|add image\n"
            "-\t-\timage.png\n"
        )
        commits = GitParser.from_log_text(log)
        assert commits[0].file_changes[0].additions == 0
        assert commits[0].file_changes[0].deletions == 0

    def test_multiple_commits_with_numstat(self):
        log = (
            "aaa|alice|a@t.com|1704067200|first commit\n"
            "10\t5\tfile1.py\n"
            "bbb|bob|b@t.com|1704153600|second commit\n"
            "20\t3\tfile2.py\n"
            "5\t0\tfile3.py\n"
        )
        commits = GitParser.from_log_text(log)
        assert len(commits) == 2
        assert len(commits[0].file_changes) == 1
        assert len(commits[1].file_changes) == 2


# ── Pipe-in-Subject Regression ───────────────────────────────────

class TestFromLogTextPipeInSubject:
    def test_five_field_single_pipe_in_message(self):
        """5-field commit with '|' in subject must NOT be misparsed."""
        log = "abc123|alice|alice@test.com|1704067200|fix parser | guard\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].message == "fix parser | guard"
        assert commits[0].author_tz_offset_hours is None

    def test_five_field_multiple_pipes_in_message(self):
        log = "abc123|bob|b@t.com|1704067200|feat: add A | B | C support\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].message == "feat: add A | B | C support"

    def test_six_field_with_pipe_in_message(self):
        log = "abc123|alice|a@t.com|1704067200|2024-01-01T12:00:00+00:00|fix foo | bar\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].message == "fix foo | bar"
        assert commits[0].author_tz_offset_hours == 0.0

    def test_message_starting_with_year_but_not_iso(self):
        log = "abc123|alice|a@t.com|1704067200|2024 update | final\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].message == "2024 update | final"
        assert commits[0].author_tz_offset_hours is None

    def test_pipe_only_message(self):
        log = "abc123|alice|a@t.com|1704067200||\n"
        commits = GitParser.from_log_text(log)
        assert len(commits) == 1
        assert commits[0].message == "|"

    def test_pipe_with_numstat_after(self):
        log = (
            "abc123|alice|a@t.com|1704067200|fix | thing\n"
            "3\t1\tapp.py\n"
        )
        commits = GitParser.from_log_text(log)
        assert commits[0].message == "fix | thing"
        assert len(commits[0].file_changes) == 1
from mythrix.core.logging_config import truncate


def test_truncate_passes_short_text_through_unchanged() -> None:
    assert truncate("hello", limit=10) == "hello"


def test_truncate_passes_text_at_exact_limit_through_unchanged() -> None:
    text = "x" * 10
    assert truncate(text, limit=10) == text


def test_truncate_marks_text_over_limit() -> None:
    text = "x" * 11
    result = truncate(text, limit=10)
    assert result == f"{'x' * 10}…[truncated, 11 chars total]"

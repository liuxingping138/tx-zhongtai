from platform_common.similarity import (
    HIGH,
    LEVEL_HIGH,
    LEVEL_MEDIUM,
    LEVEL_NONE,
    MEDIUM,
    similarity,
    similarity_level,
)


def test_similarity_identical() -> None:
    assert similarity("智慧园区", "智慧园区") == 1.0


def test_similarity_empty() -> None:
    assert similarity("", "智慧园区") == 0.0
    assert similarity("智慧园区", "") == 0.0
    assert similarity("   ", "   ") == 0.0


def test_similarity_substring_containment() -> None:
    score_short = similarity("智慧", "智慧园区信息化平台")
    assert score_short < 0.5

    score_long = similarity("智慧园区", "某某智慧园区项目")
    assert score_long >= 0.5


def test_similarity_with_noise_characters() -> None:
    assert similarity("智慧-园区（一期）", "智慧园区一期") == 1.0


def test_similarity_level() -> None:
    assert similarity_level(HIGH) == LEVEL_HIGH
    assert similarity_level(HIGH + 0.1) == LEVEL_HIGH
    assert similarity_level(MEDIUM) == LEVEL_MEDIUM
    assert similarity_level(MEDIUM - 0.1) == LEVEL_NONE

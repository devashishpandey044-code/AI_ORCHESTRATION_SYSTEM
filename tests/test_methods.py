import pytest
import yaml
from pydantic import ValidationError

from app.methods.loader import (
    LIBRARY_DIR,
    LibraryError,
    get_library,
    get_method,
    load_library,
    methods_for,
)
from app.methods.report import main as report_main
from app.methods.schema import Method
from app.methods.taxonomy import DESCRIPTIONS, SENSITIVE, RoadblockType


def valid_raw(**overrides):
    base = {
        "slug": "example_method",
        "title": "Example method",
        "summary": "A short example summary that is long enough.",
        "targets": ["distraction"],
        "target_behavior": "Do the example behaviour.",
        "difficulty": "easy",
        "duration_minutes": 10,
        "schedule_kind": "daily_block",
        "steps": ["Step one text", "Step two text", "Step three text"],
        "ideal_context": "Anywhere quiet enough.",
        "contraindications": ["Not for every situation."],
        "measurement": "Count the number of completed sessions.",
        "evidence_level": "practitioner",
        "evidence_note": "Practitioner technique without strong research.",
        "sources": [],
        "escalation_note": None,
    }
    return base | overrides


# ---- schema ----------------------------------------------------------------

def test_valid_method_passes():
    method = Method.model_validate(valid_raw())
    assert method.slug == "example_method"
    assert method.reviewed_on is None


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Method.model_validate(valid_raw(secret_field="x"))


def test_missing_required_field_rejected():
    raw = valid_raw()
    del raw["measurement"]
    with pytest.raises(ValidationError):
        Method.model_validate(raw)


def test_bad_slug_rejected():
    for slug in ("Bad Slug", "x", "UPPER_case", "has-dash", "_leading"):
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(slug=slug))


def test_duplicate_targets_rejected():
    with pytest.raises(ValidationError):
        Method.model_validate(valid_raw(targets=["distraction", "distraction"]))


def test_unknown_roadblock_rejected():
    with pytest.raises(ValidationError):
        Method.model_validate(valid_raw(targets=["boredom"]))


def test_strong_or_moderate_evidence_needs_sources():
    for level in ("strong", "moderate"):
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(evidence_level=level, sources=[]))
        source = "Author, A. (2020). A real looking citation. Journal, 1(1), 1-10."
        Method.model_validate(valid_raw(evidence_level=level, sources=[source]))
    Method.model_validate(valid_raw(evidence_level="limited", sources=[]))


def test_sensitive_targets_need_escalation_note():
    for target in ("low_energy", "burnout_risk"):
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(targets=[target], escalation_note=None))
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(targets=[target], escalation_note="   "))
        Method.model_validate(
            valid_raw(targets=[target], escalation_note="Please talk to a doctor if this lasts.")
        )


def test_step_count_limits():
    too_few = ["Step one text", "Step two text"]
    too_many = [f"Step number {i}" for i in range(8)]
    for steps in (too_few, too_many):
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(steps=steps))
    Method.model_validate(valid_raw(steps=[f"Step number {i}" for i in range(3)]))
    Method.model_validate(valid_raw(steps=[f"Step number {i}" for i in range(7)]))


def test_blank_step_rejected():
    with pytest.raises(ValidationError):
        Method.model_validate(valid_raw(steps=["Step one text", "   ", "Step three text"]))


def test_blank_contraindication_rejected():
    with pytest.raises(ValidationError):
        Method.model_validate(valid_raw(contraindications=[" "]))


def test_duration_bounds():
    for minutes in (0, 241):
        with pytest.raises(ValidationError):
            Method.model_validate(valid_raw(duration_minutes=minutes))
    for minutes in (1, 240):
        Method.model_validate(valid_raw(duration_minutes=minutes))


# ---- the real library ------------------------------------------------------

def test_library_loads_and_has_enough_methods():
    assert len(get_library()) >= 8


def test_slugs_unique_and_match_filenames():
    slugs = [m.slug for m in get_library()]
    assert len(slugs) == len(set(slugs))
    assert sorted(slugs) == sorted(p.stem for p in LIBRARY_DIR.glob("*.yaml"))


def test_every_roadblock_has_at_least_one_method():
    for roadblock in RoadblockType:
        assert methods_for(roadblock), roadblock.value


def test_every_roadblock_has_a_description():
    assert set(DESCRIPTIONS) == set(RoadblockType)


def test_sensitive_methods_have_escalation_notes():
    sensitive = [m for m in get_library() if SENSITIVE & set(m.targets)]
    assert sensitive
    for method in sensitive:
        assert method.escalation_note, method.slug


def test_strong_and_moderate_methods_cite_sources():
    for method in get_library():
        if method.evidence_level in ("strong", "moderate"):
            assert method.sources, method.slug


def test_get_method_and_methods_for():
    assert get_method("implementation_intentions") is not None
    assert get_method("does_not_exist") is None
    distraction = methods_for(RoadblockType.DISTRACTION)
    assert all(RoadblockType.DISTRACTION in m.targets for m in distraction)
    assert "phone_friction" in [m.slug for m in distraction]


# ---- loader errors ---------------------------------------------------------

def test_invalid_yaml_reports_the_filename(tmp_path):
    (tmp_path / "broken.yaml").write_text("slug: [unclosed\n", encoding="utf-8")
    with pytest.raises(LibraryError, match="broken.yaml"):
        load_library(tmp_path)


def test_filename_must_match_slug(tmp_path):
    raw = valid_raw(slug="other_name")
    (tmp_path / "wrong_name.yaml").write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(LibraryError, match="wrong_name.yaml"):
        load_library(tmp_path)


def test_empty_file_is_rejected(tmp_path):
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")
    with pytest.raises(LibraryError, match="empty.yaml"):
        load_library(tmp_path)


# ---- report ----------------------------------------------------------------

def test_report_prints_coverage(capsys):
    assert report_main() == 0
    out = capsys.readouterr().out
    assert "Roadblock coverage" in out
    assert "distraction" in out

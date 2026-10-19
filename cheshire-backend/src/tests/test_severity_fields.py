from tools.helpers.output_schema import VulnerabilityDetails

def _base(**kw):
    return dict(title="t", description="d", page_no=1, web_references=[], recommendations=[], **kw)

def test_defaults_are_none_for_legacy_findings():
    v = VulnerabilityDetails(**_base())
    assert v.severity is None and v.confidence is None

def test_roundtrip_json_keeps_severity_and_confidence():
    v = VulnerabilityDetails(**_base(severity="major", confidence=0.8))
    r = VulnerabilityDetails.model_validate_json(v.model_dump_json())
    assert (r.severity, r.confidence) == ("major", 0.8)
from types import SimpleNamespace
from knowledge_base.progress import ProgressTracker

def test_percent_is_monotonic_and_counts_findings():
    p = ProgressTracker()
    p.set_stage("auditing", "x")
    last = 0.0
    for i in range(3):
        p.begin_chunk(i, 3, f"S{i}", (i + 1, i + 1), 0)
        p.end_chunk((i + 1, i + 1), [SimpleNamespace(severity="major", title="T", finding="f")])
        cur = p.snapshot()["percent"]
        assert cur >= last
        last = cur
    snap = p.snapshot()
    assert snap["counts"]["major"] == 3
    assert snap["scanned_pages"] == [1, 2, 3]
    assert snap["events"][-1]["kind"] == "finding"
    assert p.snapshot(since=snap["last_seq"])["events"] == []
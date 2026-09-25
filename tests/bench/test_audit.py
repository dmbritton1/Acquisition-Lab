import json

from acqlab.bench.audit import audit, main
from acqlab.generator.batch import AnswerKey


def test_the_audit_counts_pages_on_evidence_and_the_real_facts_never_read(data, tmp_path, capsys):
    key = AnswerKey.model_validate_json((data / "truth" / "dev-000.json").read_text())
    real = {f.trap for f in key.truth.facts if f.amount > 0}
    ev = next(e for e in key.evidence if e.trap in real)
    held = set().union(*(e.docs for e in key.evidence if e.trap in real))
    other = next(d for d in ("it_policy", "hr_policy", "travel", "marketing") if d not in held)
    runs = tmp_path / "runs" / "s4"
    runs.mkdir(parents=True)
    (tmp_path / "truth").mkdir()
    (tmp_path / "truth" / "dev-000.json").write_text(key.model_dump_json())
    (runs / "dev-000.json").write_text(json.dumps({"deal": "dev-000", "case_type": key.truth.case_type,
                                                   "correct": True, "regret": 0.0}))
    rows = [{"tool": "open_document", "args": {"doc_id": ev.docs[0]}, "cost": 5.0, "refused": False},
            {"tool": "open_document", "args": {"doc_id": other}, "cost": 2.0, "refused": False},
            {"tool": "open_document", "args": {"doc_id": "audited"}, "cost": 14.0, "refused": True},
            {"tool": "route", "args": {"doc": other}, "cost": 0.0, "refused": False}]
    (runs / "dev-000.trace.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    [row] = audit(tmp_path, "s4")
    assert row["pages"] == 7.0 and row["evidence_pages"] == 5.0 and not row["audited"]  # a refused open is no read
    docs = {e.trap: set(e.docs) for e in key.evidence}
    assert row["missed"] == sorted(t for t in real if ev.docs[0] not in docs[t]) and ev.trap not in row["missed"]
    assert main(["--data", str(tmp_path), "--system", "s4"]) == 0 and "1 runs" in capsys.readouterr().out

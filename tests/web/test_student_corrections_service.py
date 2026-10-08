from datetime import timedelta

import pytest

from sms.web.errors import ApiError
from sms.web.services import student_corrections as sc
from sms.web.services.student_corrections import _utcnow
from sms.web.services.submissions import get_submission
from sms.worker.jobs import JobStore
from tests.web.seed_v2 import seed_v2
from tests.web.test_student_api import _setup


def _released(auth, app, days=7):
    t, c, ca, _ = _setup(auth)
    tan = c["students"][0]
    sid, _ = seed_v2(app, label="#1 Tan", assignment_id=t["id"], run_id="r-tan", queue={})
    app.state.db.execute("UPDATE submissions SET class_assignment_id = :a, student_id = :s, handed_in_at = CURRENT_TIMESTAMP, source = 'student' WHERE id = :id",
                         {"a": ca["id"], "s": tan["id"], "id": sid})
    auth.post(f"/api/classes/{c['id']}/assignments/{ca['id']}/release")
    app.state.db.execute("UPDATE class_assignments SET reflect_days = :d WHERE id = :id", {"d": days, "id": ca["id"]})
    row = app.state.db.query("SELECT * FROM class_assignments WHERE id = :id", {"id": ca["id"]})[0]
    return row, sid


def test_window_and_correctable_parts(auth, app):
    ca, sid = _released(auth, app)
    db = app.state.db
    assert sc.window_open(db, ca)
    assert sc.window_end(db, ca) > _utcnow() + timedelta(days=6)
    db.execute("UPDATE class_assignments SET reflect_days = 0 WHERE id = :id", {"id": ca["id"]})
    ca["reflect_days"] = 0
    assert sc.window_end(db, ca) is None and not sc.window_open(db, ca)
    detail = get_submission(db, JobStore(db), sid)
    parts = sc.correctable_parts(detail)
    assert set(parts) == {"1b", "2"} and parts["1b"]["max"] == 1   # 1a has full marks in the seed


def test_submit_enforces_rules_and_enqueues_a_remark(auth, app):
    ca, sid = _released(auth, app)
    db = app.state.db
    jobs = JobStore(db)
    detail = get_submission(db, jobs, sid)
    status_before = db.query("SELECT status FROM submissions WHERE id = :id", {"id": sid})[0]["status"]
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1a", reason="sign", text="x", photo=None)
    assert e.value.code == "not_correctable"
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="  ", photo=None)
    assert e.value.code == "empty_correction"
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="x^2 = 9", photo=None)
    assert row["status"] == "submitted" and row["q_id"] == "1b"
    assert db.query("SELECT kind, payload_json FROM jobs WHERE kind = 'remark'")[0]["payload_json"] == '{"correction_id": %d}' % row["id"]
    assert db.query("SELECT status FROM submissions WHERE id = :id", {"id": sid})[0]["status"] == status_before == "done"
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="again", photo=None)
    assert e.value.code == "already_corrected"
    db.execute("UPDATE class_assignments SET reflect_days = 0 WHERE id = :id", {"id": ca["id"]}); ca["reflect_days"] = 0
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="2", reason="sign", text="z", photo=None)
    assert e.value.code == "window_closed"


def test_decide_and_release_transitions(auth, app):
    ca, sid = _released(auth, app)
    db = app.state.db
    jobs = JobStore(db)
    detail = get_submission(db, jobs, sid)
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="9", photo=None)
    db.execute("UPDATE student_corrections SET status = 'remarked', remark_total = 1, remark_max = 1, remark_note = 'B1 now earned' WHERE id = :id", {"id": row["id"]})
    assert sc.decide(db, row["id"], "accept")["status"] == "accepted"
    assert sc.decide(db, row["id"], "override", total=0.5)["teacher_total"] == 0.5
    with pytest.raises(ApiError):
        sc.decide(db, row["id"], "override", total=5)         # above max
    assert sc.release_corrections(db, ca["id"]) == 1
    got = db.query("SELECT status, released_at FROM student_corrections WHERE id = :id", {"id": row["id"]})[0]
    assert got["status"] == "released" and got["released_at"] is not None
    with pytest.raises(ApiError):
        sc.decide(db, row["id"], "reject", reason="too late")   # released is final
    view = sc.student_reflection(db, ca, get_submission(db, jobs, sid))
    assert view["parts"]["1b"] == {"can_correct": False, "status": "released", "new_mark": 0.5}
    assert view["parts"]["2"]["can_correct"] is True and view["days_left"] >= 6


def test_photo_correction_stores_a_correction_page(auth, app):
    import io

    from PIL import Image

    ca, sid = _released(auth, app)
    db = app.state.db
    jobs = JobStore(db)
    detail = get_submission(db, jobs, sid)
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="2", reason="other", text="", photo=("w.png", buf.getvalue()))
    page = db.query("SELECT kind FROM pages WHERE id = :id", {"id": row["page_id"]})[0]
    assert page["kind"] == "correction"
    with pytest.raises(ApiError) as e:
        sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="other", text="", photo=("w.png", b"not an image"))
    assert e.value.code == "bad_photo"


def test_duplicate_part_is_a_409_and_leaves_no_page_behind(auth, app):
    import io

    from PIL import Image

    ca, sid = _released(auth, app)
    db = app.state.db
    jobs = JobStore(db)
    detail = get_submission(db, jobs, sid)
    db.execute("INSERT INTO student_corrections (submission_id, q_id, status) VALUES (:s, '2', 'submitted')", {"s": sid})
    pages_before = db.query("SELECT COUNT(*) AS c FROM pages")[0]["c"]
    jobs_before = db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"]
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(buf, format="PNG")
    # Skip the fast-path SELECT to emulate the losing side of a race: the unique index must still give a 409.
    real_query = db.query
    db.query = lambda sql, params=None: [] if "FROM student_corrections WHERE submission_id" in sql else real_query(sql, params)
    try:
        with pytest.raises(ApiError) as e:
            sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="2", reason="other", text="z", photo=("w.png", buf.getvalue()))
    finally:
        db.query = real_query
    assert e.value.status == 409 and e.value.code == "already_corrected"
    assert db.query("SELECT COUNT(*) AS c FROM pages")[0]["c"] == pages_before
    assert db.query("SELECT COUNT(*) AS c FROM jobs")[0]["c"] == jobs_before


def test_students_see_only_coarse_status_words(auth, app):
    ca, sid = _released(auth, app)
    db = app.state.db
    jobs = JobStore(db)
    detail = get_submission(db, jobs, sid)
    row = sc.submit_correction(db, app.state.storage, jobs, ca=ca, submission_detail=detail, q_id="1b", reason="sign", text="9", photo=None)
    assert sc.student_reflection(db, ca, detail)["parts"]["1b"]["status"] == "sent"
    db.execute("UPDATE student_corrections SET status = 'accepted', remark_total = 1, remark_max = 1, remark_note = 'secret note', "
               "teacher_reason = 'secret reason' WHERE id = :id", {"id": row["id"]})
    view = sc.student_reflection(db, ca, detail)
    assert view["parts"]["1b"] == {"can_correct": False, "status": "waiting", "new_mark": None}
    blob = repr(view)
    assert all(k not in blob for k in ("remark_note", "teacher_reason", "justification", "secret"))

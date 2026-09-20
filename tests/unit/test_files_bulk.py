from sms.files.bulk import match_entries

STUDENTS = [{"id": 1, "reg_no": 7, "name": "Amirah"}, {"id": 2, "reg_no": 12, "name": "Ben"}]


def test_prefix_forms():
    plan = match_entries(["07_amirah.py", "12 - ben/prog.py", "12 - ben/data.xlsx", "7.jpg", "notes.txt", "99_nobody.py"], STUDENTS)
    assert plan.matched == {1: ["07_amirah.py", "7.jpg"], 2: ["12 - ben/prog.py", "12 - ben/data.xlsx"]}
    assert plan.unmatched == ["notes.txt", "99_nobody.py"] and plan.ambiguous == []


def test_ambiguous_when_two_students_share_a_number():
    plan = match_entries(["7_x.py"], STUDENTS + [{"id": 3, "reg_no": 7, "name": "Dup"}])
    assert plan.ambiguous == ["7_x.py"] and plan.matched == {}

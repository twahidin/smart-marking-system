from sms.web.services.classlist import parse_classlist


def test_header_variants_and_bom():
    rows, errors = parse_classlist("﻿Reg No,Name\r\n1,Tan Wei Ling\r\n2,Muhammad Danish\r\n".encode())
    assert errors == []
    assert [(r["reg_no"], r["name"], r["issues"]) for r in rows] == [(1, "Tan Wei Ling", []), (2, "Muhammad Danish", [])]


def test_missing_columns_is_a_file_error():
    rows, errors = parse_classlist(b"student,index\nA,1\n")
    assert rows == [] and errors == ["The first row must have the columns name and reg_no"]


def test_row_issues_are_flagged_inline():
    data = b"name,reg_no\nTan,1\n,2\nLim,x\nOng,1\n\n"
    rows, errors = parse_classlist(data)
    assert errors == []
    assert [r["issues"] for r in rows] == [["duplicate_reg_no"], ["missing_name"], ["bad_reg_no"], ["duplicate_reg_no"]]
    assert rows[2]["raw_reg_no"] == "x" and rows[2]["reg_no"] is None


def test_empty_file():
    assert parse_classlist(b"") == ([], ["The file is empty"])

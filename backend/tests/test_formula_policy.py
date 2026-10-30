import pytest

from app.services.calculation_service import CalcError, crit_expr
from app.services.formula_policy import FormulaError, validate_formula

SHEETS = {"Data", "Bob's data", "الموظفين"}


@pytest.mark.parametrize("f", [
    "=COUNTIF('Data'!$B$2:$B$3001,\"Active\")",
    "=IF(COUNT('Data'!$C$2:$C$10)=0,\"\",AVERAGE('Data'!$C$2:$C$10))",
    "=SUMPRODUCT(('Data'!$A$2:$A$9<>\"\")/COUNTIF('Data'!$A$2:$A$9,'Data'!$A$2:$A$9&\"\"))",
    "=IF($A5=\"\",\"\",COUNTIFS('Bob''s data'!$B$2:$B$9,$A5,'Data'!$C$2:$C$9,\">=50\"))",
    "=SUM('الموظفين'!$C$2:$C$9)",
    "=_xlfn.MINIFS('Data'!$C$2:$C$9,'Data'!$B$2:$B$9,$A1)",
])
def test_allowed(f):
    validate_formula(f, SHEETS)


@pytest.mark.parametrize("f", [
    "=HYPERLINK(\"http://evil.example\",\"x\")",
    "=INDIRECT(\"A1\")", "=WEBSERVICE(\"http://x\")", "=CALL(\"a\")", "=EXEC(\"calc\")",
    "=SUM([1]Sheet1!A1:A5)", "='C:\\files\\[book.xlsx]Sheet1'!A1", "=SUM('Other'!A1:A2)",
    "=cmd|' /C calc'!A0", "=SUM(A1:A2", "=SUM(A1:A2))", "=SUM(A1)+@x", "=SUM(A1);SUM(A2)", "=SUM({1,2})",
    "=SUM(XFE1)", "=SUM(A0)", "=SUM(A1048577)", "=NAME1+1", "SUM(A1)", "=", "=SUM(A1)" + "+1" * 1500,
    "='Data'!", "='Data'!SUM(A1)", "=_xlfn.WEBSERVICE(\"http://x\")", "=_xlfn.SUM(A1)", "=_xlfn.IF(1,2,3)",
])
def test_rejected(f):
    with pytest.raises(FormulaError):
        validate_formula(f, SHEETS)


def test_string_literals_are_data_not_syntax():
    validate_formula('=COUNTIF(\'Data\'!$A$2:$A$9,"=HYPERLINK(""http://x"")")', SHEETS)
    assert crit_expr('x"); =HYPERLINK("http://evil","c")').count('"') % 2 == 0
    assert crit_expr("a*b?") == '"a~*b~?"' and crit_expr(">=50") == '">=50"' and crit_expr("50") == "50"
    assert crit_expr("<>") == '"<>"'
    for bad in ["", "   ", "x" * 300, ">="]:
        with pytest.raises(CalcError):
            crit_expr(bad)

from bernstein.core.govern.audit_sweep import CheckOutcome, CheckVerdict

outcome = CheckOutcome("CMP-001", "area", CheckVerdict.MEASURED, False, "sum1", "")
print(outcome.verdict is CheckVerdict.MEASURED)
print(outcome.verdict == CheckVerdict.MEASURED)
print(type(outcome.verdict))

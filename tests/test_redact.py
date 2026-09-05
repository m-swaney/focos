from focos.doctor.redact import redact

NAMES = [("Ann Example", "OWNER"), ("Corner Shop LLC", "ENTITY_SHOP"), ("12 Harbor Court", "ADDRESS")]


def test_redact_rules():
    text = ("ANTHROPIC_API_KEY=sk-ant-api03-abcdefghijklmnopqrstuvwxyz\n"  # private-scan: allow (fake test value)
            "url https://alice:hunter2@bridge.simplefin.org/simplefin/accounts\n"  # private-scan: allow (fake test value)
            "acct 123456789012 owner ann example at 12 Harbor Court, mail ann@example.com\n"  # private-scan: allow (fake test value)
            "paid Corner Shop LLC $1,234.56 and 98765 units\n"
            "token ghp_abcdefghijklmnopqrstuvwxyz0123 and key AIzaSyA1234567890abcdefghijklmn")  # private-scan: allow (fake test value)
    out = redact(text, extra_names=NAMES)
    assert "sk-ant" not in out and "ANTHROPIC_API_KEY=[SET]" in out
    assert "alice:hunter2" not in out and "[CREDS]@bridge" in out
    assert "123456789012" not in out and "########9012" in out  # private-scan: allow (fake test value)
    assert "ann example" not in out.lower() and "[OWNER]" in out
    assert "Harbor Court" not in out and "[ADDRESS]" in out
    assert "ann@example.com" not in out and "[EMAIL]" in out
    assert "Corner Shop LLC" not in out and "[ENTITY_SHOP]" in out
    assert "ghp_" not in out and "AIza" not in out
    assert "$1,234.56" in out  # amounts stay unless asked
    assert "$1,234.56" not in redact(text, scrub_amounts=True, extra_names=NAMES)
    assert "[AMOUNT]" in redact(text, scrub_amounts=True, extra_names=NAMES)

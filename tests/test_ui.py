from pathlib import Path

from app.api.ui import UI_DIR


def test_the_landing_page_is_served_with_a_strict_content_policy(client):
    res = client.get("/")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/html")
    assert "AI Life Orchestrator" in res.text
    policy = res.headers["content-security-policy"]
    assert "default-src 'none'" in policy
    assert "script-src 'self'" in policy
    assert "unsafe-inline" not in policy
    assert res.headers["x-content-type-options"] == "nosniff"


def test_the_script_and_stylesheet_are_served(client):
    script = client.get("/ui/app.js")
    assert script.status_code == 200
    assert "javascript" in script.headers["content-type"]
    style = client.get("/ui/style.css")
    assert style.status_code == 200
    assert style.headers["content-type"].startswith("text/css")


def test_the_landing_page_does_not_hide_the_api(client):
    assert client.get("/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/ui/missing.js").status_code == 404


def test_the_page_has_no_inline_script_or_handlers():
    html = (UI_DIR / "index.html").read_text()
    assert html.count("<script") == html.count("<script src=")
    for handler in ("onclick=", "onload=", "onerror=", "javascript:"):
        assert handler not in html


def test_the_script_never_builds_markup_from_text():
    code = Path(UI_DIR / "app.js").read_text()
    risky_calls = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(")
    for risky in risky_calls + ("new Function",):
        assert risky not in code, risky


def test_the_page_only_talks_to_its_own_server():
    code = Path(UI_DIR / "app.js").read_text()
    assert "http://" not in code and "https://" not in code

from findingz.run_progress import latest_log


def test_tail_is_bounded_and_ansi_removed(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "generation.log").write_text("old\n" * 10000 + "\x1b[31mIntegrating\x1b[0m\n")
    name, text, age = latest_log(tmp_path)
    assert name == "generation.log"
    assert text.endswith("Integrating") and "\x1b" not in text
    assert len(text.splitlines()) <= 14 and age >= 0


def test_no_log_yet(tmp_path):
    assert latest_log(tmp_path) is None


def test_progress_ui(tmp_path):
    from streamlit.testing.v1 import AppTest

    (tmp_path / "logs").mkdir()
    (tmp_path / "logs/generation.log").write_text("Compiling subprocesses")
    app = AppTest.from_string(
        "from findingz.run_progress import render_progress_details\n"
        f"render_progress_details({{'run_dir': {str(tmp_path)!r}, 'summary': '100 events · seed 225'}})"
    ).run()
    assert not app.exception
    assert app.code[0].value == "Compiling subprocesses"
    assert any("Elapsed" in c.value for c in app.caption)

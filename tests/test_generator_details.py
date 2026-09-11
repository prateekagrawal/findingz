from PIL import Image

from findingz.generator_details import diagram_preview, retain_generator_details


def test_preview_has_white_paper_and_preserves_original(tmp_path):
    path = tmp_path / "diagram.png"
    source = Image.new("RGBA", (3, 1), (0, 0, 0, 0))
    source.putpixel((1, 0), (0, 0, 0, 255))
    source.putpixel((2, 0), (0, 0, 0, 128))
    source.save(path)
    original = path.read_bytes()
    preview = diagram_preview(path)
    assert preview.mode == "RGB"
    assert preview.getpixel((0, 0)) == (255, 255, 255)
    assert preview.getpixel((1, 0)) == (0, 0, 0)
    assert preview.getpixel((2, 0)) == (127, 127, 127)
    assert path.read_bytes() == original


def test_details_retained_without_renderer(tmp_path, monkeypatch):
    monkeypatch.setattr("findingz.generator_details.shutil.which", lambda _: None)
    diagram = tmp_path / "process/SubProcesses/P1_test/matrix.ps"
    diagram.parent.mkdir(parents=True)
    diagram.write_text("native diagrams")
    card = tmp_path / "process/Cards/run_card.dat"
    card.parent.mkdir(parents=True)
    card.write_text("actual settings")
    retain_generator_details(tmp_path)
    assert (tmp_path / "diagrams/P1_test/matrix.ps").read_text() == "native diagrams"
    assert (tmp_path / "cards/generated/run_card.dat").read_text() == "actual settings"
    # Reusing a cleaned checkpoint must preserve already-retained documentation.
    diagram.unlink()
    retain_generator_details(tmp_path)
    assert (tmp_path / "diagrams/P1_test/matrix.ps").exists()


def test_renderer_failure_does_not_fail_generation(tmp_path, monkeypatch):
    monkeypatch.setattr("findingz.generator_details.shutil.which", lambda _: "/missing/gs")
    diagram = tmp_path / "process/SubProcesses/P1_test/matrix.ps"
    diagram.parent.mkdir(parents=True)
    diagram.write_text("native diagrams")
    retain_generator_details(tmp_path)
    assert (tmp_path / "diagrams/P1_test/matrix.render.log").is_file()


def test_run_files_grouping(tmp_path):
    from streamlit.testing.v1 import AppTest

    (tmp_path / "analysis.csv").write_text("mll\n91\n")
    (tmp_path / "events.lhe").write_text("test LHE")
    app = AppTest.from_string(
        "from pathlib import Path\nfrom findingz.generator_details import render_run_files\n"
        f"root=Path({str(tmp_path)!r})\n"
        "render_run_files(root, {'stages': {'matrix_element': 'events.lhe'}}, root/'analysis.csv')"
    ).run()
    assert not app.exception
    assert [e.label for e in app.expander] == [
        "Run files and details", "Saved run configuration (JSON)"]
    assert [t.label for t in app.tabs] == ["Event files", "Settings and cards", "Execution logs"]
    assert not app.selectbox
    labels = [button.label for button in app.get("download_button")]
    assert "Analysis table (CSV)" in labels
    assert "Generator events (LHE)" in labels
    assert "Detector events (ROOT)" not in labels


def test_settings_use_consistent_file_rows(tmp_path):
    from streamlit.testing.v1 import AppTest

    cards = tmp_path / "cards" / "generated"
    cards.mkdir(parents=True)
    (cards / "run_card.dat").write_text("100 = nevents")
    app = AppTest.from_string(
        "from pathlib import Path\nfrom findingz.generator_details import render_settings_files\n"
        f"render_settings_files(Path({str(tmp_path)!r}), {{'config': {{'events': 100}}}})"
    ).run()
    assert not app.exception and not app.selectbox and not app.get("json")
    assert [e.label for e in app.expander] == [
        "Saved run configuration (JSON)", "generated/run_card.dat"]
    assert len(app.get("download_button")) == 2


def test_logs_use_expandable_file_rows(tmp_path):
    from streamlit.testing.v1 import AppTest

    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "generation.log").write_text("Run completed")
    (logs / "shower.log").write_text("Shower completed")
    app = AppTest.from_string(
        "from pathlib import Path\nfrom findingz.generator_details import render_text_files\n"
        f"render_text_files(Path({str(tmp_path)!r}), 'logs', 'Execution logs')"
    ).run()
    assert not app.exception and not app.selectbox
    assert [e.label for e in app.expander] == ["generation.log", "shower.log"]
    assert len(app.get("download_button")) == 2
    assert [c.value for c in app.code] == ["Run completed", "Shower completed"]


def test_only_used_cards_are_offered(tmp_path):
    from findingz.generator_details import used_card_paths

    cards = tmp_path / "cards"
    (cards / "generated").mkdir(parents=True)
    for name in ["madgraph_process.mg5", "madevent_commands.txt", "delphes_card.dat",
                 "generated/run_card.dat", "generated/param_card.dat",
                 "generated/pythia8_card.dat", "generated/delphes_card.dat",
                 "generated/run_card_default.dat", "generated/pgs_card_ATLAS.dat",
                 "generated/delphes_card_CMS.dat", "generated/proc_card_mg5.dat"]:
        (cards / name).write_text("test")
    names = lambda mode: [str(p.relative_to(cards)) for p in
                          used_card_paths(tmp_path, {"config": {"run_mode": mode}})]
    assert names("madgraph") == ["madgraph_process.mg5", "madevent_commands.txt",
                                 "generated/run_card.dat", "generated/param_card.dat"]
    assert names("full") == names("madgraph") + ["generated/pythia8_card.dat", "delphes_card.dat"]


def test_diagram_crop_preserves_content_and_source(tmp_path):
    from PIL import ImageDraw

    path = tmp_path / "page.png"
    page = Image.new("RGB", (600, 1000), "white")
    draw = ImageDraw.Draw(page)
    draw.rectangle((510, 50, 540, 60), fill="black")  # Page number
    draw.rectangle((100, 200, 500, 450), fill="black")  # Diagram and labels
    draw.rectangle((200, 950, 400, 960), fill="black")  # Footer
    page.save(path)
    original = path.read_bytes()
    result = diagram_preview(path)
    assert result.size == (425, 275)
    assert result.getpixel((12, 12)) == (0, 0, 0)
    assert path.read_bytes() == original

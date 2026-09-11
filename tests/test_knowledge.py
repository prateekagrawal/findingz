from findingz.knowledge import search_course_notes


def test_retrieval_finds_relativity_note() -> None:
    results = search_course_notes("Why is dilepton invariant mass Lorentz invariant?")
    assert results
    assert any(item["source"] == "relativity.md" for item in results)

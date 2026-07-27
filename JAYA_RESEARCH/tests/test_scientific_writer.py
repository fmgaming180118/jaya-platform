from research.experiment_designer import ExperimentDesigner
from research.experiment_runner import ExperimentRunner
from research.experimental_memory import ExperimentalMemory
from research.hypothesis_generator import HypothesisGenerator
from research.scientific_writer import ScientificWriter


def _simulation_report(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Neural Architecture Search")
    plan = ExperimentDesigner().design_experiment(hypothesis)
    result = ExperimentRunner(
        memory=ExperimentalMemory(tmp_path / "memory.json")
    ).run_experiment(plan)
    return ScientificWriter().generate_paper(hypothesis, plan, result)


def test_simulation_report_is_honestly_labelled_and_not_publishable(tmp_path):
    paper = _simulation_report(tmp_path)

    assert paper["paper_status"] == "SIMULATION_REPORT"
    assert paper["publication_ready"] is False
    assert paper["evidence_kind"] == "SIMULATION"
    assert paper["references"] == []
    assert "simulation" in paper["title"].casefold()
    assert "cannot establish an empirical" in paper["sections"]["discussion"]


def test_writer_never_invents_references(tmp_path):
    paper = _simulation_report(tmp_path)

    assert paper["references"] == []
    assert "arXiv" not in str(paper)
    assert "doi.org" not in str(paper)


def test_reproduced_empirical_draft_uses_only_supplied_reference(tmp_path):
    hypothesis = HypothesisGenerator().generate_hypothesis("Measured Throughput")
    hypothesis["references"] = [
        {
            "title": "Approved benchmark dataset",
            "uri": "https://example.invalid/approved-dataset",
            "sha256": "a" * 64,
        }
    ]
    hypothesis.update(
        {
            "observations": {
                "baseline": [1.0, 1.1, 0.9],
                "treatment": [2.0, 2.1, 1.9],
            },
            "provenance": {
                "source_hashes": ["a" * 64],
                "license_id": "CC-BY-4.0",
                "runner_id": "runner-a",
                "environment_id": "environment-a",
            },
        }
    )
    first_plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="EMPIRICAL",
    )
    first_result = ExperimentRunner(
        memory=ExperimentalMemory(tmp_path / "memory-first.json")
    ).run_experiment(first_plan)

    hypothesis["observations"] = {
        "baseline": [1.2, 1.3, 1.1],
        "treatment": [2.2, 2.3, 2.1],
    }
    hypothesis["provenance"] = {
        "source_hashes": ["b" * 64],
        "license_id": "CC-BY-4.0",
        "runner_id": "runner-b",
        "environment_id": "environment-b",
    }
    hypothesis["prior_empirical_runs"] = [first_result]
    plan = ExperimentDesigner().design_experiment(
        hypothesis,
        execution_mode="EMPIRICAL",
    )
    result = ExperimentRunner(
        memory=ExperimentalMemory(tmp_path / "memory-second.json")
    ).run_experiment(plan)
    paper = ScientificWriter().generate_paper(
        hypothesis,
        plan,
        result,
        {"recommendation": "ACCEPT_HYPOTHESIS"},
    )

    assert paper["paper_status"] == "EMPIRICAL_DRAFT"
    assert paper["publication_ready"] is True
    assert len(paper["references"]) == 1
    assert "Approved benchmark dataset" in paper["references"][0]


def test_export_markdown_and_latex(tmp_path):
    paper = _simulation_report(tmp_path)
    writer = ScientificWriter()
    markdown_path = tmp_path / "paper.md"
    latex_path = tmp_path / "paper.tex"

    markdown = writer.export_markdown(paper, output_path=markdown_path)
    latex = writer.export_latex(paper, output_path=latex_path)

    assert markdown.startswith("# Simulation Report:")
    assert "## Abstract" in markdown
    assert "\\documentclass" in latex
    assert "\\section{Materials and Methods}" in latex
    assert markdown_path.is_file()
    assert latex_path.is_file()

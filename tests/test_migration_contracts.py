from pathlib import Path
import pytest
from harbor.agents.factory import AgentFactory
from boxbox.terminus_boxbox import TerminusBoxBox, harness
from boxbox.terminus_boxbox.seed import fingerprint, materialize
from perfrace.installed.terminus_boxbox import TerminusBoxBoxAgent
from perfrace.settings import configured_model, expand_environment
from perfrace.run.config import load_run
from perfrace.collect.discovery.projects import repository_names


def test_seed_is_independent_and_identical(tmp_path):
    source = Path(harness.__file__).parent
    a = materialize(source, tmp_path / "a")
    b = materialize(source, tmp_path / "b")
    assert fingerprint(a) == fingerprint(b)
    f = a / "prompt-templates" / "task.txt"
    f.write_text("edited")
    assert fingerprint(a) != fingerprint(b)
    assert (b / f.relative_to(a)).read_text() != "edited"


def test_seed_file_overlay_is_local(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "instructions.txt").write_text("original")
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    (overlay / "instructions.txt").write_text("replacement")
    tree = materialize(source, tmp_path / "seed", overlay=overlay)
    assert (tree / "instructions.txt").read_text() == "replacement"
    assert (source / "instructions.txt").read_text() == "original"


def test_model_is_explicit(monkeypatch):
    monkeypatch.delenv("PERFRACE_SETTINGS")
    with pytest.raises(ValueError, match="Specify a model"):
        configured_model("filter")
    assert configured_model("filter", "chosen") == "chosen"


@pytest.mark.parametrize("entry", ["name", "cli", "import"])
def test_terminus_boxbox_name_and_direct_budget(tmp_path, entry):
    config = tmp_path / "run.yaml"
    if entry == "cli":
        config.write_text("task_budget_sec: 14400\n")
        run = load_run(config, agent="terminus-boxbox", model="test-model")
    else:
        selector = (
            "name: terminus-boxbox" if entry == "name"
            else f"import_path: {TerminusBoxBoxAgent.import_path()}"
        )
        config.write_text(
            f"task_budget_sec: 14400\njob:\n  agents:\n    - {selector}\n"
            "      model_name: test-model\n"
        )
        run = load_run(config)
    agent_config = run.job.agents[0]
    agent = AgentFactory.create_agent_from_config(agent_config, logs_dir=tmp_path / "logs")
    assert isinstance(agent, TerminusBoxBoxAgent)
    assert agent.to_agent_info().name == TerminusBoxBox.name() == "terminus-boxbox"
    assert agent.model_name == "test-model"
    assert agent_config.task_budget_sec == 14400


def test_fixed_patch_is_kept(tmp_path):
    result = load_run(None, patch=tmp_path)
    assert result.submission_path == tmp_path


def test_repository_list_normalization():
    assert repository_names("https://github.com/a/b.git\na/b\nc/d\n") == ["a/b", "c/d"]
    with pytest.raises(ValueError):
        repository_names("https://example.com/a/b")


def test_credentials_resolve_without_config_rewrite(monkeypatch):
    monkeypatch.setenv("TEST_SECRET", "value")
    assert expand_environment({"api_key": "${env:TEST_SECRET}"}) == {"api_key": "value"}

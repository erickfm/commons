import pytest

from commons.scenario import Scenario


def make(**kw):
    return Scenario(name="t", task="shared task", agents=3, runtimes=["claude_code", "codex"], models={"claude_code": "a", "codex": "b"}, **kw)


def test_defaults_cycle_runtimes():
    s = make()
    assert [s.runtime(i) for i in (1, 2, 3)] == ["claude_code", "codex", "claude_code"]
    assert s.task_for(2) == "shared task" and s.role(2) is None


def test_per_agent_overrides_one_agent():
    s = make(per_agent={"agent_2": {"role": "plant", "system_prompt": "secret", "task": "own task", "runtime": "basic", "model": "c"}})
    assert (s.runtime(2), s.model(2), s.system_prompt_for(2), s.task_for(2), s.role(2)) == ("basic", "c", "secret", "own task", "plant")
    assert (s.runtime(1), s.model(1), s.task_for(1)) == ("claude_code", "a", "shared task")


def test_agent_name_placeholder():
    s = make(system_prompt="You are {agent}.")
    assert s.system_prompt_for(2) == "You are agent_2." and s.task_for(2) == "shared task"


def test_per_agent_rejects_unknown_agent_and_settings():
    with pytest.raises(ValueError):
        make(per_agent={"agent_9": {"role": "x"}})
    with pytest.raises(ValueError):
        make(per_agent={"agent_1": {"colour": "red"}})
    with pytest.raises(ValueError):
        make(per_agent={"agent_1": {"runtime": "gemini"}})


def test_example_scenarios_load():
    for name in ("hello", "basic", "web_open", "web_allowlist", "plant", "channels"):
        Scenario.load(f"scenarios/{name}.yaml")


def test_workspace_resolves_relative_to_scenario_file():
    s = Scenario.load("scenarios/plant.yaml")
    files = s.workspace_files()
    assert set(files) == {"dates.py", "test_dates.py"}
    assert s.role(4) == "plant" and s.runtime(4) == "basic"


def test_private_scripted_posts_need_messages_channel():
    with pytest.raises(ValueError):
        make(scripted_posts=[{"at": 0, "as": "agent_9", "to": "agent_1", "message": "hi"}])
    s = make(channels=["board", "messages"], scripted_posts=[{"at": 0, "as": "agent_9", "to": "agent_1", "message": "hi"}])
    assert s.channels == ["board", "messages"]
    with pytest.raises(ValueError):
        make(channels=["board", "telepathy"])

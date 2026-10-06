import pytest

from commons.compose import compose_config


def test_off_has_no_egress_and_internal_network():
    c = compose_config(3)
    assert set(c["services"]) == {"agent_1", "agent_2", "agent_3", "board"}
    assert c["networks"] == {"swarm": {"internal": True}}
    assert "environment" not in c["services"]["agent_1"]


def test_agents_are_hardened():
    agent = compose_config(2, mem="2g", cpus=1)["services"]["agent_2"]
    assert "hidepid=invisible" in agent["command"]
    assert agent["mem_limit"] == "2g" and agent["cpus"] == 1
    assert "volumes" not in agent


@pytest.mark.parametrize("level", ["open", "allowlist"])
def test_internet_goes_through_egress(level):
    c = compose_config(2, internet=level, allow=["pypi.org"])
    assert c["services"]["agent_1"]["networks"] == ["swarm"]
    assert c["services"]["agent_1"]["environment"]["HTTPS_PROXY"] == "http://egress:3128"
    assert c["services"]["egress"]["networks"] == ["swarm", "outside"]
    assert c["services"]["egress"]["environment"]["EGRESS_MODE"] == level


def test_allowlist_requires_hosts():
    with pytest.raises(ValueError):
        compose_config(2, internet="allowlist")


def test_plants_reach_board():
    c = compose_config(1, plants=[{"at": 5, "as": "agent_9", "message": "hi"}])
    assert '"agent_9"' in c["services"]["board"]["environment"]["BOARD_PLANTS"]

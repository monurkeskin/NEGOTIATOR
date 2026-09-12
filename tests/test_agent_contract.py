import random

import pytest

from negotiator.examples import builtin_domain, example_profiles
from negotiator.strategies import create_agent, strategy_names
from negotiator.testing import AgentContractError, assert_agent_contract


@pytest.mark.parametrize("name", strategy_names())
def test_builtin_agents_meet_the_reusable_contract(name):
    _, own = example_profiles(builtin_domain("fruits"))
    receipt = assert_agent_contract(lambda pref, seed: create_agent(name, pref, seed=seed), own)
    assert receipt["actions_checked"] >= 1 and receipt["deadline_checked"]


def test_contract_detects_global_rng_and_restores_test_state():
    _, own = example_profiles(builtin_domain("fruits"))
    before = random.getstate()

    def bad_factory(pref, seed):
        random.random()
        return create_agent("hybrid", pref)

    with pytest.raises(AgentContractError, match="global RNG"):
        assert_agent_contract(bad_factory, own)
    assert random.getstate() == before

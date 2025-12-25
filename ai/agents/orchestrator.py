from ai.agents.analyst import analyst_ai
from ai.agents.critic import critic_ai
from ai.agents.synthesizer import synthesizer_ai


def generate_ai_summary(data: dict) -> dict:
    analyst = analyst_ai(data)
    critic = critic_ai(data, analyst)
    synth = synthesizer_ai(data, analyst, critic)

    return {
        "analyst": analyst,
        "critic": critic,
        "synthesizer": synth,
    }


import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def critic_ai(data: dict, analyst_text: str) -> str:
    prompt = f"""
You are a critical reviewer.

You are given:
- The same raw data
- The Analyst’s interpretation

Your task:
- Point out weaknesses
- Suggest alternative explanations
- Highlight uncertainty
- Identify missing data
- Avoid repeating the Analyst

For each analyst claim:
- Say whether evidence is sufficient
- Propose at least one alternative explanation


Data:
{data}

Analyst explanation:
{analyst_text}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You challenge analytics interpretations carefully."},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content

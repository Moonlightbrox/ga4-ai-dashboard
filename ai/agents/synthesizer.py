import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def synthesizer_ai(data: dict, analyst_text: str, critic_text: str) -> str:
    prompt = f"""
You are the Synthesizer AI.

You represent the outcome of an internal analytics discussion between:
- an Analyst (pattern discovery)
- a Critic (risk & uncertainty)

Your task:
- Summarize the discussion for a business owner
- Organize insights into clear sections:
  • Summary
  • Risks
  • Opportunities
  • Actionable Insights
  • Confidence & Caveats
- 

Rules:
- Do NOT introduce new facts
- Use simple, clear language
- Prioritize business relevance
- If evidence is weak, say so
- Avoid technical jargon

Output should be structured, scannable, and decision-oriented.


Data:
{data}

Analyst explanation:
{analyst_text}

Critic review:
{critic_text}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You produce clean, accurate executive summaries."},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content

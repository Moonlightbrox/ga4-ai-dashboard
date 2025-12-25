import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def analyst_ai(data: dict) -> str:
    prompt = f"""
You are a data analyst.

You are given raw analytical data from Google Analytics.

Your task:
- Identify patterns
- Identify notable changes
- Explain what is happening in the data
- Do NOT give business advice
- Stick to what the data supports

When you make a claim:
- State what changed
- Over what time frame
- How confident you are
- What data supports it


{data}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "You explain analytics clearly and factually."},
            {"role": "user", "content": prompt},
        ],
    )

    return response.choices[0].message.content

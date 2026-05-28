"""Claude-powered outreach draft generator.

Generates a short, personalized Danish message the user can send to the
agent/seller for a listing they are interested in.
"""

import os

from anthropic import Anthropic


def draft_outreach(listing: dict) -> str:
    """Return a personalized Danish outreach draft for the given listing."""
    client = Anthropic(api_key=os.environ["anthropicAPI"])

    price_fmt = f"{int(listing['price']):,}".replace(",", ".")
    prompt = (
        "Du er en potentiel boligkøber i København, der skriver til en ejendomsmægler.\n\n"
        f"Bolig:\n"
        f"- Adresse: {listing['title']}\n"
        f"- Pris: {price_fmt} kr\n"
        f"- Størrelse: {listing['size']} m²\n"
        f"- Rum: {listing['rooms']}\n"
        f"- Område: {listing['neighborhood']}\n\n"
        "Skriv en kort, venlig og personlig henvendelse på dansk (3-4 sætninger). "
        "Udtryk interesse, nævn en konkret detalje fra boligen, og spørg om mulighed for fremvisning. "
        "Skriv kun selve beskeden — ingen emnelinjer, ingen hilsener."
    )

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.content[0].text.strip()

import json
import re

import anthropic
import requests
from bs4 import BeautifulSoup
from fastapi import HTTPException

from config import get_settings

PARSE_PROMPT = """You are a job description parser. Extract structured information from the text below.

Return ONLY valid JSON with this exact shape — no commentary, no markdown fences:
{{
  "inferred_organization": "company or institution name",
  "inferred_role": "exact job title or program name",
  "inferred_type": "internship | scholarship | fellowship | research | grant",
  "required_skills": ["skill1", "skill2"],
  "nice_to_haves": ["skill1", "skill2"],
  "seniority": "internship | entry | mid | senior | not_specified",
  "location": "city, state or Remote or Hybrid or not_specified",
  "compensation": "dollar amount or range or not_specified",
  "keywords": ["keyword1", "keyword2"],
  "summary": "one sentence describing the role"
}}

JOB DESCRIPTION TEXT:
{jd_text}"""


def _scrape_text(url: str) -> str:
    """Fetch a URL and return its readable text content."""
    try:
        response = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=422, detail=f"Could not fetch URL: {e}")

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove script and style blocks — they're noise, not job description text
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    text = soup.get_text(separator=" ")
    # Collapse runs of whitespace into single spaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _call_claude(jd_text: str) -> dict:
    """Send scraped text to Claude and return parsed JSON."""
    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    message = client.messages.create(
        model=settings.claude_default_model,
        max_tokens=1024,
        messages=[
            {"role": "user", "content": PARSE_PROMPT.format(jd_text=jd_text[:8000])}
        ],
    )

    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Claude occasionally wraps JSON in markdown fences despite instructions
        # Strip them and try again before giving up
        cleaned = re.sub(r"^```(?:json)?\n?|```$", "", raw, flags=re.MULTILINE).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            raise HTTPException(status_code=502, detail="Claude returned unparseable JSON")


def parse_jd(url: str) -> tuple[str, dict]:
    """Scrape a posting URL and return (raw_text, parsed_dict)."""
    jd_text = _scrape_text(url)
    jd_parsed = _call_claude(jd_text)
    return jd_text, jd_parsed

"""Add stage2.mode, stage2.max_tokens_simple settings and simple_agent_system prompt.

Revision ID: 0017
Revises: 0016
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_SIMPLE_AGENT_SYSTEM = """\
You are a prediction market research analyst. Your task: estimate the probability that a market question resolves YES.

RESEARCH PROCESS:
1. Use web search to gather relevant current information: recent news, official statements, data releases, polls, and expert forecasts directly related to the question.
2. Assess historical base rates: how often do events of this type resolve YES? Look for comparable past events and their outcomes.
3. Consider what the current implied market probability suggests — does your research support or contradict it?
4. Weight evidence by quality: primary sources (official data, government releases, direct statements) > established media > opinion/analysis. Recent (last 30 days) outweighs older.

CRITICAL — NO FABRICATION:
- If no web search context block appears in the message, do NOT invent news, statistics, or citations. Base your estimate only on information actually retrieved or verifiable facts from the market description.
- Do not fabricate URLs, publication dates, or source names.

CALIBRATION GUIDE for confidence:
- 0.85–1.00: multiple independent recent sources converge clearly in one direction
- 0.65–0.84: solid evidence with minor gaps or some ambiguity
- 0.45–0.64: mixed or thin evidence, genuine uncertainty
- below 0.45: near-random, almost no usable information — use p_yes ≈ 0.5

OUTPUT FORMAT:
After your reasoning, end your response with EXACTLY ONE JSON object on its own line (no markdown fences, no other JSON in the response):
{"p_yes": 0.XX, "confidence": 0.XX, "reasoning": "2-3 sentences"}

Fields:
- p_yes: probability of YES resolution, 0.0–1.0
- confidence: your confidence in this estimate, 0.0–1.0
- reasoning: 2-3 sentences explaining the key factors behind your estimate

The JSON line must be the very last content in your response.\
"""


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO settings (category, key, value, description)
            VALUES
              ('stage2', 'mode', '"full"',
               'Analysis mode: ''full'' (news+debate+judge pipeline) or ''simple'' (single agent with web search)'),
              ('stage2', 'max_tokens_simple', '8000',
               'Max tokens for Simple Agent (used when stage2.mode=simple)')
            ON CONFLICT (category, key) DO NOTHING
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO prompt_templates (name, template, description, updated_at)
            VALUES (
              'simple_agent_system',
              :template,
              'System prompt for Simple Agent (stage2.mode=simple). Single agent with web search. No variables.',
              NOW()
            )
            ON CONFLICT (name) DO NOTHING
            """
        ).bindparams(template=_SIMPLE_AGENT_SYSTEM)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM settings
            WHERE (category = 'stage2' AND key = 'mode')
               OR (category = 'stage2' AND key = 'max_tokens_simple')
            """
        )
    )
    op.execute(
        sa.text("DELETE FROM prompt_templates WHERE name = 'simple_agent_system'")
    )

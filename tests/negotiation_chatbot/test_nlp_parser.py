"""
tests/negotiation_chatbot/test_nlp_parser.py
Unit tests for NLP intent classification, Indian currency extraction, and Hinglish understanding.
"""
from decimal import Decimal
import pytest
from app.domain.negotiation_chatbot.nlp_parser import NLPNegotiationParser
from app.domain.negotiation_chatbot.schemas import ClaimantIntent


@pytest.fixture
def parser() -> NLPNegotiationParser:
    return NLPNegotiationParser()


@pytest.mark.parametrize(
    "text,expected_amount",
    [
        ("I need ₹15,000 for repair", Decimal("15000.00")),
        ("Rs. 12500 is what my mechanic asked", Decimal("12500.00")),
        ("INR 14,000.50 minimum", Decimal("14000.50")),
        ("Can you do 18000 rupees?", Decimal("18000.00")),
        ("Bumper quote is 16500 bucks", Decimal("16500.00")),
    ],
)
def test_explicit_inr_amounts(parser, text, expected_amount):
    """Tests currency extraction across prefixes (₹, Rs, INR) and punctuation."""
    intent, counteroffer, _ = parser.parse(text, current_offer_inr=Decimal("10000.00"))
    assert intent == ClaimantIntent.COUNTER
    assert counteroffer == expected_amount


@pytest.mark.parametrize(
    "text,delta,expected_counter",
    [
        ("+2000", Decimal("2000.00"), Decimal("10000.00")),
        ("add 1500 to this offer", Decimal("1500.00"), Decimal("9500.00")),
        ("give extra 1000 please", Decimal("1000.00"), Decimal("9000.00")),
        ("increase by rs 2,500", Decimal("2500.00"), Decimal("10500.00")),
    ],
)
def test_relative_deltas(parser, text, delta, expected_counter):
    """Tests relative increment extraction (+2000, add 1500, extra 1000)."""
    current_offer = Decimal("8000.00")
    intent, counteroffer, _ = parser.parse(text, current_offer_inr=current_offer)
    assert intent == ClaimantIntent.COUNTER
    assert counteroffer == expected_counter


@pytest.mark.parametrize(
    "text",
    [
        "paisa badhao bohot kam hai",
        "yeh offer bohot kam hai, nahi hoga",
        "kharcha bohot zyada hai garage mein",
        "aur do thoda sa",
        "thoda aur badha do",
    ],
)
def test_hinglish_keywords(parser, text):
    """Tests Hinglish negotiation keywords (badhao, kam hai, zyada, aur do)."""
    intent, counteroffer, rationale_score = parser.parse(text, current_offer_inr=Decimal("7500.00"))
    assert intent == ClaimantIntent.QUALITATIVE_PLEA
    assert counteroffer is None
    assert rationale_score == 0.35


@pytest.mark.parametrize(
    "text",
    [
        "I accept this cash offer",
        "Agreed, proceed with payment",
        "Deal, please send the money",
        "theek hai mujhe manzoor hai",
        "ok done send money",
        "Yes confirm cash in lieu",
    ],
)
def test_accept_keywords(parser, text):
    """Tests accept keywords across English and Hinglish."""
    current_offer = Decimal("8500.00")
    intent, counteroffer, rationale_score = parser.parse(text, current_offer_inr=current_offer)
    assert intent == ClaimantIntent.ACCEPT
    assert counteroffer == current_offer
    assert rationale_score == 1.0


def test_accept_negation_guard(parser):
    """Tests that negative statements like 'don't accept' are not misclassified as accept."""
    text = "I don't accept this low amount, increase it"
    intent, _, _ = parser.parse(text, current_offer_inr=Decimal("8000.00"))
    assert intent != ClaimantIntent.ACCEPT


@pytest.mark.parametrize(
    "text",
    [
        "I want cashless garage repair instead",
        "send a physical surveyor to my workshop",
        "take the car to authorized service center",
        "no thanks, prefer authorized network garage",
        "claimless garage repair please",
    ],
)
def test_reject_garage_keywords(parser, text):
    """Tests reject and cashless garage routing keywords."""
    intent, counteroffer, rationale_score = parser.parse(text, current_offer_inr=Decimal("8000.00"))
    assert intent == ClaimantIntent.REJECT_GARAGE
    assert counteroffer is None
    assert rationale_score == 0.0


def test_rationale_scoring(parser):
    """
    Tests rationale score graduation:
    - 0.50 for technical justification (OEM part, paint, labor, dent, quote)
    - 0.35 for Hinglish plea / expensive
    - 0.25 for baseline negotiation
    """
    current_offer = Decimal("7500.00")

    # Technical
    _, _, score_tech = parser.parse("OEM bumper replacement and metallic paint labor is expensive", current_offer)
    assert score_tech == 0.50

    # Hinglish
    _, _, score_hing = parser.parse("bohot kam hai paisa badhao", current_offer)
    assert score_hing == 0.35

    # Baseline
    _, _, score_base = parser.parse("please give me a higher offer", current_offer)
    assert score_base == 0.25


def test_explicit_counteroffer_overrides_text(parser):
    """Verifies that an explicitly provided counteroffer takes precedence over parsed text."""
    text = "I was thinking 12000"
    intent, counteroffer, _ = parser.parse(
        text,
        current_offer_inr=Decimal("8000.00"),
        explicit_counteroffer=Decimal("15000.00"),
    )
    assert intent == ClaimantIntent.COUNTER
    assert counteroffer == Decimal("15000.00")
"""
app/domain/negotiation_chatbot/nlp_parser.py
Natural Language Processing intent classifier, currency extractor, and Hinglish matcher.
"""
from decimal import Decimal, InvalidOperation
import re
from typing import Optional, Tuple
from app.domain.negotiation_chatbot.schemas import ClaimantIntent

CURRENCY_AMOUNT_REGEX = re.compile(
    r"(?:rs\.?|inr|₹)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)\s*(?:rs\.?|inr|₹|rupees|bucks)?",
    re.IGNORECASE,
)

RELATIVE_DELTA_REGEX = re.compile(
    r"(?:add|increase|extra|more|\+)\s*(?:by\s*)?(?:rs\.?|inr|₹)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)",
    re.IGNORECASE,
)

ACCEPT_KEYWORDS = {
    "accept", "accepted", "agree", "agreed", "deal", "done", "ok", "okay",
    "theek hai", "manzoor", "yes", "confirm", "proceed with cash", "i accept",
}

REJECT_GARAGE_KEYWORDS = {
    "cashless garage", "network garage", "garage repair", "cashless", "workshop", "surveyor", "human", "reject", "rejected",
    "authorized center", "service center", "claimless", "network", "no thanks",
}

TECHNICAL_JUSTIFICATION_KEYWORDS = {
    "paint", "denting", "oem", "bumper", "door", "bonnet", "fender", "labor",
    "labour", "authorized", "authorised", "service center", "genuine", "parts",
    "quote", "estimate", "gst", "replacement", "scratch", "dent", "metallic",
}

HINGLISH_PLEA_KEYWORDS = {
    "badhao", "badha do", "kam hai", "bohot kam", "zyada", "aur do", "mehenga",
    "kharcha", "paisa badhao", "thoda aur", "nahi hoga",
}


class NLPNegotiationParser:
    """
    Parses claimant natural language messages into structured negotiation intents and numbers.
    """

    def parse(
        self,
        raw_message: str,
        current_offer_inr: Decimal,
        explicit_counteroffer: Optional[Decimal] = None,
    ) -> Tuple[ClaimantIntent, Optional[Decimal], float]:
        """
        Parses user input text.
        Returns: (ClaimantIntent, parsed_counteroffer_inr, rationale_score)
        """
        text = raw_message.strip().lower()

        # 1. Check for Accept Intent
        if any(kw in text for kw in ACCEPT_KEYWORDS) and not any(kw in text for kw in {"don't accept", "not accept", "cannot accept"}):
            return ClaimantIntent.ACCEPT, current_offer_inr, 1.0

        # 2. Check for Garage / Surveyor Rejection Intent
        if any(kw in text for kw in REJECT_GARAGE_KEYWORDS):
            return ClaimantIntent.REJECT_GARAGE, None, 0.0

        # 3. Check for Explicit or Extracted Counteroffer
        counteroffer = explicit_counteroffer
        if counteroffer is None:
            # Check relative increment first: "+2000" or "add 1500"
            delta_match = RELATIVE_DELTA_REGEX.search(text)
            if delta_match:
                cleaned_num = delta_match.group(1).replace(",", "")
                try:
                    delta = Decimal(cleaned_num)
                    counteroffer = (current_offer_inr + delta).quantize(Decimal("0.01"))
                except InvalidOperation:
                    pass

        if counteroffer is None:
            # Check absolute currency match
            matches = list(CURRENCY_AMOUNT_REGEX.finditer(text))
            for m in matches:
                matched_str = m.group(1)
                if not matched_str:
                    continue
                cleaned_num = matched_str.replace(",", "")
                try:
                    cand = Decimal(cleaned_num)
                    if cand >= Decimal("100.00"):  # filter trivial numbers like '2' or '1'
                        counteroffer = cand.quantize(Decimal("0.01"))
                        break
                except InvalidOperation:
                    continue

        # 4. Assess Rationale Score (Technical depth)
        has_tech = any(kw in text for kw in TECHNICAL_JUSTIFICATION_KEYWORDS)
        has_hinglish = any(kw in text for kw in HINGLISH_PLEA_KEYWORDS)

        if has_tech:
            rationale_score = 0.50
        elif has_hinglish or "expensive" in text or "costly" in text:
            rationale_score = 0.35
        else:
            rationale_score = 0.25

        # 5. Determine Intent
        if counteroffer is not None:
            return ClaimantIntent.COUNTER, counteroffer, rationale_score

        # No number found: check if qualitative plea
        if has_tech or has_hinglish or any(w in text for w in {"more", "low", "increase", "higher", "fair", "better"}):
            return ClaimantIntent.QUALITATIVE_PLEA, None, rationale_score

        # Default fallback: treat as qualitative request with baseline score
        return ClaimantIntent.QUALITATIVE_PLEA, None, 0.25


nlp_negotiation_parser = NLPNegotiationParser()


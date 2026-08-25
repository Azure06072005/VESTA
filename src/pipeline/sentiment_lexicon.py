"""Rule-based Vietnamese financial-news sentiment scorer (F201).

STATUS: STATED ASSUMPTION, NOT A SOURCED/VALIDATED LEXICON. Per B3
("numbers/claims need a source"), this is disclosed plainly: a web search
for an existing, publicly available Vietnamese *financial-domain* sentiment
lexicon (2026-08-25) found none with a citable, reproducible word list --
only general-purpose Vietnamese sentiment resources (e.g. Vietnamese
SentiWordNet extensions, UIT-VSMEC/UIT-VSFC emotion datasets) and
English-only finance lexicons (Loughran-McDonald). None of those are
finance-specific *and* Vietnamese *and* have a public word list that could
be imported and cited directly.

This lexicon is therefore a small, hand-built starter list of unambiguous
Vietnamese corporate-disclosure/financial-news vocabulary -- the kind of
words that appear literally in dividend announcements, earnings headlines,
and regulatory-action news (see F003/F004/F006 sample headlines already in
the repo, e.g. "phat hanh co phieu", "co tuc bang tien mat"). It is NOT
tuned or validated against a labeled Vietnamese financial-sentiment
dataset. Treat it exactly like F009's news-dedup threshold (0.75
similarity, 6-hour window): a stated assumption, cheap to ship, explicitly
flagged for revision once real labeled data or a proper VN finance lexicon
becomes available -- not a substitute for that validation.

Matching is on UNDECORATED (accent-stripped) lowercase substrings, because
headlines in this repo mix diacritics inconsistently (compare F003's
"FPT: Nghi quyet HDQT..." vs F004's diacritic-complete headlines) and a
strict accented match would silently miss real matches. Substring matching
over a short curated list is deliberately simple (Simplicity First, A2) --
no tokenization, no negation handling, no stemming. This WILL misclassify
some headlines (e.g. sarcasm, negated statements, multi-clause headlines
with mixed sentiment) -- that noise is expected and is exactly why F201's
statistical test needs a large-enough n to average it out, not proof this
lexicon is accurate at the individual-headline level.
"""
from __future__ import annotations

import re
import unicodedata

# Positive terms: unambiguous good-news vocabulary in VN financial/corporate
# disclosure text (profit growth, dividends, expansion, recovery, records).
POSITIVE_TERMS: tuple[str, ...] = (
    "tang truong",       # growth
    "loi nhuan tang",    # profit increase
    "vuot ke hoach",     # exceeded plan/target
    "khoi sac",          # picking up / brightening (business conditions)
    "but pha",           # breakthrough
    "hoi phuc",          # recover
    "ky luc",            # record (positive superlative in this domain)
    "mo rong",           # expand
    "thang dam phan",    # won a contract/negotiation
    "ky ket hop dong",   # signed a contract
    "co tuc",            # dividend (paid out -- treated as mildly positive)
    "tra co tuc",        # pay dividend
    "niem yet them",     # additional listing (growth signal)
    "lai rong tang",     # net profit increased
    "doanh thu tang",    # revenue increased
)

# Negative terms: unambiguous bad-news vocabulary (losses, defaults,
# bankruptcy, penalties, sell-offs, layoffs, lawsuits).
NEGATIVE_TERMS: tuple[str, ...] = (
    "thua lo",           # loss
    "lo rong",           # net loss
    "pha san",           # bankruptcy
    "no xau",            # bad debt
    "sut giam",          # decline
    "giam manh",         # sharp decrease
    "khung hoang",       # crisis
    "canh bao",          # warning
    "vi pham",           # violation
    "xu phat",           # penalty / fine
    "rut von",           # capital withdrawal
    "ban thao",          # sell-off
    "thoai von",         # divest
    "kien tung",         # lawsuit / litigation
    "sa thai",           # layoff
    "dinh chi",          # suspend
    "huy niem yet",      # delisting
    "no dong",           # frozen / overdue debt
    "loi nhuan giam",    # profit decreased
    "doanh thu giam",    # revenue decreased
)


def _strip_accents_lower(text: str) -> str:
    """Lowercase and strip Vietnamese diacritics for robust substring matching.

    Uses NFD decomposition + combining-mark removal, which handles standard
    Vietnamese Unicode text. Does not special-case "d" vs "đ" beyond what
    NFD naturally produces (đ decomposes to a base 'd' plus a stroke that
    NFD does not treat as a combining mark in all normalizers -- see the
    explicit .replace() below, which is a known NFD gap for Vietnamese).
    """
    text = text.lower()
    text = text.replace("đ", "d")
    nfd = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in nfd if unicodedata.category(ch) != "Mn")


def score_headline(headline: str) -> float:
    """Return a sentiment score in [-1.0, 1.0] for a single VN headline.

    Score = (positive_hits - negative_hits) / (positive_hits + negative_hits),
    clipped to [-1, 1]. Returns 0.0 (neutral) if no lexicon term matches --
    this is the "no signal" case, not an assertion that the headline is
    actually neutral in sentiment.

    A headline containing both positive and negative terms nets out
    partially rather than being forced into one bucket -- e.g. a headline
    reporting a loss alongside a dividend payment isn't purely one or the
    other, and a hand-built lexicon has no way to weigh which term is more
    salient to the reader.
    """
    if not headline:
        return 0.0
    normalized = _strip_accents_lower(headline)

    pos_hits = sum(1 for term in POSITIVE_TERMS if term in normalized)
    neg_hits = sum(1 for term in NEGATIVE_TERMS if term in normalized)

    total = pos_hits + neg_hits
    if total == 0:
        return 0.0
    score = (pos_hits - neg_hits) / total
    return max(-1.0, min(1.0, score))


def classify_headline(headline: str, neutral_band: float = 0.0) -> str:
    """Classify a headline into 'positive' / 'negative' / 'neutral'.

    neutral_band: scores with absolute value <= neutral_band are neutral.
    Default 0.0 means only an exact tie (or no lexicon hits) is neutral --
    any net-positive or net-negative score is classified accordingly. This
    default is a STATED ASSUMPTION (see module docstring); widen
    neutral_band if a future labeled sample shows near-zero scores are
    mostly noise rather than genuine weak sentiment.
    """
    score = score_headline(headline)
    if abs(score) <= neutral_band:
        return "neutral"
    return "positive" if score > 0 else "negative"


# Precompiled for reference/inspection only -- not used in the hot path,
# since substring `in` checks on a short list are already fast enough for
# this repo's data volumes (see conventions.md A2, no premature optimization).
_ALL_TERMS_PATTERN = re.compile(
    "|".join(re.escape(t) for t in POSITIVE_TERMS + NEGATIVE_TERMS)
)
"""
IBAN Extractor — Core pipeline.
Single-best IBAN extraction for speed and deterministic output.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any
from PIL import Image

from iban_validator import (
    COUNTRY_LENGTHS,
    format_iban,
    get_country_name,
    validate_iban,
)
from ocr_engine import extract_text_from_image
from pdf_handler import process_pdf_from_bytes, get_pdf_page_count

IBAN_PATTERN = re.compile(
    r"\b([A-Z]{2}\s*\d{2}"
    r"(?:[\s\-\n\./\|]?[\dA-Z]{1,4})"
    r"(?:[\s\-\n\./\|]?[\dA-Z]{2,4}){2,8})\b",
    re.IGNORECASE,
)

CONTIGUOUS_IBAN_PATTERN = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")


@dataclass
class IBANResult:
    """A single extracted IBAN with validation details."""

    raw: str
    cleaned: str
    formatted: str
    valid: bool
    country_code: str | None
    country_name: str | None
    errors: list[str]
    source_page: int | None = None


@dataclass
class ExtractionResult:
    """Full result of an extraction operation."""

    ibans: list[IBANResult] = field(default_factory=list)
    file_type: str = ""
    total_pages: int = 0
    messages: list[str] = field(default_factory=list)
    raw_text: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _correct_ocr_errors(candidate: str) -> str:
    """
    Apply OCR fixes very conservatively.
    Only normalize check digits (positions 2-3), where digits are mandatory.
    """
    if len(candidate) < 4:
        return candidate

    country = candidate[:2]
    check_digits = (
        candidate[2:4]
        .replace("O", "0")
        .replace("I", "1")
        .replace("L", "1")
    )
    bban = candidate[4:]
    return country + check_digits + bban


def _normalize_candidate(raw: str) -> str | None:
    cleaned = re.sub(r"[^A-Z0-9]", "", raw.upper())
    cleaned = _correct_ocr_errors(cleaned)
    if len(cleaned) < 5 or not (
        cleaned[:2].isalpha() and cleaned[2:4].isdigit()
    ):
        return None

    expected_length = COUNTRY_LENGTHS.get(cleaned[:2])
    if expected_length:
        if len(cleaned) == expected_length:
            return cleaned

        # Keep +1 length candidates for downstream single-char repair.
        if len(cleaned) == expected_length + 1:
            return cleaned

        # For longer candidates, accept only a validated exact-length window.
        if len(cleaned) > expected_length + 1:
            # OCR may append trailing labels (e.g. BIC/RIB) to the candidate.
            # Remove a pure letter suffix before strict window checks.
            stripped = re.sub(r"[A-Z]+$", "", cleaned)
            if stripped != cleaned:
                cleaned = stripped
                if len(cleaned) == expected_length:
                    return cleaned
                if len(cleaned) == expected_length + 1:
                    return cleaned
                if len(cleaned) >= max(15, expected_length - 1):
                    return cleaned

            max_shift = min(2, len(cleaned) - expected_length)
            for shift in range(max_shift + 1):
                window = cleaned[shift:shift + expected_length]
                if validate_iban(window)["valid"]:
                    return window
            return None

        # Allow near-miss shorter values; they may be recovered
        # by downstream correction.
        if len(cleaned) >= max(15, expected_length - 1):
            return cleaned
        return None

    if 15 <= len(cleaned) <= 34:
        return cleaned
    return None


def _iter_label_windows(text: str) -> list[str]:
    """
    Extract short generic windows immediately after an IBAN label.
    This avoids brittle document-specific stop words and relies
    on generic text proximity instead.
    """
    normalized_text = text.upper()
    windows: list[str] = []

    # Keep context before and after the label because many bank documents
    # place the value on the previous line and the "IBAN" label next.
    for label_match in re.finditer(r"I\s*B\s*A\s*N", normalized_text):
        start = max(0, label_match.start() - 140)
        end = min(len(normalized_text), label_match.end() + 140)
        window = normalized_text[start:end]

        # Remove duplicated label tokens from the local window.
        window = re.sub(r"(?:I\s*B\s*A\s*N[^A-Z0-9]*)+", " ", window)
        window = re.sub(r"\s+", " ", window).strip()

        if window:
            windows.append(window)

    return windows


def _extract_candidates(text: str) -> list[str]:
    """
    Ordered candidate extraction:
    1) text close to IBAN label (highest precision)
    2) generic IBAN regex
    3) contiguous fallback on original text (only if nothing found above)
    """
    normalized_text = text.upper()
    raw_candidates: list[str] = []

    # Priority 1: candidates right after an IBAN label to avoid
    # distant false positives.
    for window in _iter_label_windows(normalized_text):
        labeled_matches = IBAN_PATTERN.findall(window)
        if not labeled_matches:
            # Relaxed label-near pattern for OCR cases like "IT 60/A 01235 ..."
            labeled_matches = re.findall(
                r"([A-Z]{2}\s*\d{2}[\s,;:_\/\-\.\|\dA-Z]{10,40})",
                window,
            )
        raw_candidates.extend(labeled_matches)

    # Priority 2: fallback to generic scan only when label-focused
    # extraction found nothing.
    if not raw_candidates:
        raw_candidates.extend(IBAN_PATTERN.findall(normalized_text))

    if not raw_candidates:
        raw_candidates.extend(CONTIGUOUS_IBAN_PATTERN.findall(normalized_text))

    candidates: list[str] = []
    seen: set[str] = set()

    for raw in raw_candidates:
        normalized = _normalize_candidate(raw)
        if normalized:
            if normalized not in seen:
                seen.add(normalized)
                candidates.append(normalized)

    return candidates


def _try_fix_single_extra_char(candidate: str) -> str | None:
    """
    OCR-safe correction:
    if candidate is exactly one char too long for its country,
    try removing one char
    in BBAN and keep only a unique valid result.
    """
    country = candidate[:2]
    expected_length = COUNTRY_LENGTHS.get(country)
    if expected_length is None or len(candidate) != expected_length + 1:
        return None

    valid_variants: list[str] = []
    for i in range(4, len(candidate)):
        variant = candidate[:i] + candidate[i + 1:]
        if validate_iban(variant)["valid"]:
            valid_variants.append(variant)
            if len(valid_variants) > 1:
                return None

    return valid_variants[0] if len(valid_variants) == 1 else None


def _try_fix_ocr_ambiguities(candidate: str) -> str | None:
    """
    Resolve a small number of OCR-ambiguous BBAN characters by validation.
    This remains generic and only accepts a unique valid variant.
    """
    country = candidate[:2]
    expected_length = COUNTRY_LENGTHS.get(country)
    if expected_length is None or len(candidate) != expected_length:
        return None

    replacements = {
        "O": ("0",),
        "I": ("1",),
        "L": ("1",),
    }
    ambiguous_positions = [
        index for index, char in enumerate(candidate[4:], start=4)
        if char in replacements
    ]

    if not ambiguous_positions or len(ambiguous_positions) > 3:
        return None

    valid_variants: list[str] = []

    def explore(position_index: int, current: list[str]) -> bool:
        if position_index == len(ambiguous_positions):
            variant = "".join(current)
            if validate_iban(variant)["valid"]:
                valid_variants.append(variant)
                if len(valid_variants) > 1:
                    return True
            return False

        position = ambiguous_positions[position_index]
        original = current[position]

        if explore(position_index + 1, current):
            return True

        for replacement in replacements[original]:
            current[position] = replacement
            if explore(position_index + 1, current):
                return True

        current[position] = original
        return False

    explore(0, list(candidate))
    return valid_variants[0] if len(valid_variants) == 1 else None


def _build_iban_result(
    candidate: str,
    source_page: int | None = None,
) -> IBANResult:
    validation = validate_iban(candidate)
    if not validation["valid"]:
        corrected = _try_fix_single_extra_char(candidate)
        if corrected:
            validation = validate_iban(corrected)
        else:
            corrected = _try_fix_ocr_ambiguities(candidate)
            if corrected:
                validation = validate_iban(corrected)

    cleaned = validation["iban"]
    country = validation["country"]
    return IBANResult(
        raw=candidate,
        cleaned=cleaned,
        formatted=format_iban(cleaned),
        valid=validation["valid"],
        country_code=country,
        country_name=get_country_name(country) if country else None,
        errors=validation["errors"],
        source_page=source_page,
    )


def extract_from_text(
    text: str,
    source_page: int | None = None,
) -> list[IBANResult]:
    """
    Extract exactly one best IBAN from text.
    Preference: first valid candidate.
    Invalid fallback is returned only when an explicit
    IBAN label exists in text.
    """
    has_iban_label = bool(re.search(r"I\s*B\s*A\s*N", text, re.IGNORECASE))
    candidates = _extract_candidates(text)
    if not candidates:
        return []

    results = [
        _build_iban_result(candidate, source_page=source_page)
        for candidate in candidates
    ]
    for result in results:
        if result.valid:
            return [result]

    # If we have exactly one strong candidate near expected country length,
    # surface it as invalid even without an explicit IBAN label.
    if len(results) == 1:
        expected_length = COUNTRY_LENGTHS.get(results[0].cleaned[:2])
        is_near_expected = (
            expected_length
            and abs(len(results[0].cleaned) - expected_length) <= 1
        )
        if is_near_expected:
            return [results[0]]

    if not has_iban_label:
        return []

    # Only keep invalid fallback if it is very close to the
    # expected country length.
    for result in results:
        expected_length = COUNTRY_LENGTHS.get(result.cleaned[:2])
        if expected_length and abs(len(result.cleaned) - expected_length) <= 1:
            return [result]

    return []


def _extract_from_ocr_image(
    image: Image.Image,
    source_page: int | None = None,
) -> tuple[str, list[IBANResult], dict[str, str | int | bool]]:
    """
    Fast OCR first, then fallback to enhanced OCR only if needed.
    """
    quick_text = extract_text_from_image(image, preprocess=False, psm=6, oem=1)
    quick_results = extract_from_text(quick_text, source_page=source_page)
    quick_candidate_count = len(_extract_candidates(quick_text))

    if quick_results and quick_results[0].valid:
        return quick_text, quick_results, {
            "strategy": "ocr_quick",
            "candidate_count": quick_candidate_count,
            "has_iban_signal": True,
        }

    # Skip the expensive enhanced OCR pass when quick OCR shows no IBAN signal.
    has_iban_signal = bool(
        re.search(r"I\s*B\s*A\s*N|[A-Z]{2}\s*\d{2}", quick_text, re.IGNORECASE)
    )
    if not has_iban_signal:
        return quick_text, quick_results, {
            "strategy": "ocr_quick_no_signal",
            "candidate_count": quick_candidate_count,
            "has_iban_signal": False,
        }

    enhanced_text = extract_text_from_image(
        image,
        preprocess=True,
        psm=6,
        oem=1,
    )
    enhanced_results = extract_from_text(
        enhanced_text,
        source_page=source_page,
    )
    enhanced_candidate_count = len(_extract_candidates(enhanced_text))

    if enhanced_results and enhanced_results[0].valid:
        return enhanced_text, enhanced_results, {
            "strategy": "ocr_enhanced",
            "candidate_count": enhanced_candidate_count,
            "has_iban_signal": True,
        }

    if quick_results:
        return quick_text, quick_results, {
            "strategy": "ocr_quick_invalid",
            "candidate_count": quick_candidate_count,
            "has_iban_signal": True,
        }

    return enhanced_text, enhanced_results, {
        "strategy": (
            "ocr_enhanced_invalid"
            if enhanced_candidate_count
            else "ocr_enhanced_none"
        ),
        "candidate_count": enhanced_candidate_count,
        "has_iban_signal": True,
    }


def extract_from_image(image: Image.Image) -> ExtractionResult:
    """Extract one best IBAN from an image."""
    started_at = time.perf_counter()
    result = ExtractionResult(file_type="image", total_pages=1)

    text, ibans, debug = _extract_from_ocr_image(image)
    result.raw_text = text
    result.ibans = ibans
    result.diagnostics = {
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "strategy": str(debug["strategy"]),
        "candidate_count": int(debug["candidate_count"]),
        "has_iban_signal": bool(debug["has_iban_signal"]),
    }

    if not result.ibans:
        result.diagnostics["reason"] = (
            "No IBAN candidate matched the OCR text."
        )
        result.messages.append(
            "⚠️ We have not detected any IBAN in this image. "
            "Ensure the IBAN area is visible and sharp."
        )
        return result

    iban = result.ibans[0]
    if iban.valid:
        result.diagnostics["reason"] = "A valid IBAN was found."
        result.messages.append("✅ 1 IBAN detected and validated.")
        # result.messages.append(
        #     "🔍 OCR may still confuse similar characters (0/O, 1/I/l)."
        # )
    else:
        result.diagnostics["reason"] = (
            "An IBAN-like value was found but failed validation."
        )
        result.messages.append(
            "⚠️ 1 IBAN-like value detected but it failed validation."
        )
        # result.messages.append(
        #     "🔍 Please verify the document quality or characters manually."
        # )

    return result


def extract_from_pdf(file_bytes: bytes) -> ExtractionResult:
    """
    Extract one best IBAN from a PDF.
    Fast path: stop scanning as soon as one valid IBAN is found.
    """
    started_at = time.perf_counter()
    result = ExtractionResult(file_type="pdf")
    result.total_pages = get_pdf_page_count(file_bytes)

    text_parts: list[str] = []
    best_invalid: IBANResult | None = None
    pages_scanned = 0
    used_ocr = False
    last_candidate_count = 0
    last_strategy = "native_text"

    for page_data in process_pdf_from_bytes(file_bytes):
        pages_scanned += 1
        page_num = page_data["page_num"]
        text = (
            page_data["text"]
            if page_data["method"] == "native_text"
            else ""
        )

        if page_data["method"] == "ocr_needed":
            used_ocr = True
            text, ibans, debug = _extract_from_ocr_image(
                page_data["image"],
                source_page=page_num,
            )
            last_candidate_count = int(debug["candidate_count"])
            last_strategy = str(debug["strategy"])
            text_parts.append(f"--- Page {page_num} ---\n{text}")

            if not ibans:
                continue

            candidate = ibans[0]
            if candidate.valid:
                result.ibans = [candidate]
                break

            if best_invalid is None:
                best_invalid = candidate
            continue
        text_parts.append(f"--- Page {page_num} ---\n{text}")
        ibans = extract_from_text(text, source_page=page_num)
        last_candidate_count = len(_extract_candidates(text))
        last_strategy = "native_text"

        if not ibans:
            continue

        candidate = ibans[0]
        if candidate.valid:
            result.ibans = [candidate]
            break

        if best_invalid is None:
            best_invalid = candidate

    if not result.ibans and best_invalid:
        result.ibans = [best_invalid]

    result.raw_text = "\n".join(text_parts)
    result.diagnostics = {
        "elapsed_ms": round((time.perf_counter() - started_at) * 1000, 1),
        "pages_scanned": pages_scanned,
        "used_ocr": used_ocr,
        "strategy": last_strategy,
        "candidate_count": last_candidate_count,
    }

    if not result.ibans:
        result.diagnostics["reason"] = (
            "No IBAN candidate matched the PDF text or OCR output."
        )
        result.messages.append(
            f"⚠️ We have not detected any IBAN in this PDF "
            f"({result.total_pages} page(s) scanned)."
        )
        return result

    iban = result.ibans[0]
    if iban.valid:
        result.diagnostics["reason"] = "A valid IBAN was found."
        result.diagnostics["result_page"] = iban.source_page or 1
        result.messages.append(
            f"✅ 1 IBAN detected and validated "
            f"(page {iban.source_page or 1})."
        )
        # result.messages.append(
        #     "🔍 OCR may still confuse similar characters (0/O, 1/I/l)."
        # )
    else:
        result.diagnostics["reason"] = (
            "An IBAN-like value was found but failed validation."
        )
        result.diagnostics["result_page"] = iban.source_page or 1
        result.messages.append(
            "⚠️ 1 IBAN-like value detected but it failed validation."
        )
        # result.messages.append(
        #     "🔍 Please verify the document quality or characters manually."
        # )

    return result

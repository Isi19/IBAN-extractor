"""IBAN Extractor — Streamlit Application."""

import io
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, UnidentifiedImageError

from iban_extractor import (
    ExtractionResult,
    extract_from_image,
    extract_from_pdf,
)
from iban_validator import format_iban, validate_iban


st.set_page_config(page_title="IBAN Extractor", page_icon="🏦", layout="wide")

st.markdown(
    """
<style>
div[data-testid="stFileUploader"] {
    border: 1px dashed #9aa5b1;
    border-radius: 12px;
    padding: 0.2rem 0.4rem;
    max-width: 420px;
    background: #fafbfd;
}
div[data-testid="stFileUploader"] section {
    padding: 0.1rem 0;
}
</style>
""",
    unsafe_allow_html=True,
)

st.title("🏦 IBAN Extractor")
st.markdown(
    "Enter your IBAN manually, or upload an image/PDF to auto-fill the field "
    "when extraction returns a valid IBAN."
)

with st.sidebar:
    st.header("⚙️ Settings")
    st.markdown("---")
    st.markdown("### Supported formats")
    st.markdown("- **Images**: PNG, JPG, JPEG")
    st.markdown("- **PDF**: Native text & scanned/image-based")
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown(
        "1. Enter IBAN manually or upload a file\n"
        "2. Text is extracted (native or OCR)\n"
        "3. IBAN candidates are detected via regex\n"
        "4. Each IBAN is validated:\n"
        "   - Country code & length\n"
        "   - BBAN format\n"
        "   - ISO 13616 mod-97 checksum"
    )


if "iban_input" not in st.session_state:
    st.session_state["iban_input"] = ""
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "diagnostics_text" not in st.session_state:
    st.session_state["diagnostics_text"] = "No processing yet."
if "last_source" not in st.session_state:
    st.session_state["last_source"] = ""
if "last_upload_id" not in st.session_state:
    st.session_state["last_upload_id"] = ""
if "needs_rerun" not in st.session_state:
    st.session_state["needs_rerun"] = False
if "pending_iban_input" not in st.session_state:
    st.session_state["pending_iban_input"] = None
if "uploader_nonce" not in st.session_state:
    st.session_state["uploader_nonce"] = 0
if "ready_for_upload" not in st.session_state:
    st.session_state["ready_for_upload"] = False
if "open_file_dialog" not in st.session_state:
    st.session_state["open_file_dialog"] = False


def summarize_diagnostics(result: ExtractionResult) -> str:
    """Return compact processing diagnostics."""

    diagnostics = result.diagnostics or {}
    strategy = diagnostics.get("strategy", "-")
    elapsed_ms = diagnostics.get("elapsed_ms", "-")
    candidates = diagnostics.get("candidate_count", "-")
    pages = diagnostics.get("pages_scanned", result.total_pages or 1)
    reason = diagnostics.get("reason", "-")
    summary = (
        f"strategy={strategy}; time_ms={elapsed_ms}; candidates={candidates}; "
        f"pages={pages}; reason={reason}"
    )
    if "used_ocr" in diagnostics:
        summary += (
            f"; ocr_used={'yes' if diagnostics['used_ocr'] else 'no'}"
        )
    return summary


def handle_extraction_result(
    result: ExtractionResult,
    source_name: str,
) -> None:
    st.session_state["last_result"] = result
    st.session_state["last_source"] = source_name
    st.session_state["diagnostics_text"] = summarize_diagnostics(result)

    valid_iban = next((ib for ib in result.ibans if ib.valid), None)
    if valid_iban:
        formatted = format_iban(valid_iban.cleaned)
        current_or_pending = (
            st.session_state.get("pending_iban_input")
            or st.session_state["iban_input"]
        )
        if current_or_pending != formatted:
            st.session_state["pending_iban_input"] = formatted
            st.session_state["needs_rerun"] = True


def _is_pdf_upload(uploaded_file) -> bool:
    mime = (uploaded_file.type or "").lower()
    name = uploaded_file.name.lower()
    return mime == "application/pdf" or name.endswith(".pdf")


def reset_ui_state(ready_for_upload: bool) -> None:
    """Clear visible state and reset uploader widget."""
    st.session_state["last_upload_id"] = ""
    st.session_state["last_result"] = None
    st.session_state["last_source"] = ""
    st.session_state["diagnostics_text"] = "No processing yet."
    st.session_state["pending_iban_input"] = ""
    st.session_state["uploader_nonce"] += 1
    st.session_state["ready_for_upload"] = ready_for_upload


# Apply deferred auto-fill before the text_input widget is instantiated.
if st.session_state.get("pending_iban_input") is not None:
    st.session_state["iban_input"] = st.session_state["pending_iban_input"]
    st.session_state["pending_iban_input"] = None

st.subheader("IBAN")
st.text_input(
    "IBAN field (format: CCkk ...)",
    key="iban_input",
    placeholder="Type your IBAN or upload a file below",
)

st.markdown("⬆️ Upload file (auto-fill if valid)")
uploader_key = f"main_uploader_{st.session_state['uploader_nonce']}"
uploaded_file = st.file_uploader(
    "Upload image or PDF",
    type=["png", "jpg", "jpeg", "pdf"],
    label_visibility="visible",
    key=uploader_key,
)
st.caption(
    "Small drop zone: image or PDF. "
    "Auto-processing starts immediately."
)
if st.session_state["ready_for_upload"] and uploaded_file is None:
    st.info("Ready for a new upload. Select a file above.")

# Best-effort auto-open of file chooser after clicking "Try upload again".
if st.session_state["open_file_dialog"] and uploaded_file is None:
    components.html(
        """
        <script>
        (function() {
          const tryClick = () => {
            const doc = window.parent.document;
            const input = doc.querySelector(
              'div[data-testid="stFileUploader"] input[type="file"]'
            );
            if (input) {
              input.click();
            }
          };
          setTimeout(tryClick, 50);
        })();
        </script>
        """,
        height=0,
    )
    st.session_state["open_file_dialog"] = False

if uploaded_file is not None:
    upload_id = (
        f"{uploaded_file.name}:{uploaded_file.size}:{uploaded_file.type}"
    )
    if upload_id != st.session_state["last_upload_id"]:
        st.session_state["ready_for_upload"] = False
        # New file selected: clear previous file output and queued IBAN value.
        st.session_state["last_result"] = None
        st.session_state["last_source"] = uploaded_file.name
        st.session_state["diagnostics_text"] = (
            "Processing newly uploaded file..."
        )
        st.session_state["pending_iban_input"] = ""
        st.session_state["needs_rerun"] = True
        try:
            file_bytes = uploaded_file.read()
            with st.spinner("Processing uploaded file..."):
                if _is_pdf_upload(uploaded_file):
                    result = extract_from_pdf(file_bytes)
                else:
                    image = Image.open(io.BytesIO(file_bytes))
                    result = extract_from_image(image)
                handle_extraction_result(result, uploaded_file.name)
            st.session_state["last_upload_id"] = upload_id
        except UnidentifiedImageError:
            st.error(
                "Could not read this as an image. "
                "Please upload a valid image or PDF file."
            )
            st.session_state["diagnostics_text"] = (
                "upload_error=invalid_image_or_format"
            )
            st.session_state["needs_rerun"] = False
        except Exception as err:
            st.error(f"Upload processing failed: {err}")
            st.session_state["diagnostics_text"] = (
                f"upload_error={type(err).__name__}: {err}"
            )
            st.session_state["needs_rerun"] = False

if st.session_state["needs_rerun"]:
    st.session_state["needs_rerun"] = False
    st.rerun()

manual_value = st.session_state["iban_input"].strip()
manual_validation = validate_iban(manual_value) if manual_value else None

# if manual_validation is None:
#     st.info("Provide an IBAN manually or upload a file.")
# elif manual_validation["valid"]:
#     st.success("✅ Current IBAN is valid.")
# else:
#     st.warning("⚠️ Current IBAN is invalid.")

last_result = st.session_state["last_result"]
if last_result is not None:
    st.caption(f"Last processed file: {st.session_state['last_source']}")
    for msg in last_result.messages:
        if msg.startswith("⚠️"):
            st.warning(msg)
        elif msg.startswith("❌"):
            st.error(msg)
        elif msg.startswith("🔍"):
            st.info(msg)
        else:
            st.success(msg)

    with st.expander("Raw extracted text", expanded=False):
        st.text(
            last_result.raw_text
            if last_result.raw_text
            else "(no text extracted)"
        )

st.subheader("Continue")
can_continue = bool(manual_validation and manual_validation["valid"])
proceed = st.button("Continue with this IBAN", disabled=not can_continue)
if proceed:
    st.success("Validated IBAN accepted for next step.")

has_valid_from_upload = bool(
    last_result and any(ib.valid for ib in last_result.ibans)
)
if last_result is not None and not has_valid_from_upload:
    reason = (last_result.diagnostics or {}).get(
        "reason",
        "No valid IBAN could be extracted from the uploaded file.",
    )
    st.warning(f"Extraction is not valid: {reason}")
    retry_col, manual_col = st.columns(2)
    with retry_col:
        if st.button("Try upload again", key="retry_upload"):
            reset_ui_state(ready_for_upload=True)
            st.session_state["open_file_dialog"] = True
            st.rerun()
    with manual_col:
        if st.button("Enter manually", key="enter_manually"):
            reset_ui_state(ready_for_upload=False)
            st.rerun()

st.subheader("Diagnostics")
st.text_area(
    "Diagnostics field",
    value=st.session_state["diagnostics_text"],
    height=90,
    disabled=True,
)

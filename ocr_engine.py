"""OCR Engine — Text extraction from images using Tesseract."""

import os
import shutil

import pytesseract
from PIL import Image
from image_preprocessor import preprocess_full


def _configure_tesseract_cmd() -> None:
    """
    Resolve Tesseract executable path for cloud/local environments.
    Priority:
      1) TESSERACT_CMD environment variable
      2) tesseract found in PATH
    """
    explicit_cmd = os.getenv("TESSERACT_CMD")
    if explicit_cmd:
        pytesseract.pytesseract.tesseract_cmd = explicit_cmd
        return

    detected_cmd = shutil.which("tesseract")
    if detected_cmd:
        pytesseract.pytesseract.tesseract_cmd = detected_cmd


_configure_tesseract_cmd()


def extract_text_from_image(
    image: Image.Image,
    lang: str = "eng+fra",
    preprocess: bool = True,
    psm: int = 6,
    oem: int = 1,
) -> str:
    """
    Extract text from an image using Tesseract OCR.

    Args:
        image: PIL Image to process
        lang: Tesseract language string (e.g. "eng+fra+deu")
        preprocess: whether to apply image preprocessing
        psm: Tesseract page segmentation mode
        oem: Tesseract OCR engine mode

    Returns:
        Extracted text as a string
    """
    if preprocess:
        image = preprocess_full(image)

    config = f"--psm {psm} --oem {oem}"
    return pytesseract.image_to_string(image, lang=lang, config=config)

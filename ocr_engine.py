"""OCR Engine — Text extraction from images using Tesseract."""

import pytesseract
from PIL import Image
from image_preprocessor import preprocess_full


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

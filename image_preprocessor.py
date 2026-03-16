"""
Image Preprocessor — Enhance image quality before OCR.
Deskewing, binarization, noise removal for scanned documents.
"""

import cv2
import numpy as np
from PIL import Image


def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV BGR format."""
    rgb = np.array(pil_image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR image to PIL Image."""
    rgb = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert to grayscale if not already."""
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def binarize(image: np.ndarray) -> np.ndarray:
    """Adaptive thresholding for clean text on varying backgrounds."""
    gray = to_grayscale(image)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 10
    )


def denoise(image: np.ndarray) -> np.ndarray:
    """Remove noise while preserving text edges."""
    gray = to_grayscale(image)
    return cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)


def deskew(image: np.ndarray) -> np.ndarray:
    """Correct slight rotation in scanned documents."""
    gray = to_grayscale(image)
    # Detect edges and find lines
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)

    if lines is None:
        return image

    # Calculate median angle
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 15:  # Only consider near-horizontal lines
            angles.append(angle)

    if not angles:
        return image

    median_angle = np.median(angles)
    if abs(median_angle) < 0.5:  # Don't rotate for tiny angles
        return image

    # Rotate
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_REPLICATE)


def sharpen(image: np.ndarray) -> np.ndarray:
    """Sharpen text edges for better OCR recognition."""
    kernel = np.array([[-1, -1, -1],
                       [-1,  9, -1],
                       [-1, -1, -1]])
    return cv2.filter2D(image, -1, kernel)


def upscale_if_small(image: np.ndarray, min_height: int = 1000) -> np.ndarray:
    """Upscale small images for better OCR accuracy."""
    h, w = image.shape[:2]
    if h < min_height:
        scale = min_height / h
        new_w = int(w * scale)
        return cv2.resize(image, (new_w, min_height), interpolation=cv2.INTER_CUBIC)
    return image


def preprocess_light(pil_image: Image.Image) -> Image.Image:
    """
    Light preprocessing for EasyOCR (deep learning handles noise well).
    Only upscale and deskew — no binarization which can destroy detail.
    """
    img = pil_to_cv2(pil_image)
    img = upscale_if_small(img)
    img = deskew(img)
    return cv2_to_pil(img)


def preprocess_full(pil_image: Image.Image) -> Image.Image:
    """
    Full preprocessing for Tesseract (traditional CV, needs clean input).
    1. Upscale if too small
    2. Deskew
    3. Denoise
    4. Binarize
    """
    img = pil_to_cv2(pil_image)
    img = upscale_if_small(img)
    img = deskew(img)
    img = denoise(img)
    img = binarize(img)
    # binarize returns a single-channel grayscale ndarray
    return Image.fromarray(img)

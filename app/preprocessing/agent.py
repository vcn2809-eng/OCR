"""
Image Preprocessing Agent — converts PDF pages to cleaned images (deskewed, denoised,
binarized) optimised for OCR accuracy. Only applies to image-based PDF files.
"""

import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from app.config.settings import DEBUG_MODE, DEBUG_IMAGES_FOLDER
from app.preprocessing.exceptions import PDFConversionError, ImageProcessingError

logger = logging.getLogger(__name__)

def pdf_to_page_images(
    pdf_path: Path,
    dpi: int = 300,
    first_page: Optional[int] = None,
    last_page: Optional[int] = None,
) -> list[np.ndarray]:
    try:
        from pdf2image import convert_from_path
    except ImportError as e:
        raise PDFConversionError("pdf2image is not installed") from e

    try:
        kwargs = {'dpi': dpi}
        if first_page is not None:
            kwargs['first_page'] = first_page
        if last_page is not None:
            kwargs['last_page'] = last_page

        pil_images = convert_from_path(str(pdf_path), **kwargs)
        logger.info(f"Converted {len(pil_images)} page(s) from {pdf_path} (dpi={dpi})")
        cv_images = []
        for img in pil_images:
            cv_img = np.array(img.convert('RGB'))[:, :, ::-1]
            cv_images.append(cv_img)
        return cv_images
    except Exception as e:
        raise PDFConversionError(f"Failed to convert PDF {pdf_path} to images") from e

def deskew_image(image: np.ndarray) -> np.ndarray:
    try:
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=100, maxLineGap=10)
        
        if lines is None:
            logger.debug("no lines for deskew")
            return image
            
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line.flatten()[:4]
            angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
            if -45 <= angle <= 45:
                angles.append(angle)
                
        if not angles:
            logger.debug("no valid angles for deskew")
            return image
            
        median_angle = np.median(angles)
        
        if abs(median_angle) < 0.1:
            return image
            
        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, float(median_angle), 1.0)
        rotated = cv2.warpAffine(image, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return rotated
    except Exception as e:
        raise ImageProcessingError("Failed to deskew image") from e

def correct_perspective(image: np.ndarray) -> np.ndarray:
    try:
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)
        
        doc_contour = None
        total_area = image.shape[0] * image.shape[1]
        
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < 0.2 * total_area:
                break
                
            epsilon = 0.02 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            
            if len(approx) == 4:
                doc_contour = approx
                break
                
        if doc_contour is None:
            logger.debug("No 4-point contour found for perspective correction")
            return image
            
        pts = doc_contour.reshape(4, 2)
        rect = np.zeros((4, 2), dtype="float32")
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]
        rect[2] = pts[np.argmax(s)]
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]
        rect[3] = pts[np.argmax(diff)]
        
        (tl, tr, br, bl) = rect
        widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
        widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
        maxWidth = max(int(widthA), int(widthB))
        
        heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
        heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
        maxHeight = max(int(heightA), int(heightB))
        
        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype="float32")
            
        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(image, M, (maxWidth, maxHeight))
        return warped
    except Exception as e:
        raise ImageProcessingError("Failed to correct perspective") from e

def denoise_image(image: np.ndarray) -> np.ndarray:
    """High-speed noise reduction using fast median filtering, maintaining channel shape."""
    try:
        return cv2.medianBlur(image, 3)
    except Exception as e:
        raise ImageProcessingError("Failed to denoise image") from e

def binarize_image(image: np.ndarray) -> np.ndarray:
    try:
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return binary
    except Exception as e:
        raise ImageProcessingError("Failed to binarize image") from e

def preprocess_page(image: np.ndarray, document_id: str = '') -> np.ndarray:
    try:
        logger.debug("Deskewing image")
        deskewed = deskew_image(image)
        logger.debug("Correcting perspective")
        perspective = correct_perspective(deskewed)
        logger.debug("Denoising image")
        denoised = denoise_image(perspective)
        logger.debug("Binarizing image")
        binarized = binarize_image(denoised)
        
        if DEBUG_MODE and document_id:
            debug_dir = Path(DEBUG_IMAGES_FOLDER) / document_id
            debug_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(debug_dir / "01_deskewed.png"), deskewed)
            cv2.imwrite(str(debug_dir / "02_perspective.png"), perspective)
            cv2.imwrite(str(debug_dir / "03_denoised.png"), denoised)
            cv2.imwrite(str(debug_dir / "04_binarized.png"), binarized)
            
        return binarized
    except Exception as e:
        raise ImageProcessingError("Failed to preprocess page") from e

def preprocess_document(document_id: str, pdf_path: Path) -> list[np.ndarray]:
    logger.info(f"Preprocessing document {document_id}")
    images = pdf_to_page_images(pdf_path)
    processed_images = []
    for i, img in enumerate(images):
        logger.debug(f"Preprocessing page {i+1}/{len(images)}")
        processed = preprocess_page(img, document_id)
        processed_images.append(processed)
    logger.info(f"Finished preprocessing document {document_id}, {len(images)} pages")
    return processed_images

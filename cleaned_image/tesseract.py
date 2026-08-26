import importlib.util
import os

import pytesseract

fitz = None
if importlib.util.find_spec("fitz") is not None:
    import fitz  # type: ignore[import-not-found]

input_folder = "cleaned_image/processed_pages"
output_file = "extracted_file.txt"


def render_pdf_pages(input_path, output_dir):
    if fitz is None:
        raise ImportError(
            "PDF OCR support requires PyMuPDF/Fitz to be installed. "
            "Install it with: python -m pip install PyMuPDF"
        )

    doc = fitz.open(input_path)
    rendered_paths = []

    for page_no in range(doc.page_count):
        page = doc[page_no]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        stem = os.path.splitext(os.path.basename(input_path))[0]
        page_output_path = os.path.join(output_dir, f"{stem}_page_{page_no + 1}.png")
        pix.save(page_output_path)
        rendered_paths.append(page_output_path)

    doc.close()
    return rendered_paths


def perform_ocr(input_folder, output_file):
    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as output:
        for filename in os.listdir(input_folder):
            input_path = os.path.join(input_folder, filename)

            if filename.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                try:
                    text = pytesseract.image_to_string(input_path)
                    output.write(f"--- Text from {filename} ---\n")
                    output.write(text + "\n\n")
                    print(f"OCR completed for {input_path}")
                except Exception as e:
                    print(f"Error processing {input_path}: {e}")

            elif filename.lower().endswith(".pdf"):
                try:
                    rendered_paths = render_pdf_pages(input_path, input_folder)
                    for rendered_image_path in rendered_paths:
                        text = pytesseract.image_to_string(rendered_image_path)
                        output.write(
                            f"--- Text from {os.path.basename(rendered_image_path)} ---\n"
                        )
                        output.write(text + "\n\n")
                        print(f"OCR completed for {rendered_image_path}")
                except Exception as e:
                    print(f"Error processing {input_path}: {e}")


if __name__ == "__main__":
    perform_ocr(input_folder, output_file)

import importlib.util
import os
import cv2

fitz = None
if importlib.util.find_spec("fitz") is not None:
    import fitz  # type: ignore[import-not-found]

input_folder = "bill_image"
output_folder = "cleaned_image"
processed_subfolder = os.path.join(output_folder, "processed_pages")


def preprocess_image(input_path, output_path):
    color_image = cv2.imread(input_path)
    if color_image is None:
        raise ValueError(f"Unable to decode image file: {input_path}")

    gray_image = cv2.cvtColor(color_image, cv2.COLOR_BGR2GRAY)
    blurred_image = cv2.GaussianBlur(gray_image, (5, 5), 0)
    _, thresholded_image = cv2.threshold(
        blurred_image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    cv2.imwrite(output_path, thresholded_image)


def render_pdf_pages(input_path, output_dir):
    if fitz is None:
        raise ImportError(
            "PDF support requires PyMuPDF/Fitz to be installed. "
            "Install it with: python -m pip install PyMuPDF"
        )

    doc = fitz.open(input_path)
    rendered_paths = []

    for page_no in range(doc.page_count):
        page = doc[page_no]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

        stem = os.path.splitext(os.path.basename(input_path))[0]
        page_output_path = os.path.join(
            output_dir, f"{stem}_page_{page_no + 1}.png"
        )

        pix.save(page_output_path)
        rendered_paths.append(page_output_path)

    doc.close()
    return rendered_paths


def image_cleaning(input_folder, output_folder):
    valid_extensions = [".jpg", ".jpeg", ".png", ".bmp", ".pdf"]
    count = 0

    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(processed_subfolder, exist_ok=True)

    for filename in os.listdir(input_folder):
        if not any(filename.lower().endswith(ext) for ext in valid_extensions):
            continue

        input_path = os.path.join(input_folder, filename)

        try:
            if filename.lower().endswith(".pdf"):
                rendered_paths = render_pdf_pages(input_path, output_folder)

                for rendered_image_path in rendered_paths:
                    output_stem = os.path.splitext(os.path.basename(rendered_image_path))[0]
                    output_path = os.path.join(
                        processed_subfolder, f"{output_stem}_clean.png"
                    )
                    preprocess_image(rendered_image_path, output_path)
                    count += 1
                    print(f"Processed and saved: {output_path}")

            else:
                output_path = os.path.join(processed_subfolder, filename)
                preprocess_image(input_path, output_path)
                count += 1
                print(f"Processed and saved: {output_path}")

        except Exception as e:
            print(f"Error processing {input_path}: {e}")

    print(f"Total processed: {count}")


if __name__ == "__main__":
    image_cleaning(input_folder, output_folder)





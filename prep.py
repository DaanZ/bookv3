import math
import os
import shutil

from pypdf.errors import PdfStreamError

from chunks import get_page_chunks, highlight_chunk
from fragments import read_book_pages
from meta import get_book_meta, UnreadableCharactersError
from util.files import json_write_file, sanitize_filename


# Function to summarize a single book
def summarize_book(pdf_path, output_folder):
    try:
        print(f"Processing: {pdf_path}")
        # Read book pages
        pages = read_book_pages(pdf_path)
        amount_chunks = int(math.ceil(len(pages) / 25))
        page_chunks = get_page_chunks(pages, amount_chunks)
        print(f"Split book into {len(page_chunks)} chunks.")

        # Extract metadata
        meta_info = get_book_meta(pages, min(5, len(pages)))
        book_info = {"meta": meta_info, "parts": []}

        # Highlight chunks
        first_chunk = True
        for index, page_chunk in enumerate(page_chunks):
            print(f"Highlighting chunk {index + 1} of {amount_chunks}...")
            highlighted = highlight_chunk(page_chunk, first_chunk)
            book_info["parts"].append(highlighted)
            first_chunk = False

        # Write to JSON
        output_path = os.path.join(
            output_folder, f"{sanitize_filename(meta_info['title'])}.json"
        )
        json_write_file(output_path, book_info)
        print(f"Summary saved to {output_path}")

    except PdfStreamError:
        print(f"Error: Unable to read the book {pdf_path}. Please verify the file.")
    except UnreadableCharactersError:
        print(f"Error: Unable to process text in {pdf_path}.")
    except Exception as ex:
        print(f"Error processing {pdf_path}: {ex}")


# Function to process all books in the folder
def process_folder(input_folder, output_folder, book_folder: str):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    if not os.path.exists(book_folder):
        os.makedirs(book_folder)

    pdf_files = [f for f in os.listdir(input_folder) if f.lower().endswith('.pdf')]
    if not pdf_files:
        print("No PDF files found in the input folder.")
        return

    for pdf_file in pdf_files:
        pdf_path = os.path.join(input_folder, pdf_file)
        pdf_outcome_path = os.path.join(book_folder, pdf_file)
        json_file = os.path.join(
            output_folder, f"{sanitize_filename(pdf_file[:-4])}.json"
        )

        # Skip if JSON summary already exists
        if os.path.exists(json_file):
            print(f"Skipping {pdf_file}, summary already exists.")
            continue

        summarize_book(pdf_path, output_folder)

        try:
            shutil.move(pdf_path, pdf_outcome_path)
            print(f"File moved to {pdf_outcome_path}")
        except FileNotFoundError:
            print("The source file was not found.")
        except PermissionError:
            print("Permission denied. Check your file and folder permissions.")
        except Exception as e:
            print(f"An error occurred: {e}")


if __name__ == "__main__":
    # Define input and output folders
    input_folder = "next"
    output_folder = "books/available"
    book_folder = "pdfs"

    # Process books in the folder
    process_folder(input_folder, output_folder, book_folder)

import copy
import os

import rootpath
import streamlit as st
from pypdf.errors import PdfStreamError
from streamlit.runtime.uploaded_file_manager import UploadedFile

from chunks import get_page_chunks, highlight_chunk
from fragments import read_book_pages
from meta import get_book_meta, UnreadableCharactersError
from util.files import json_write_file, sanitize_filename


def reset_app():
    st.session_state.pages = None
    st.session_state.chunks = None
    st.session_state.page_chunks = None
    st.session_state.current_index = 0
    st.session_state.next_highlighted = None
    st.session_state.first_chunk = True  # Create an empty container for the Next button
    st.session_state.amount_chunks = 10  # Create an empty container for the Next button


# Render the chunk with custom CSS
def render_chunk(chunk):
    # Define the custom CSS styles
    st.title(chunk["title"])
    st.markdown(chunk["body"].replace(chunk["title"], ""), unsafe_allow_html=True)
    print("rendering chunk", chunk["title"])


# Streamlit Interface
if 'pages' not in st.session_state:
    reset_app()


def upload_stage():
    st.title("Book Summarized Viewer")
    st.session_state.amount_chunks = st.number_input("Number of parts", 5, 25, st.session_state.amount_chunks)
    uploaded_file: UploadedFile = st.file_uploader("Upload a Book file (pdf)", type="pdf")
    if uploaded_file:
        try:
            with st.spinner("Reading Book..."):
                file_path = os.path.join("uploaded_files", uploaded_file.name)
                os.makedirs("pdfs", exist_ok=True)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())

                st.session_state.pages = read_book_pages(file_path)
                st.session_state.page_chunks = get_page_chunks(st.session_state.pages, st.session_state.amount_chunks)
                print(st.session_state.page_chunks)

            meta_info = get_book_meta(st.session_state.pages, min(5, len(st.session_state.pages)))
            st.session_state.book_info = {"meta": meta_info, "parts": []}
            st.success(f"Summarizing {meta_info['title']} by {meta_info['author']} from {meta_info['publisher']}...")
        except PdfStreamError:
            st.error("Was unable to read book, please upload a different book.")
            st.session_state.pages = None
        except UnreadableCharactersError:
            st.error("Unable to read words in the book.")
            st.session_state.pages = None
            st.session_state.page_chunks = None
        except Exception as ex:
            print(ex)


def reading_stage():
    print((st.session_state.current_index + 1), st.session_state.amount_chunks)
    st.progress((st.session_state.current_index + 1) / st.session_state.amount_chunks)
    if st.session_state.next_highlighted:
        highlighted = copy.deepcopy(st.session_state.next_highlighted)
        st.session_state.next_highlighted = None
    else:
        with st.spinner("Highlighting chunk..."):
            page_chunk = st.session_state.page_chunks[st.session_state.current_index]
            print(st.session_state.first_chunk)
            highlighted = highlight_chunk(page_chunk, st.session_state.first_chunk)
            st.session_state.book_info["parts"].append(highlighted)
            st.session_state.first_chunk = False

    if highlighted:
        render_chunk(highlighted)

    print(st.session_state.current_index, st.session_state.amount_chunks - 1, len(st.session_state.page_chunks))
    if st.session_state.current_index < st.session_state.amount_chunks - 1:
        page_chunk = st.session_state.page_chunks[st.session_state.current_index + 1]
        st.session_state.next_highlighted = highlight_chunk(page_chunk, st.session_state.first_chunk)
        st.session_state.book_info["parts"].append(st.session_state.next_highlighted)

        if st.button("Next"):
            st.session_state.current_index += 1
    else:

        book_path = f"{sanitize_filename(st.session_state.book_info['meta']['title'])}.json"
        path = os.path.join(rootpath.detect(), "books", "read", book_path)
        if not os.path.exists(path):
            json_write_file(path, st.session_state.book_info)

        meta_info = st.session_state.book_info["meta"]
        st.success(f"Finished {meta_info['title']} by {meta_info['author']}!")

        reset_app()

        if st.button("Summarize another Book"):
            return


if __name__ == "__main__":
    # File upload
    try:
        if st.session_state.pages is None:
            upload_stage()

        # check again if the pages exist now.
        if st.session_state.pages:
            reading_stage()

    except Exception as ex:
        print(ex)

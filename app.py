import copy
import os

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from chunk_size import get_page_chunks
from read_fragments import read_book_pages, highlight_chunk


def reset_app():
    st.session_state.pages = None
    st.session_state.chunks = None
    st.session_state.page_chunks = None
    st.session_state.current_index = 0
    st.session_state.next_highlighted = None
    st.session_state.progress_container = st.empty()  # Create an empty container for the progress bar
    st.session_state.text_box = st.empty()
    st.session_state.button_container = st.empty()  # Create an empty container for the Next button
    st.session_state.first_chunk = True  # Create an empty container for the Next button
    st.session_state.amount_chunks = 10  # Create an empty container for the Next button


# Render the chunk with custom CSS
def render_chunk(text_box, chunk):

    # Define the custom CSS styles
    custom_css = """
    <style>
        .dyslexia-text {
            font-family: 'Lexend', sans-serif;
            font-size: 24px;
            line-height: 2;
            padding: 20px;
            border-radius: 10px;
            background-color: #f9f9f9;  /* Light background for readability */
            color: #000000;  /* Dark text color for contrast */
        }

        /* Dark theme adjustment */
        [data-testid="stAppViewContainer"] {
            background-color: #121212; /* Dark mode background */
        }
        .stApp {
            background-color: #121212;  /* Dark background for content */
        }

        /* Adjust the background of the chunk for better contrast in dark mode */
        .dyslexia-text {
            background-color: #2d2d2d;  /* Darker background for dark theme */
            color: #ffffff;  /* Light text for better contrast in dark theme */
        }

    </style>
    """

    # Inject the CSS styles
    text_box.markdown(custom_css, unsafe_allow_html=True)

    # Display the chunk
    text_box.markdown(f'<div class="dyslexia-text"><h1>{chunk["title"]}</h1>{chunk["body"]}</div>', unsafe_allow_html=True)


# Streamlit Interface
if 'pages' not in st.session_state:
    reset_app()


def upload_stage():
    st.title("Book Summarized Viewer")
    st.session_state.amount_chunks = st.number_input("Number of parts", 5, 25, st.session_state.amount_chunks)
    uploaded_file: UploadedFile = st.file_uploader("Upload a Book file (pdf)", type="pdf")
    if uploaded_file:
        with st.spinner("Reading Book..."):
            file_path = os.path.join("uploaded_files", uploaded_file.name)
            os.makedirs("uploaded_files", exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            st.session_state.pages = read_book_pages(file_path)
            st.session_state.page_chunks = get_page_chunks(st.session_state.pages, st.session_state.amount_chunks)

        st.success(f"Read book with {len(st.session_state.pages)} pages!")


def reading_stage():
    st.session_state.progress_container.progress((st.session_state.current_index + 1) / st.session_state.amount_chunks)
    print("next", st.session_state.next_highlighted)
    if st.session_state.next_highlighted:
        highlighted = copy.deepcopy(st.session_state.next_highlighted)
        st.session_state.next_highlighted = None
    else:
        with st.spinner("Highlighting chunk..."):
            page_chunk = st.session_state.page_chunks[st.session_state.current_index]
            print(st.session_state.first_chunk)
            highlighted = highlight_chunk(page_chunk, st.session_state.first_chunk)
            st.session_state.first_chunk = False

    print("Highlighted", highlighted)
    if highlighted:
        render_chunk(st.session_state.text_box, highlighted)

    print(st.session_state.current_index, st.session_state.amount_chunks - 1)
    if st.session_state.current_index < st.session_state.amount_chunks - 1:
        page_chunk = st.session_state.page_chunks[st.session_state.current_index + 1]
        st.session_state.next_highlighted = highlight_chunk(page_chunk, st.session_state.first_chunk)

        if st.session_state.button_container.button("Next"):
            st.session_state.current_index += 1

    elif st.session_state.button_container.button("Summarize another Book"):
        st.session_state.pages = None
        reset_app()


if __name__ == "__main__":
    # File upload
    if st.session_state.pages is None:
        upload_stage()

    # check again if the pages exist now.
    if st.session_state.pages:
        reading_stage()

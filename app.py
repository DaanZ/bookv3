import copy
import math
import os

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from read_fragments import read_book_pages, highlight_chunk


def reset_app():
    for key in st.session_state.keys():
        del st.session_state[key]
    st.session_state.pages = None
    st.write("<script>location.reload()</script>", unsafe_allow_html=True)


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
    st.session_state.pages = None
if 'chunks' not in st.session_state:
    st.session_state.chunks = None

if 'current_index' not in st.session_state:
    st.session_state.current_index = 0

if 'next_highlighted' not in st.session_state:
    st.session_state.next_highlighted = None

if 'progress_container' not in st.session_state:
    st.session_state.progress_container = st.empty()  # Create an empty container for the progress bar

if 'text_box' not in st.session_state:
    st.session_state.text_box = st.empty()

if 'button_container' not in st.session_state:
    st.session_state.button_container = st.empty()  # Create an empty container for the Next button

chunks = 10

# File upload
if st.session_state.pages is None:
    st.title("Book Summarized Viewer")
    uploaded_file: UploadedFile = st.file_uploader("Upload a Book file (pdf)", type="pdf")
    if uploaded_file:
        with st.spinner("Reading Book..."):
            file_path = os.path.join("uploaded_files", uploaded_file.name)
            os.makedirs("uploaded_files", exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            st.session_state.pages = read_book_pages(file_path)
            st.session_state.chunk_size = math.floor(len(st.session_state.pages) / chunks)

        st.success(f"Read book with {len(st.session_state.pages)} pages!")


if st.session_state.pages:

    st.session_state.progress_container.progress((st.session_state.current_index + 1) / chunks)

    if st.session_state.next_highlighted is None:
        with st.spinner("Highlighting chunk..."):
            s = st.session_state.current_index * st.session_state.chunk_size
            highlighted = highlight_chunk(st.session_state.pages[s:s + st.session_state.chunk_size])
    else:
        highlighted = copy.deepcopy(st.session_state.next_highlighted)
        st.session_state.next_highlighted = None

    print("Highlighted", highlighted)
    if highlighted:
        render_chunk(st.session_state.text_box, highlighted)

    print(st.session_state.current_index, chunks - 1)
    if st.session_state.current_index < chunks - 1:
        s = (st.session_state.current_index+1)*st.session_state.chunk_size
        st.session_state.next_highlighted = highlight_chunk(st.session_state.pages[s:s+st.session_state.chunk_size])

        if st.session_state.button_container.button("Next"):
            st.session_state.current_index += 1

    elif st.session_state.button_container.button("Summarize another Book"):
        reset_app()

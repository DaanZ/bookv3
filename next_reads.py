import os
import json
import shutil

import streamlit as st

from hardcover.request import mark_book_as_read
from homework import HomeworkModel, random_answer_model
from util.chatgpt import llm_strict
from util.history import History


# Folder containing the JSON files
BOOKS_FOLDER = "books/available"
FINISHED_FOLDER = "books/read"


# Function to get all JSON files in the folder
def get_json_files(folder):
    try:
        return [os.path.join(folder, file) for file in os.listdir(folder) if file.endswith(".json")]
    except FileNotFoundError:
        st.error(f"The folder '{folder}' does not exist.")
        return []


# Function to extract book details from a JSON file
def extract_book_details(file_path):
    try:
        with open(file_path, "r") as file:
            data = json.load(file)
        meta = data.get("meta", {})
        return {
            "path": file_path,
            ""
            "Title": meta.get("title", "Unknown Title"),
            "Author": meta.get("author", "Unknown Author"),
            "Category": meta.get("category", "Unknown Category"),
            "Publisher": meta.get("publisher", "Unknown Publisher"),
            "Pages": meta.get("pages", "Unknown Pages"),
            "Image": data.get("image", None),
            "parts": data.get("parts", [])
        }
    except (json.JSONDecodeError, FileNotFoundError):
        st.error(f"Failed to read or decode {file_path}.")
        return None


def read_books():
    json_files = get_json_files(BOOKS_FOLDER)

    if json_files:
        # Create a dropdown to select a book
        st.session_state.book_options = {}
        for json_file in json_files:
            book = extract_book_details(json_file)
            if book:
                st.session_state.book_options[book["Title"]] = json_file


def move_book_file(path):
    try:
        output_path = path.replace(BOOKS_FOLDER, FINISHED_FOLDER)
        shutil.move(path, output_path)
        print(f"File moved to {output_path}")
    except FileNotFoundError:
        print("The source file was not found.")
    except PermissionError:
        print("Permission denied. Check your file and folder permissions.")
    except Exception as e:
        print(f"An error occurred: {e}")


def render_chunk(segment, number_chunks):
    st.session_state.progress.progress((st.session_state.segment_index + 1) / number_chunks)
    if segment["title"] not in segment["body"]:
        st.session_state.title.title(segment["title"])
    st.session_state.text.markdown(segment["body"], unsafe_allow_html=True)


def book_interface():
    if not st.session_state.book_options:
        st.write("No JSON files found in the folder.")
        return

    return st.session_state.selector.selectbox("Select a book to read:", list(st.session_state.book_options.keys()))


def view_summary(selected_title):

    if st.session_state.current_book != selected_title:
        st.session_state.segment_index = 0
        print("reset segment index")
        st.session_state.current_book = selected_title

    selected_file = st.session_state.book_options[selected_title]
    book_details = extract_book_details(selected_file)

    if not book_details:
        return None, None, None

    number_chunks = len(book_details["parts"])
    if st.session_state.segment_index + 1 > number_chunks:
        return None, None, None

    if st.session_state.button.button("Next chunk"):
        st.session_state.segment_index += 1
        print("next chunk ", st.session_state.segment_index)

    # Display segments with navigation
    segment = book_details["parts"][st.session_state.segment_index]
    render_chunk(segment, number_chunks)

    return number_chunks, book_details, segment


def finish_book(book_details):
    st.session_state.button.empty()
    st.success("Finished Book: " + book_details["Title"] + " - " + book_details['Author'])
    response = mark_book_as_read(book_details["Title"], book_details['Author'])
    if "error" in response:
        st.error(response["error"])
    else:
        st.success("Added to Hardcover read list.")
    move_book_file(book_details["path"])


def create_homework(segment):
    history = History()
    history.system(segment["body"])
    homework: HomeworkModel = llm_strict(history, base_model=random_answer_model())
    with st.session_state.homework.container():
        st.text("Question: " + homework.question)
        options = ["A: " + homework.answer_A, "B: " + homework.answer_B, "C: " + homework.answer_C, "D: " + homework.answer_D]
        st.radio("Options", options=options)


if __name__ == "__main__":

    # Streamlit app
    st.title("Book Reader")

    if "current_book" not in st.session_state:
        st.session_state.current_book = None

        st.session_state.selector = st.empty()
        st.session_state.progress = st.empty()
        st.session_state.title = st.empty()
        st.session_state.text = st.empty()
        st.session_state.button = st.empty()
        st.session_state.homework = st.empty()

    # Get JSON files
    if "book_options" not in st.session_state:
        read_books()

    selected_title = book_interface()

    if selected_title:
        number_chunks, book_details, segment = view_summary(selected_title)

        if st.session_state.segment_index + 1 == number_chunks:
            finish_book(book_details)
            read_books()
        #else:
            #   create_homework(segment)
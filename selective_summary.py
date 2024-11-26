
from util.chatgpt import llm_chat
from util.files import json_write_file, json_read_file
from util.history import History


if __name__ == "__main__":
    path = "books/effective_communication.json"
    context = "I am having a problem with someone in my work team and I want to learn some lessons that make it easier to relate to what this book has to tell."
    book = json_read_file(path)

    for part in book["content"]:
        history = History()
        history.system("Summary: " + part["summary"])
        history.user("User Context: " + context)
        history.system("Rewrite the summary based on the user context:")
        part["personalized"] = llm_chat(history)

    json_write_file(path, book)


from util.chatgpt import llm_chat
from util.files import json_write_file, json_read_file
from util.history import History


if __name__ == "__main__":
    path = "books/effective_communication.json"
    book = json_read_file(path)

    for part in book["content"]:
        history = History()
        history.system("Summary: " + part["summary"])
        history.system("Use markup to highlight important words and sentences for someone with dyslexia:")
        part["highlighted"] = llm_chat(history)

    json_write_file(path, book)

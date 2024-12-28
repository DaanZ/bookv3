import random

from pydantic import Field, BaseModel

from util.chatgpt import llm_strict
from util.files import json_read_file
from util.history import History

book = json_read_file("books/available/How_to_Fight_a_Hydra_Face_Your_Fears,_Pursue_Your_Ambitions,_and_Become_the_Hero_You_Are_Destined_to_Be.json")


class HomeworkModel(BaseModel):
    question: str = Field(..., description="Question to ask the student to see if they understood the text.")
    answer_A: str
    answer_B: str
    answer_C: str
    answer_D: str


class HomeworkAModel(HomeworkModel):
    answer_A: str = Field(..., description="Correct Answer to the Question.")
    answer_B: str = Field(..., description="First Incorrect Answer to the Question.")
    answer_C: str = Field(..., description="Second Incorrect Answer to the Question.")
    answer_D: str = Field(..., description="Third Incorrect Answer to the Question.")


class HomeworkBModel(HomeworkModel):
    answer_A: str = Field(..., description="First Incorrect Answer to the Question.")
    answer_B: str = Field(..., description="Correct Answer to the Question.")
    answer_C: str = Field(..., description="Second Incorrect Answer to the Question.")
    answer_D: str = Field(..., description="Third Incorrect Answer to the Question.")


class HomeworkCModel(HomeworkModel):
    answer_A: str = Field(..., description="First Incorrect Answer to the Question.")
    answer_B: str = Field(..., description="Second Incorrect Answer to the Question.")
    answer_C: str = Field(..., description="Correct Answer to the Question.")
    answer_D: str = Field(..., description="Third Incorrect Answer to the Question.")


class HomeworkDModel(HomeworkModel):
    answer_A: str = Field(..., description="First Incorrect Answer to the Question.")
    answer_B: str = Field(..., description="Second Incorrect Answer to the Question.")
    answer_C: str = Field(..., description="Third Incorrect Answer to the Question.")
    answer_D: str = Field(..., description="Correct Answer to the Question.")


def random_answer_model():
    return random.choice([HomeworkAModel, HomeworkBModel, HomeworkCModel, HomeworkDModel])


for part in book["parts"]:
    history = History()
    history.system(part["body"])
    print(part["body"])
    homework: HomeworkModel = llm_strict(history, base_model=random_answer_model())

    print("Question: ", homework.question)
    print("A:", homework.answer_A)
    print("B:", homework.answer_B)
    print("C:", homework.answer_C)
    print("D:", homework.answer_D)
    break
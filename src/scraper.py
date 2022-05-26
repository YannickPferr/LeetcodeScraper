import re
from pathlib import Path

import pandas as pd
import requests

from config import CSRF_TOKEN, SESSION
from constants import *


def string_to_java_class_name(string):
    regex = r"\bII\b|\bIII\b|\bIV\b|\bVI\b|\bVII\b|\bVIII\b"
    string = string.replace("(", " ")
    string = string.replace(")", " ")
    return "".join(map(lambda x: x if re.search(regex, x) else x.capitalize(), string.strip().split(" ")))

def construct_java_file(id, title, difficulty, url, java_class_name, code):
    comment = """
    /**
    * Problem: {id}. {title}
    * Difficulty: {difficulty}
    * Link: {url}
    */
    """.format(id=id, title=title, difficulty=difficulty, url=url)
    code = re.sub(r"\bclass Solution\b", "public class " + java_class_name, code)
    return comment + code

#auth
header = {"Referer": LEETCODE_BASE_URL, "x-csrftoken": CSRF_TOKEN}
cookie = {"LEETCODE_SESSION": SESSION}

#query all problems and filter solved ones
response = requests.post(url=GRAPHQL_BASE_URL, headers=header, cookies=cookie, json={"query" : ALL_PROBLEMS_QUERY, "variables": {"categorySlug":"","skip":0,"limit":10000,"filters":{}}})
all_problems = pd.json_normalize(response.json()["data"]["problemsetQuestionList"]["questions"])
solved_problems = all_problems[all_problems["status"] == "ac"].reset_index()

#create category lookup from neetcode 150 list -> https://neetcode.io/
neetcode150 = pd.read_csv(PARENT_DIR / "neetcode150.csv", sep=";")
category_lookup = {}
for index, row in neetcode150.iterrows():
    path = Path(SUBMISSIONS_DIR, row["Category"].lower(), row["Difficulty"].lower())
    category_lookup[row["Problem"].lower()] = path

#find the last submitted code for all the solved problems and save them as java files grouped by type of problem and difficulty
num_solved = len(solved_problems)
for index, row in solved_problems.iterrows():
    #find last submitted code for this problem
    id, title, difficulty, url = row["frontendQuestionId"], row["title"], row["difficulty"], PROBLEMS_BASE_URL + row["titleSlug"]
    params = {"qid": id, "lang": CODE_LANG_TO_RETRIEVE}
    response = requests.get(url=SUBMISSIONS_URL, headers=header, cookies=cookie, params=params)

    #if submission not found its probably because of the wrong question id, so query problem details to find real id and retry
    if response.status_code != 200:
        print("Couldn't fetch code for question '{title}' with url {url}, retrying...".format(title=title, url=url))
        response = requests.post(url=GRAPHQL_BASE_URL, headers=header, cookies=cookie, json={"query" : PROBLEM_DETAILS_QUERY, "variables": {"titleSlug": row["titleSlug"]}})
        question_id = response.json()["data"]["question"]["questionId"]
        params = {"qid": question_id, "lang": CODE_LANG_TO_RETRIEVE}
        response = requests.get(url=SUBMISSIONS_URL, headers=header, cookies=cookie, params=params)
        if response.status_code != 200:
            print("Couldn't fetch code on retry, skipping question!".format(title=title, url=url))
            continue

    #create paths if not exists
    #e.g. submissions/backtracking/easy, submissions/backtracking/medium, submissions/greedy/easy, ...
    path = category_lookup[title.lower()] if title.lower() in category_lookup else Path(SUBMISSIONS_DIR, "other", difficulty.lower())
    path.mkdir(parents=True, exist_ok=True)

    #construct java file
    java_class_name=string_to_java_class_name(title)
    java_file = construct_java_file(id, title, difficulty, url, java_class_name, response.json()["code"])

    #save to file
    f = open(path / (java_class_name + ".java"), "w")
    f.write(java_file)
    f.close()
    print("{a}/{b} done!".format(a=index + 1, b=num_solved))

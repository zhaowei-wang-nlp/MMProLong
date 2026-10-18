import json

from tqdm import tqdm


current_question_type = ["calculate", "compare", "count"]
current_question_name = "math"
page_flag = "all_page"

input_path = "/path/to/workspace/pdf_data/longdocurl_data/LongDocURL_public_with_subtask_category.jsonl"
output_path = (
    f"/path/to/workspace/pdf_data/longdocurl_data/LongDocURL_exemplar_{current_question_name}_{page_flag}.jsonl"
)

with open(input_path, "r") as fin:
    dataset = [json.loads(line) for line in fin]

new_dataset = [data for data in dataset if data["question_type"] in current_question_type]
dataset = new_dataset

# single page or multi page or all_page
new_dataset = []
for data in tqdm(dataset, f"filtering by page_flag {page_flag}"):
    if page_flag == "multi_page":
        if len(data["evidence_pages"]) > 1:
            new_dataset.append(data)
    elif page_flag == "single_page":
        if len(data["evidence_pages"]) == 1:
            new_dataset.append(data)
    elif page_flag == "all_page":
        new_dataset.append(data)
    else:
        raise ValueError(f"Unknown page_flag: {page_flag}")
dataset = new_dataset

# answer type sort
dataset = sorted(dataset, key=lambda x: x["answer_format"])

with open(output_path, "w") as fout:
    for data in dataset:
        fout.write(json.dumps(data, ensure_ascii=False) + "\n")

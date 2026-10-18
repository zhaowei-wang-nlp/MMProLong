import argparse
import base64
import json
import os
import random
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import partial

import pyarrow.parquet as pq
from openai import OpenAI
from prompt_utils import QA_GENERATION_PROMPT_TEMPLATE, exemplar_prompt_template
from tqdm import tqdm
from utils import listdir


random.seed(42)

image_special_token = "<special_image_token_12345>"
page_template = "Page {page_id}: " + image_special_token
title_and_section_tags = {"title", "sec"}


_detailed_task_description = None
_extra_page_restriction = ""
_exemplar_data = None
_client = None


def worker_init(detailed_task_description, extra_page_restriction, exemplar_data):
    global _detailed_task_description, _extra_page_restriction, _exemplar_data
    _detailed_task_description = detailed_task_description
    _extra_page_restriction = extra_page_restriction
    _exemplar_data = exemplar_data

    global _client
    api_key = os.environ.get("VQA_API_KEY") or os.environ.get("ARK_API_KEY")
    base_url = os.environ.get("VQA_API_BASE_URL")
    if not api_key or not base_url or not os.environ.get("VQA_API_MODEL"):
        raise ValueError("Set VQA_API_KEY, VQA_API_BASE_URL and VQA_API_MODEL before generating QA pairs.")
    _client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )


def sample_page_selection(title_tag_list, min_qa_pair_page_num):
    assert len(title_tag_list) >= 2

    start_page_idx = end_page_idx = random.choice(range(len(title_tag_list) - 1))

    # extend end page first
    for end_page_idx in range(end_page_idx, len(title_tag_list)):
        end_page = title_tag_list[end_page_idx]
        if end_page - title_tag_list[start_page_idx] + 1 >= min_qa_pair_page_num:
            break

    # then extend start page
    for start_page_idx in range(start_page_idx, -1, -1):
        start_page = title_tag_list[start_page_idx]
        if title_tag_list[end_page_idx] - start_page + 1 >= min_qa_pair_page_num:
            break

    return title_tag_list[start_page_idx], title_tag_list[end_page_idx]


def format_chat(text, image_list):
    content = re.split(r"({})".format(image_special_token), text)
    image_idx, new_content = 0, []
    for c in content:
        if c == image_special_token:
            new_content.append({"type": "image_url", "image_url": image_list[image_idx]})
            image_idx += 1
        elif c.strip():
            new_content.append({"type": "text", "text": c})
    assert image_idx == len(image_list)
    return new_content


def build_example_prompt(row, exemplar_num, image_pool, ocr_pool):
    row_source, row_id, page_count = row["source"], row["id"], row["page_count"]
    row_global_id = f"{row_source}__{row_id}"
    ocr_json_path = os.path.join(ocr_pool, row_source, f"{row_id}.json")
    page_img_path_temp = os.path.join(image_pool, row_source, row_id[:1], f"{row_global_id}_page{{page_id}}.png")

    # split the document by title and section
    with open(ocr_json_path) as f:
        ocr_data = json.load(f)

    title_tag = [0]
    for page_data in ocr_data:
        page_id = page_data["page_id"]
        page_blocks = json.loads(page_data["page_blocks"])
        for block in page_blocks:
            block_label = block["label"]
            if block_label in title_and_section_tags:
                title_tag.append(page_id)
                break
    title_tag.append(page_count - 1)

    # sample a section
    min_qa_pair_page_num, max_qa_pair_page_num = 8, 15
    start_page, end_page, retry_count = None, None, 0
    while retry_count < 3 and (start_page is None or end_page - start_page + 1 > max_qa_pair_page_num):
        start_page, end_page = sample_page_selection(title_tag, min_qa_pair_page_num)
        retry_count += 1

    # the page count might still be larger than max_qa_pair_page_num, back to random selection pages in the current section
    if end_page - start_page + 1 > max_qa_pair_page_num:
        latest_possible_start = end_page - max_qa_pair_page_num + 1
        start_page = random.randint(start_page, latest_possible_start)
        end_page = start_page + max_qa_pair_page_num - 1

    if start_page is None or end_page is None:
        raise ValueError(f"Failed to sample a valid section for row {row_global_id} after {retry_count} retries.")

    page_img_list = [page_img_path_temp.format(page_id=page_id) for page_id in range(start_page, end_page + 1)]

    # build in-context exemplar
    global _exemplar_data
    curr_exemplar_list = random.sample(_exemplar_data, exemplar_num)
    curr_exemplar_prompt_list = []
    for exemplar_index, exemplar in enumerate(curr_exemplar_list):
        json_dump_str = json.dumps(
            {
                "question": exemplar["question"],
                "answer": str(exemplar["answer"]),
                "answer_format": exemplar["answer_format"],
                "evidence_pages": exemplar["evidence_pages"],
                "evidence_sources": exemplar["evidence_sources"],
            },
            ensure_ascii=False,
        )
        curr_exemplar_prompt_list.append(
            exemplar_prompt_template.format(
                json_dump_str=json_dump_str,
                exemplar_index=exemplar_index + 1,
                detailed_evidences=exemplar["detailed_evidences"],
            )
        )
    few_qa_examples = "\n\n".join(curr_exemplar_prompt_list)

    # build final prompt with current case
    current_case_image_sequence = "\n".join(
        [page_template.format(page_id=page_id) for page_id in range(start_page, end_page + 1)]
    )

    current_case_prompt = QA_GENERATION_PROMPT_TEMPLATE.format(
        detailed_task_description=_detailed_task_description,
        few_qa_examples=few_qa_examples,
        current_case_image_sequence=current_case_image_sequence,
        extra_page_restriction=_extra_page_restriction,
        start_page=start_page,
        end_page=end_page,
    )

    return current_case_prompt, page_img_path_temp, page_img_list, list(range(start_page, end_page + 1))


def convert_to_chat_format(current_case_prompt, page_img_list):
    # convert to base64
    base64_page_img_list = []
    for page_img in page_img_list:
        mime_type = os.path.splitext(page_img)[1][1:]
        with open(page_img, "rb") as f:
            b64_str = base64.b64encode(f.read()).decode("utf-8")
            base64_page_img_list.append(f"data:image/{mime_type};base64,{b64_str}")

    # change to chat format
    chat_format_prompt = [{"role": "user", "content": format_chat(current_case_prompt, base64_page_img_list)}]
    return chat_format_prompt


def api_retry_wrapper(func, limit: int = 5, initial_pause: int = 5, return_rate_limit=False):
    """
    Call the API function with retries and rate limit handling.
    TODO: more error handling?
    """
    count = 0
    while True:
        try:
            output = func()
            break
        except Exception as e:
            print(f"Exception while using api: {e}")
            msg = str(e).lower()

            if "rate limit" in msg or "rate_limit" in msg or "quota" in msg or "429" in msg or "overloaded" in msg:
                if return_rate_limit:
                    print("Rate limit exceeded, returning")
                    return "rate limit"
            if "error code: 400" in msg or "400" in msg or "request entity too large" in msg:
                print(f"Encountered error {e}, return None")
                return None
            count += 1
            if count < limit:
                wait_time = initial_pause * (2 ** (count - 1)) * random.uniform(0.8, 1.2)
                wait_time = min(wait_time, 60.0)
                print(f"Encountered error {e}, retrying in {wait_time:.2f} seconds...")
                time.sleep(wait_time)
            else:
                print("Skipping generation due to unknown error")
                raise e
    return output


def call_llm_api(chat_format_prompt):
    func = partial(
        _client.chat.completions.create,
        model=os.environ["VQA_API_MODEL"],
        messages=chat_format_prompt,
        timeout=120,
    )
    completion = api_retry_wrapper(func, limit=5, initial_pause=5)
    return completion


def process_single_row(row, exemplar_num, image_pool_path, ocr_pool_path):
    try:
        # prompt LLM
        current_case_prompt, page_img_path_temp, page_img_list, page_idx_list = build_example_prompt(
            row, exemplar_num, image_pool_path, ocr_pool_path
        )
        chat_format_prompt = convert_to_chat_format(current_case_prompt, page_img_list)

        # call LLM API
        completion = call_llm_api(chat_format_prompt)
        qa_content = completion.choices[0].message.content

        save_row = {
            "source": row["source"],
            "id": row["id"],
            "global_id": f"{row['source']}__{row['id']}",
            "qa_page_idx_list": page_idx_list,
            "qa_page_img_list": page_img_list,
            "qa_prompt": current_case_prompt,
            "qa_content": qa_content,
            "page_count": row["page_count"],
            "page_img_path_temp": page_img_path_temp,
        }
        return save_row

    except Exception as e:
        print(f"Error processing row {row.get('global_id', 'unknown')}: {e}")
        return None


def prompt_light_weight_vqa_data(file_path, image_pool_path, ocr_pool_path, output_path, exemplar_num, batch_size):
    parquet_file_obj = pq.ParquetFile(file_path)
    num_row_groups = parquet_file_obj.num_row_groups

    pbar = tqdm(
        total=parquet_file_obj.metadata.num_rows,
        desc=f"building examples {os.path.basename(file_path)}",
        position=1,
        unit="pdf",
        mininterval=0.5,
    )

    for i in range(num_row_groups):
        # tmp save path for current group
        base_name, _ = os.path.splitext(os.path.basename(output_path))
        cur_group_output_path = os.path.join(os.path.dirname(output_path), f"{base_name}_group{i}.json")

        if os.path.exists(cur_group_output_path):
            continue

        tmp_dir = os.path.join("/tmp", os.path.dirname(cur_group_output_path).split("/")[-1])
        os.makedirs(tmp_dir, exist_ok=True)
        tmp_output_path = os.path.join(tmp_dir, os.path.basename(cur_group_output_path))

        fout = open(tmp_output_path, "w")

        # in-case the connection is not stable
        df_chunk = pq.ParquetFile(file_path).read_row_group(i).to_pandas()

        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            future_ordered_list = []
            future2row_dict = {}

            for _, row in df_chunk.iterrows():
                future = executor.submit(process_single_row, row, exemplar_num, image_pool_path, ocr_pool_path)
                future_ordered_list.append(future)
                future2row_dict[future] = row

            for future in as_completed(future_ordered_list):
                try:
                    save_row = future.result()
                    pbar.update(1)
                    if save_row is not None:
                        fout.write(json.dumps(save_row, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"Error processing row {future2row_dict[future].get('global_id', 'unknown')}: {e}")

        fout.close()
        shutil.move(tmp_output_path, cur_group_output_path)
        print(f"Finished processing group {cur_group_output_path}")


def load_question_type_prompt(question_type, page_flag):
    if question_type == "extract":
        from prompt_utils import extract_prompt_template_dict

        prompt_template_dict = extract_prompt_template_dict
    elif question_type == "math":
        from prompt_utils import math_prompt_template_dict

        prompt_template_dict = math_prompt_template_dict
    else:
        raise ValueError(f"Unsupported question type: {question_type}")

    detailed_task_description = prompt_template_dict["detailed_task_description"]

    if page_flag == "single_page":
        exemplar_file = prompt_template_dict["single_page_exemplar_file"]
        extra_page_restriction = prompt_template_dict["extra_single_page_restriction"]
    elif page_flag == "multi_page":
        exemplar_file = prompt_template_dict["multi_page_exemplar_file"]
        extra_page_restriction = prompt_template_dict["extra_multi_page_restriction"]
    elif page_flag == "all_page":
        exemplar_file = prompt_template_dict["all_page_exemplar_file"]
        extra_page_restriction = prompt_template_dict["extra_all_page_restriction"]
    else:
        raise ValueError(f"Unsupported page flag: {page_flag}")

    with open(exemplar_file, "r") as f:
        exemplar_data = [json.loads(line) for line in f]
    return detailed_task_description, extra_page_restriction, exemplar_data


# 5. page index
# 6. num of page

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_dir", type=str, default="/path/to/hdfs_root/LongVLM_data/long_doc_sample_min50page_max100page_en/data"
    )
    parser.add_argument("--image_pool_path", type=str, default="/path/to/workspace/pdf_data/pdf_pool_img_144dpi")
    parser.add_argument("--ocr_pool_path", type=str, default="/path/to/workspace/pdf_data/pdf_pool/book_blocks")
    parser.add_argument("--output_dir", type=str, default="/path/to/hdfs_root/LongVLM_data/long_vqa_data_144dpi_all")
    parser.add_argument("--output_file_subdir", type=str, default="tmp")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--question_type", type=str, default="extract")
    parser.add_argument("--page_flag", type=str, default="multi_page")
    parser.add_argument("--exemplar_num", type=int, default=2)
    parser.add_argument("--api_batch_size", type=int, default=12)  # 12)
    parser.add_argument("--start_idx", type=int, default=None)
    parser.add_argument("--end_idx", type=int, default=120)
    args = parser.parse_args()

    input_folder_name = os.path.abspath(args.input_dir).split("/")[-2]
    match = re.search(r"min(\d+)page_max(\d+)page", input_folder_name)
    if match:
        min_val = match.group(1)
        max_val = match.group(2)
        length_tag = f"min{min_val}max{max_val}"
    else:
        raise ValueError(f"Unsupported input folder name: {input_folder_name}")

    args.output_dir = os.path.join(args.output_dir, f"{args.output_file_subdir}_{args.question_type}_{args.page_flag}")

    parquet_list = [file for file in listdir(args.input_dir) if file.endswith(".parquet")]
    parquet_list = sorted(parquet_list, key=lambda x: int(os.path.basename(x).split(".")[0].split("-")[-1]))
    print(f"processing [{args.start_idx}:{args.end_idx}] parquets")
    parquet_list = parquet_list[args.start_idx : args.end_idx]

    # load prompt
    detailed_task_description, extra_page_restriction, exemplar_data = load_question_type_prompt(
        args.question_type, args.page_flag
    )

    os.makedirs(args.output_dir, exist_ok=True)

    tasks = [
        (
            file,
            args.image_pool_path,
            args.ocr_pool_path,
            os.path.join(args.output_dir, f"{length_tag}-{os.path.basename(file)}"),
            args.exemplar_num,
            args.api_batch_size,
        )
        for i, file in enumerate(parquet_list)
    ]

    worker_init(detailed_task_description, extra_page_restriction, exemplar_data)
    for t in tasks:
        prompt_light_weight_vqa_data(*t)

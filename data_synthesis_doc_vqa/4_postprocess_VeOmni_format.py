import argparse
import ast
import hashlib
import json
import multiprocessing as mp
import os
import re

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from api_parse_utils import image_special_token, item_template, parse_qa_pair_output, system_template, user_template
from PIL import Image
from tqdm import tqdm
from transformers import AutoProcessor


MIN_TOKEN_CNT = None
MAX_TOKEN_CNT = None
MIN_PAGE_CNT = None
MAX_PAGE_CNT = None

_local_processor = None
_merge_size = None
_patch_size = None
_question_type = None
_page_flag = None


def worker_init(min_K_length, max_K_length, min_page, max_page, tokenizer_name, question_type, page_flag):
    global MIN_TOKEN_CNT, MAX_TOKEN_CNT
    print("init token length")
    MIN_TOKEN_CNT = min_K_length * 1024
    MAX_TOKEN_CNT = max_K_length * 1024

    global MIN_PAGE_CNT, MAX_PAGE_CNT
    MIN_PAGE_CNT = min_page
    MAX_PAGE_CNT = max_page

    global _local_processor, _merge_size, _patch_size
    print("init processor")
    _local_processor = AutoProcessor.from_pretrained(tokenizer_name)
    _merge_size = _local_processor.image_processor.merge_size
    _patch_size = _local_processor.image_processor.patch_size

    global _question_type, _page_flag
    _question_type = question_type
    _page_flag = page_flag


def calculate_image_tokens(width, height, patch_size=14, merge_size=2):
    factor = patch_size * merge_size
    w_patch, h_patch = round(width / factor), round(height / factor)
    return w_patch * h_patch + 2


def compute_prompt_length(chat_format_prompt, tokenizer, patch_size, merge_size):
    token_count = 0
    for prompt in chat_format_prompt:
        for m in prompt["content"]:
            if m["type"] == "text":
                token_list = tokenizer.encode(m["text"], add_special_tokens=False)
                token_count += len(token_list)
            elif m["type"] == "image_url":
                token_count += calculate_image_tokens(
                    m["image_url"]["width"], m["image_url"]["height"], patch_size=patch_size, merge_size=merge_size
                )
            else:
                raise ValueError(f"Unsupported message type: {m['type']}")
    return token_count


def convert_to_llava_format(row_data, chat_format_prompt):
    global_id = row_data["global_id"]

    conversations = []
    image_info_list = []

    for turn in chat_format_prompt:
        role = "human" if turn["role"] == "user" else "gpt"
        text_content = ""

        for content_item in turn["content"]:
            if content_item["type"] == "text":
                if "<image>" in content_item["text"]:
                    raise ValueError(f"Global ID {global_id}: Text content should not contain '<image>' token.")
                text_content += content_item["text"]
            elif content_item["type"] == "image_url":
                text_content += "<image>"
                image_info_list.append(content_item["image_url"])

        conversations.append({"from": role, "value": text_content})

    image_bytes_list = []
    for image_info in image_info_list:
        with open(image_info["url"], "rb") as f:
            image_bytes_list.append(f.read())

    md5_hash = hashlib.md5(
        (row_data["qa_json"]["question"] + str(row_data["qa_json"]["answer"])).encode("utf-8")
    ).hexdigest()[:16]
    row_data["id"] = global_id + "-hash-" + md5_hash
    row_data["conversations"] = json.dumps(conversations, ensure_ascii=False)
    row_data["images"] = image_bytes_list
    row_data["source_name"] = "long_vqa_data" + "-" + _question_type + "-" + _page_flag

    return row_data


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


def truncate_doc_image_list(new_row, add_cot):
    # get prompt length first approximately
    approx_prompt_count = 0
    approx_prompt_count += len(_local_processor.tokenizer.encode(user_template, add_special_tokens=False))
    approx_prompt_count += len(_local_processor.tokenizer.encode(system_template, add_special_tokens=False))
    approx_prompt_count += len(
        _local_processor.tokenizer.encode(new_row["qa_json"]["question"], add_special_tokens=False)
    )

    answer = new_row["qa_json"]["answer"]
    if add_cot:
        answer = new_row["qa_evidence_description"] + "\n In summary, the answer is " + answer
    approx_prompt_count += len(_local_processor.tokenizer.encode(answer, add_special_tokens=False))

    # get final image_list
    image_info_list = []
    for page_id in range(new_row["page_count"]):
        curr_page_img_path = new_row["page_img_path_temp"].format(page_id=page_id)
        with Image.open(curr_page_img_path) as curr_image:
            curr_width, curr_height = curr_image.size

        curr_image_token = calculate_image_tokens(
            curr_width, curr_height, patch_size=_patch_size, merge_size=_merge_size
        )
        curr_image_token += len(
            _local_processor.tokenizer.encode(
                item_template.format(doc_id=new_row["global_id"], page_id=page_id), add_special_tokens=False
            )
        )
        image_info_list.append(
            {
                "url": curr_page_img_path,
                "width": curr_width,
                "height": curr_height,
                "image_token": curr_image_token,
                "page_id": page_id,
            }
        )

    approx_prompt_count += sum([item["image_token"] for item in image_info_list])
    start_idx, end_idx = 0, len(image_info_list) - 1
    core_image_idx_list = new_row["qa_page_idx_list"]
    start_bound, end_bound = min(core_image_idx_list), max(core_image_idx_list)

    while approx_prompt_count > MAX_TOKEN_CNT:
        is_start_core = start_idx >= start_bound
        is_end_core = end_idx <= end_bound

        # If both sides are core, we can't delete anymore (stop to avoid breaking QA)
        if is_start_core and is_end_core:
            print(
                f"Warning: Cannot truncate further for {new_row['global_id']}, only core pages remain. Current tokens: {approx_prompt_count}"
            )
            break

        # --- Try Delete Left ---
        if not is_start_core:
            approx_prompt_count -= image_info_list[start_idx]["image_token"]
            start_idx += 1
            if approx_prompt_count <= MAX_TOKEN_CNT:
                break

        # --- Try Delete Right ---
        # Check start_idx <= end_idx to ensure we don't cross over if list is empty
        if not is_end_core:
            approx_prompt_count -= image_info_list[end_idx]["image_token"]
            end_idx -= 1

    # 5. Slice the list to keep only the remaining pages
    final_image_list = image_info_list[start_idx : end_idx + 1]
    return final_image_list


def build_llava_format_data(task_args):
    file_path, output_path, row_group_size, add_cot = task_args

    quality_filtered_count = 0
    pos = mp.current_process()._identity[0] if mp.current_process()._identity else 0

    with open(file_path, "r") as fin:
        json_list = [json.loads(line) for line in fin]

    processed_data_list = []
    for row in tqdm(
        json_list, desc=f"Proc {pos:02d} | LLaVA formatting", position=pos, disable=(pos > 3), unit="example"
    ):
        # preprocess: remove examples by page count
        if row["page_count"] < MIN_PAGE_CNT or row["page_count"] > MAX_PAGE_CNT:
            quality_filtered_count += 1
            print(
                f"Page count {row['page_count']} out of range [{MIN_PAGE_CNT}, {MAX_PAGE_CNT}] for row {row['global_id']}"
            )
            continue

        new_row = row.copy()
        # 1. parse the api output
        try:
            parser_result = parse_qa_pair_output(row["qa_content"])
            new_row["qa_evidence_description"] = parser_result["qa_evidence_description"]
            new_row["qa_json"] = parser_result["qa_json"]
        except Exception as e:
            quality_filtered_count += 1
            print(f"Error parsing row {new_row['global_id']}: {e}")
            continue

        try:
            # 2. prepare question, answer, image_list, context
            question, answer = new_row["qa_json"]["question"], new_row["qa_json"]["answer"]
            if add_cot:
                answer = new_row["qa_evidence_description"] + "\n In summary, the answer is " + answer

            final_page_img_list = truncate_doc_image_list(new_row, add_cot)
            final_page_idx_list = [item["page_id"] for item in final_page_img_list]

            page_prompt_list = [
                item_template.format(doc_id=new_row["global_id"], page_id=page_id) for page_id in final_page_idx_list
            ]
            context = "\n\n".join(page_prompt_list)

            full_prompt = user_template.format(question=question, context=context)

            chat_format_prompt = [
                {"role": "user", "content": format_chat(full_prompt, final_page_img_list)},
                {"role": "assistant", "content": [{"type": "text", "text": system_template + " " + answer}]},
            ]

            row_token_count = compute_prompt_length(
                chat_format_prompt, _local_processor.tokenizer, _patch_size, _merge_size
            )
            new_row["token_count"] = row_token_count

            if new_row["token_count"] < MIN_TOKEN_CNT or new_row["token_count"] > MAX_TOKEN_CNT:
                raise ValueError(
                    f"Token count {row_token_count} out of range [{MIN_TOKEN_CNT}, {MAX_TOKEN_CNT}] for row {new_row['global_id']}"
                )
        except Exception as e:
            quality_filtered_count += 1
            print(f"Error processing row {new_row['global_id']}: {e}")
            continue

        try:
            save_row = convert_to_llava_format(new_row, chat_format_prompt)
        except Exception as e:
            quality_filtered_count += 1
            print(f"Error converting row to llava format: {e}")
            continue

        # reformat qa_json to str
        save_row["qa_json"] = json.dumps(new_row["qa_json"], ensure_ascii=False)
        processed_data_list.append(save_row)

    if processed_data_list:
        save_df = pd.DataFrame(processed_data_list)
        table = pa.Table.from_pandas(save_df, preserve_index=False)
        writer = pq.ParquetWriter(
            output_path,
            table.schema,
            compression="NONE",
            use_dictionary=False,
            write_batch_size=1,
            write_page_index=True,
        )
        writer.write_table(table, row_group_size=row_group_size)
        writer.close()

    return quality_filtered_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_dir",
        type=str,
        default="/path/to/hdfs_root/LongVLM_data/long_vqa_data_144dpi_all/tmp_extract_multi_page",
    )
    parser.add_argument("--question_type", type=str, default="extract")  # extract math
    parser.add_argument("--page_flag", type=str, default="multi_page")  # single_page multi_page all_page
    parser.add_argument("--add_cot", type=ast.literal_eval, choices=[True, False], default=False)
    parser.add_argument("--output_file_subdir", type=str, default="veomni/extract_multi_page_no_cot_v1")

    parser.add_argument("--output_dir", type=str, default="/path/to/hdfs_root/LongVLM_data/long_vqa_data_144dpi_all")
    parser.add_argument("--num_proc", type=int, default=32)
    parser.add_argument("--row_group_size", type=int, default=20)
    parser.add_argument("--min_K_length", type=int, default=32)
    parser.add_argument("--max_K_length", type=int, default=124)
    parser.add_argument("--min_page", type=int, default=50)
    parser.add_argument("--max_page", type=int, default=100)
    parser.add_argument("--max_parquet_cnt", type=int, default=120)
    parser.add_argument("--processor_name", type=str, default="Qwen/Qwen2.5-VL-7B-Instruct")
    args = parser.parse_args()

    args.output_file_subdir = (
        f"min{args.min_page}max{args.max_page}-" + args.output_file_subdir + f"-par{args.max_parquet_cnt}"
    )
    args.output_dir = os.path.join(args.output_dir, args.output_file_subdir)
    AutoProcessor.from_pretrained(args.processor_name)

    assert args.output_dir != args.input_dir
    os.makedirs(args.output_dir, exist_ok=True)

    json_list = [file for file in os.listdir(args.input_dir) if file.endswith(".json")]

    # filter json by parquet cnt
    json_list = [file for file in json_list if int(file.split("_")[0].split("-")[-1]) < args.max_parquet_cnt]
    json_list = sorted(
        json_list, key=lambda x: (int(x.split("_")[0].split("-")[-1]), int(x.split("group")[1].split(".")[0]))
    )

    # filter doc by page length
    new_json_list = []
    for file in json_list:
        match = re.search(r"min(\d+)max(\d+)", file)
        if match:
            min_page = int(match.group(1))
            max_page = int(match.group(2))
            if min_page <= args.max_page and max_page >= args.min_page:
                new_json_list.append(file)
        else:
            raise ValueError(f"Invalid file name {file}")
    json_list = new_json_list

    json_list = [os.path.join(args.input_dir, file) for file in json_list]

    print(f"🚀 [Config] Total JSON files: {len(json_list)}")

    tasks = []
    for file in json_list:
        file_name = os.path.basename(file).replace(".json", ".parquet")
        tasks.append((file, os.path.join(args.output_dir, file_name), args.row_group_size, args.add_cot))

    with mp.Pool(
        processes=args.num_proc,
        initializer=worker_init,
        initargs=(
            args.min_K_length,
            args.max_K_length,
            args.min_page,
            args.max_page,
            args.processor_name,
            args.question_type,
            args.page_flag,
        ),
    ) as pool:
        results = list(
            tqdm(
                pool.imap_unordered(build_llava_format_data, tasks),
                total=len(tasks),
                desc=f"Llava Format | Parallel processing {len(json_list)} json files with {args.num_proc} processes",
                position=0,
            )
        )

    print(f"🚀 [Summary] Quality filtered count: {sum(results)}")
    print(results)

import json
import re


image_special_token = "<special_image_token_12345>"
user_template = "You are given a document with text and images, and a question. Answer the question as concisely as you can, using a single phrase or sentence if possible. If the question cannot be answered based on the information in the article, write 'Not answerable.' Write your answer in the following format:\nAnswer: [answer]\n\n{context}\n\nQuestion: {question}"
item_template = "Document {doc_id:.15} (page {page_id}): " + image_special_token
system_template = "Answer:"


def parse_qa_pair_output(model_output):
    result = {
        "qa_evidence_description": None,
        "qa_json": None,
    }

    # 匹配: [JSON]:, ### JSON, ### Part 2: JSON Output, **JSON**, JSON: (忽略大小写)
    json_header_pattern = (
        r"(?:^|\n)\s*(?:[#*]+\s*)?(?:\[\s*)?(?:Part\s*\d+[:.]?\s*)?JSON(?:\s*Output)?(?:\]\s*)?\**[:]?"
    )
    # 匹配: [Evidence Description]:, ### Part 1: Evidence Description, ### Evidence Description
    evidence_header_pattern = (
        r"(?:^|\n)\s*(?:[#*]+\s*)?(?:\[\s*)?(?:Part\s*\d+[:.]?\s*)?Evidence(?:\s*Description)?(?:\]\s*)?\**[:]?"
    )

    # 2. locate the start of JSON part
    json_match = re.search(json_header_pattern, model_output, re.IGNORECASE)

    json_text_segment = ""
    evidence_text_segment = ""

    if json_match:
        start_of_json_header = json_match.start()
        end_of_json_header = json_match.end()

        evidence_text_segment = model_output[:start_of_json_header].strip()
        json_text_segment = model_output[end_of_json_header:].strip()
    else:
        print(f"警告: 未找到明确的 JSON 分隔符，尝试全文解析, 输入文本: {model_output}")
        evidence_text_segment = model_output
        json_text_segment = model_output

    # 3. cut Evidence Description
    if evidence_text_segment:
        # remove header
        ev_header_match = re.search(evidence_header_pattern, evidence_text_segment, re.IGNORECASE)
        if ev_header_match:
            evidence_text_segment = evidence_text_segment[ev_header_match.end() :].strip()

        # remove markdown separator (like ---, ***)
        evidence_text_segment = re.sub(r"\n\s*[-*_]{3,}\s*$", "", evidence_text_segment).strip()

        result["qa_evidence_description"] = evidence_text_segment

    # 4. parse JSON
    # remove markdown code: ```json ... ```
    json_text_segment = re.sub(r"^```[a-zA-Z]*\s*", "", json_text_segment)  # remove the starting ```json
    json_text_segment = re.sub(r"\s*```$", "", json_text_segment)  # remove the ending ```

    result["qa_json"] = robust_json_extraction(
        json_text_segment, ["question", "answer", "answer_format", "evidence_pages", "evidence_sources"]
    )

    # must have keys: question, answer
    if result["qa_evidence_description"] is None or result["qa_json"] is None:
        raise ValueError(f"必须包含 Evidence Description 和 JSON 字段, 输入文本: {model_output}")

    if not isinstance(result["qa_evidence_description"], str):
        raise ValueError(f"Evidence Description 必须是字符串类型, 输入文本: {model_output}")

    if result["qa_json"]["question"] is None or result["qa_json"]["answer"] is None:
        raise ValueError(f"API未提供有效答案, 输入文本: {model_output}")
    if (
        result["qa_json"]["answer_format"] is None
        or result["qa_json"]["evidence_pages"] is None
        or result["qa_json"]["evidence_sources"] is None
    ):
        raise ValueError(f"API未提供有效答案, 输入文本: {model_output}")

    if not isinstance(result["qa_json"]["question"], str):
        raise ValueError(f"JSON 中的 question 必须是非空字符串类型, 输入文本: {model_output}")

    result["qa_json"]["answer"] = str(result["qa_json"]["answer"])
    return result


def clean_latex_escape(text):
    text = re.sub(r"(?<!\\)\\([a-zA-Z]{2,})", r"\\\\\1", text)
    return text


def robust_json_extraction(text, key_list=None):
    text = clean_latex_escape(text)

    start_index = text.find("{")
    if start_index != -1:
        try:
            decoder = json.JSONDecoder()
            obj, _ = decoder.raw_decode(text, idx=start_index)
            return obj
        except json.JSONDecodeError as e:
            print(f"标准JSON解析失败: {e}, \n 输入文本: {text} 尝试正则提取字段...")

    extracted_data = {}
    print(f"正在尝试正则提取以下字段: {key_list}")

    for key in key_list:
        # 1. "key" \s* : \s*  -> 匹配键和冒号
        # 2. 捕获组 (...):
        #    a. "(?:[^"\\]|\\.)*"  -> 匹配双引号字符串 (修复了你的笔误，支持转义字符)
        #    b. -?\d+(?:\.\d+)?    -> 匹配数字
        #    c. true|false|null    -> 匹配字面量
        #    d. \[.*?\]|\{.*?\}    -> 简单匹配数组/对象 (非递归，不支持嵌套太深)
        pattern = rf'"{re.escape(key)}"\s*:\s*("(?:[^"\\]|\\.)*"|-?\d+(?:\.\d+)?|true|false|null|\[.*?\]|\{{.*?\}})'

        match = re.search(pattern, text, re.DOTALL)

        if match:
            value_str = match.group(1)
            try:
                extracted_data[key] = json.loads(value_str)
            except json.JSONDecodeError:
                extracted_data[key] = None
                # try:
                #     import ast
                #     extracted_data[key] = ast.literal_eval(value_str)
                # except:
                #     extracted_data[key] = None
        else:
            extracted_data[key] = None

    return extracted_data


if __name__ == "__main__":
    test_text = """{"question": "What method did the Utah Symphony use to complete Step 2 of the shared value finding process, and what are the components of this method?", "answer": "['Structured \\'Values\\' Interviews using the Zaltman Metaphor Elicitation Technique (ZMET)', 'Storytelling', 'Missing Pictures', 'Triad Task', 'Sensory Metaphors', 'Additional Probing Techniques']", "answer_format": "List", "evidence_pages": [22, 23, 25, 27], "evidence_sources": ["Layout", "Text"]}"""
    result = robust_json_extraction(
        test_text, ["question", "answer", "answer_format", "evidence_pages", "evidence_sources"]
    )
    print(result)

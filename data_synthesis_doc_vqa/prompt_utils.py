QA_GENERATION_PROMPT_TEMPLATE = """
[System]
You are an expert in synthesizing document question-answering dialogue. In this task, I will provide you the images of one or more sections from a document and you need to generate a question-answering pair based on the given sections.
You need to notice the following key points:

[Task Definition & Requirements]
The current document QA task is {detailed_task_description}

[General Restrictions]
Only include questions that have definite answers, that is:
- Questions must be confidently answerable and document-dependent, relying solely on the provided visual content without external knowledge.
- If the question asks about missing information, the absence of such content must be definitively verifiable from the provided image.
- Scope Constraint: Frame questions specifically within the scope of the provided section/pages, strictly avoiding broad references like "across the document" or "the whole file."
- Page Indexing Rule: When writing the evidence description or the "evidence_pages" field in JSON, strictly use the index provided in the prompt (e.g., use `10` for "Page 10"), regardless of the page number inside images. {extra_page_restriction}

[Response Format]
Please generate the response in two parts:

Part 1: Evidence Description
Provide a detailed description first, citing specific text or visual elements (using the four evidence types defined below) to support your reasoning. You may use multiple paragraphs if necessary.

When describing evidence, explicitly categorize the text and visual elements into one of the following four types:
- Text: pure texts, such as paragraphs.
- Layout: text elements with special layout meaning (generalized text), such as titles, headers, footers, table names, and figure names.
- Figure: including charts and general images.
- Table: structured data in rows and columns.

Part 2: JSON Output
Provide the final question, answer, and metadata in a strict JSON format.

Your answer must strictly fall into one of the following four categories. You must also indicate the type in the JSON output:
1. String: General text, names, short sentences, or short phrases found in the document.
   - Example: "John Doe", "Financial Report", "The project was completed on time."
2. Integer: Whole numbers representing counts, years, page numbers, etc.
   - Example: "42", "2023", "100".
3. Float: Numbers with decimal points, including currency, percentages, or scientific measurements.
   - Example: "12.5", "$45.20", "98.5%".
4. List: A collection of multiple items, names, or values.
   - Example: ["Apple", "Banana", "Orange"], ["Item A", "Item B"].

Your output format is:
[Evidence Description]:
[JSON]:
{{"question": <question>, "answer": <answer>, "answer_format": <answer_format>, "evidence_pages": [<page_index>], "evidence_sources": [<evidence_sources>]}}

{few_qa_examples}

[Current Case]
The following images represent pages {start_page} to {end_page} of the document. Generate the question-answering pair strictly based on the visual content below, ensuring the question scope is limited to phrases like "the Introduction section", "Pages 20, 21, and 25", or "Page 10".
{current_case_image_sequence}
"""

exemplar_prompt_template = """[Exemplar {exemplar_index}]
[Evidence Description]: {detailed_evidences}
[JSON]:
{json_dump_str}"""

# question_type specific prompt template


# extract
extract_prompt_template_dict = {
    "detailed_task_description": "information extraction. You need to generate questions that focus on extracting specific, explicit information directly from the provided document images. Your objective is to create questions that ask for precise facts, entities (such as names, dates, locations, or authors), numerical values, lists of items, or specific steps in a procedure. The answers must be visually present and directly retrievable from the text, tables, or layout elements.",
    "single_page_exemplar_file": "/path/to/workspace/pdf_data/longdocurl_data/LongDocURL_exemplar_extract_single_page.jsonl",
    "multi_page_exemplar_file": "/path/to/workspace/pdf_data/longdocurl_data/LongDocURL_exemplar_extract_multi_page.jsonl",
    "extra_multi_page_restriction": "\n- Multi-Page Priority: When multiple pages are provided, **prioritize** generating questions that require synthesizing information across different pages (>= 2 pages). For example, link a table header from one page to a row on the next, or aggregate data points scattered across multiple pages. You can also come up with other formats of multi-page questions. **Only fall back to single-page questions if no meaningful cross-page connections exist.**",
    "extra_single_page_restriction": "\n- Single-Page Focus: Although multiple pages are provided for context, you must generate a question that is **strictly self-contained within a single page**. Select one specific page from the provided sequence and generate a question based solely on its content. The answer must be fully derivable from that single page without requiring cross-referencing or synthesizing information from other pages.",
}

# reasoning
math_prompt_template_dict = {
    "detailed_task_description": "quantitative reasoning. You need to generate questions that require performing calculation, comparison, or counting. Your objective is to create questions involving one of the following: 1. Calculate: Performing arithmetic operations on data found in the document. 2. Compare: Comparing values to identify trends, maximums, minimums, or relative sizes. 3. Count: Counting the frequency of specific items, keywords, or visual elements that satisfy a condition. \nThe answer must require the aforementioned processing step rather than being directly visible as a single contiguous string.",
    "all_page_exemplar_file": "/path/to/workspace/pdf_data/longdocurl_data/LongDocURL_exemplar_math_all_page.jsonl",
    "extra_all_page_restriction": '\n- Non-Trivial Synthesis: The question must require **aggregating multiple data points**. For example, ask "What is the difference in revenue between Q1 and Q2?" or "Calculate the total sum of items listed in Table 3." The key is that the user must find at least two pieces of information and combine them to get the answer.',
}

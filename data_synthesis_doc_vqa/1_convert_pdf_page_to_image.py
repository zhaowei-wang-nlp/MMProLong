import argparse
import math
import multiprocessing as mp
import os
import sys

import fitz
import pyarrow.parquet as pq
from tqdm import tqdm
from utils import listdir


DPI = None  # NO Default value

# support 10 million pixels at most
MAX_PIXEL = 10_000_000


def init_worker(dpi):
    global DPI
    DPI = dpi


def atomic_save(pixel_file, image_path):
    image_path_name, image_path_ext = os.path.splitext(image_path)
    tmp_image_path = image_path_name + ".tmp" + image_path_ext

    if os.path.exists(image_path):
        # if exists, check file size > 0
        if os.path.getsize(image_path) > 0:
            return
        else:
            os.remove(image_path)  # otherwise, the file is broken

    # 2. clean up tmp file
    if os.path.exists(tmp_image_path):
        os.remove(tmp_image_path)

    # 3. save the pixel to tmp_image_path
    try:
        pixel_file.save(tmp_image_path)
        # 4. rename tmp file to output path if saved it successfully
        os.rename(tmp_image_path, image_path)

    except Exception as e:
        if os.path.exists(tmp_image_path):
            os.remove(tmp_image_path)
        tqdm.write(f" [ERROR] Save failed: {image_path} | Reason: {e}")


def get_effective_dpi(page):
    rect = page.rect
    width_pixel = rect.width / 72 * DPI
    height_pixel = rect.height / 72 * DPI

    effective_dpi = DPI

    current_area = width_pixel * height_pixel
    if current_area > MAX_PIXEL:
        scale_factor = math.sqrt(MAX_PIXEL / current_area) * 0.99  # slightly smaller, in case get_pixmap uses ceil
        effective_dpi = max(1, int(DPI * scale_factor))
        # print(f"警告: 原始 DPI ({DPI}) 会导致超大图片。动态调整 DPI 为: {effective_dpi}")
        # tqdm.write(f" [RESIZE] {os.path.basename(pdf_path)} -> {effective_dpi} DPI")
    return effective_dpi


def convert_pdf_to_images(task_args):
    pdf_path_temp, image_path_temp, page_count = task_args

    for page_id in range(page_count):
        pdf_path = pdf_path_temp.format(page_id=page_id)
        image_path = image_path_temp.format(page_id=page_id)
        if os.path.exists(image_path) and os.path.getsize(image_path) > 0:
            continue
        try:
            with fitz.open(pdf_path) as pdf:
                assert pdf.page_count == 1, f"page_pdf has more than one page: {pdf_path}"
                page = pdf[0]

                effective_dpi = get_effective_dpi(page)
                pix = page.get_pixmap(dpi=effective_dpi)
                atomic_save(pix, image_path)
        except Exception as e:
            tqdm.write(f" [ERROR] Convert failed: {pdf_path} | Reason: {e}")


def get_pdf2img_pair_list(task_args):
    file_path, pdf_pool, image_pool = task_args

    parquet_file_obj = pq.ParquetFile(file_path)
    num_row_groups = parquet_file_obj.num_row_groups
    pos = mp.current_process()._identity[0] if mp.current_process()._identity else 0

    total_rows = parquet_file_obj.metadata.num_rows
    pdf2img_pair_list = []
    with tqdm(
        total=total_rows,
        desc=f"Proc {pos:02d} | Streaming {os.path.basename(file_path)}",
        position=pos,
        disable=(pos > 3),
        unit="pdf",
        mininterval=0.5,
    ) as pbar:
        for i in range(num_row_groups):
            chunk_df = parquet_file_obj.read_row_group(i, columns=["source", "id", "page_count"]).to_pandas()

            for _, row in chunk_df.iterrows():
                row_source, row_id, page_count = row["source"], row["id"], row["page_count"]
                row_global_id = f"{row_source}__{row_id}"

                pdf_page_path = os.path.join(pdf_pool, row_source, row_id[:1], f"{row_global_id}_page{{page_id}}.pdf")
                img_page_path = os.path.join(
                    image_pool, row_source, row_id[:1], f"{row_global_id}_page{{page_id}}.png"
                )

                pdf2img_pair_list.append((pdf_page_path, img_page_path, page_count))
                pbar.update(1)

    sys.stdout.flush()
    return pdf2img_pair_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input_dir", type=str, default="/path/to/hdfs_root/LongVLM_data/long_doc_sample_min32page_max49page_en/data"
    )
    parser.add_argument("--num_proc", type=int, default=128)
    parser.add_argument("--pdf_pool", type=str, default="/path/to/workspace/pdf_data/pdf_pool")
    parser.add_argument("--image_dir", type=str, default="/path/to/workspace/pdf_data/pdf_pool_img")
    parser.add_argument("--dpi", type=int, default=144)
    parser.add_argument("--start_idx", type=int, default=None)
    parser.add_argument("--end_idx", type=int, default=None)
    args = parser.parse_args()

    parquet_list = [file for file in listdir(args.input_dir) if file.endswith(".parquet")]
    parquet_list = sorted(parquet_list)

    args.image_dir += f"_{args.dpi}dpi"
    os.makedirs(args.image_dir, exist_ok=True)

    tasks = [(file, args.pdf_pool, args.image_dir) for file in parquet_list]

    print(f"🚀 [Config] Total Parquet files: {len(tasks)}")
    print(f"🚀 [Config] Slicing range: [{args.start_idx}:{args.end_idx}]")

    all_pdf2img_pair_list = []
    for t in tasks[args.start_idx : args.end_idx]:
        curr_pdf2img_pair_list = get_pdf2img_pair_list(t)
        all_pdf2img_pair_list.extend(curr_pdf2img_pair_list)

    # first make the dirs for images
    image_source_dir_list = list({os.path.dirname(path_pair[1]) for path_pair in all_pdf2img_pair_list})
    for source_dir in tqdm(image_source_dir_list, desc="Create source dir for images"):
        os.makedirs(source_dir, exist_ok=True)

    # init_worker(args.dpi)
    # for p in tqdm(all_pdf2img_pair_list, desc="Converting pdf pages to images", ):
    #     convert_pdf_to_images(p)

    with mp.Pool(processes=args.num_proc, initializer=init_worker, initargs=(args.dpi,)) as pool:
        list(
            tqdm(
                pool.imap_unordered(convert_pdf_to_images, all_pdf2img_pair_list),
                total=len(all_pdf2img_pair_list),
                desc=f"Parallel converting {len(all_pdf2img_pair_list)} pdf pages to images with {args.num_proc} processes",
                position=0,
                mininterval=0.5,
            )
        )

    print("\n" * 2, flush=True)
    print("✨ 所有PDF转换任务已完成！")

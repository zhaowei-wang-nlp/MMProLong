"""A local, periodically refreshed progress page; no external resources."""

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo


def write_progress(root, status, policy):
    labels = {
        "single": "Single needle",
        "multi_local": "Local multi",
        "multi_distributed": "Distributed multi",
        "reasoning": "Reasoning",
        "unanswerable": "Unanswerable",
    }
    phases = {
        "batch_committed": "本批已入账",
        "exports_rebuilt": "训练引用已重新导出",
        "discovering_sources": "查找不同领域的公开文档",
        "source_candidates_added": "候选文档已加入队列",
        "checking_source": "检查文档许可与长度",
        "source_selected": "文档已进入本批",
        "generating_batch": "生成与全文复核",
        "ready_for_next_batch": "准备下一批",
        "paused_disk_reserve": "已在磁盘预留线前暂停",
        "target_reached": "已完成本次制作",
        "batch_limit_reached": "验证批次已完成",
        "source_search_failed": "部分检索失败，重试或切换来源",
        "source_request_failed": "跳过未成功获取的来源",
        "source_discovery_exhausted": "候选来源暂时不足，任务已停止",
        "stopped_error": "运行停止，需检查日志",
        "stopped_source_network": "来源网络连续失败，已保留队列等待续跑",
        "stopped_batch_without_accepted_data": "本批没有合格样本，需检查结果",
    }
    fraction = status["accepted_tokens"] / status["target_tokens"]
    updated = datetime.fromtimestamp(status["updated_at_unix"], ZoneInfo("Asia/Shanghai")).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    rows = ""
    for key, weight in policy["token_fractions"].items():
        count = status["by_kind"].get(key, {}).get("samples", 0)
        tokens = status["by_kind"].get(key, {}).get("tokens", 0)
        rows += f"<tr><th>{labels[key]}</th><td>{weight:.0%}</td><td>{count:,}</td><td>{tokens:,}</td><td>{int(weight * status['target_tokens']):,}</td></tr>"
    current = escape(
        str(status.get("document_id") or status.get("arxiv_id") or status.get("query") or status.get("batch") or "")
    )
    page = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="30"><title>MMProLong-Data-Public · 制作进度</title>
<style>body{{margin:0;background:#f6f7f9;color:#192b39;font:15px/1.7 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}main{{max-width:1040px;margin:50px auto;padding:0 24px}}h1{{font-size:28px;margin:0 0 8px}}h2{{font-size:18px}}.muted{{color:#667685;font-size:13px}}.top{{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap}}.metric{{font-size:36px;color:#087d77;font-weight:600}}.track{{height:10px;background:#dfe6eb;border-radius:8px;overflow:hidden;margin:18px 0 9px}}.fill{{height:100%;background:#087d77;min-width:2px}}.status{{background:white;padding:20px 24px;border:1px solid #e1e7ec;border-radius:9px;margin:25px 0}}table{{width:100%;border-collapse:collapse;font-size:13px}}th,td{{text-align:right;padding:13px 8px;border-bottom:1px solid #e1e7ec;font-variant-numeric:tabular-nums}}th:first-child{{text-align:left}}a{{color:#087d77}}.scroll{{overflow:auto}}code{{font-size:12px}}@media(max-width:600px){{main{{margin:25px auto;padding:0 16px}}.metric{{font-size:27px}}}}</style>
<main><p class="muted">MMProLong · Public corpus</p><div class="top"><div><h1>长文数据制作</h1><p>按合格样本的 token 累计，图片按文档共享存储。</p></div><div><div class="metric">{status["accepted_tokens"] / 1e9:.4f} / {policy["target_tokens"] / 1e9:g}B</div><p class="muted">{status["accepted_samples"]:,} 条样本 · {fraction:.3%}</p></div></div>
<div class="track"><div class="fill" style="width:{fraction * 100:.5f}%"></div></div><p class="muted">还需约 {status["remaining_tokens"] / 1e9:.4f}B tokens · token 计数含页面图像</p>
<div class="status"><strong>{phases.get(status["phase"], escape(status["phase"]))}</strong><div class="muted">{current}</div><p class="muted">最后更新：{updated}（北京时间）</p><p>当前磁盘可用 <b>{status["free_gib"]:.2f} GiB</b>；至少预留 <b>{status["disk_reserve_gib"]} GiB</b>。达到预留线前停止，并保存续跑状态。</p></div>
<h2>各类数据的 token 预算</h2><div class="scroll"><table><thead><tr><th>类别</th><th>目标比例</th><th>已收录条数</th><th>已收录 tokens</th><th>目标 tokens</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="muted">只累计通过当前质量检查、未被版权排除、去重后的样本。自动复核不等同于人工逐条验收；文档许可和图像权利仍保留来源记录。页面约每 30 秒刷新。</p>
<p><a href="corpus.jsonl" download>下载当前问答记录</a> · <a href="status.json">查看状态记录</a> · <a href="../MMProLong-public-100-20261023/index.html">查看 100 条小样浏览器</a></p></main></html>"""
    path = root / "progress.html"
    temporary = root / "progress.html.tmp"
    temporary.write_text(page)
    temporary.replace(path)

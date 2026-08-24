#!/usr/bin/env python3
"""BOSS直聘 抓取 + 摘要 桌面图形界面（tkinter，零额外依赖）。

薄 UI 壳：只负责把界面参数拼成命令行、以子进程调用
``scripts/boss_cdp_raw.py``，抓取正常结束（exit 0）后按勾选自动接跑
``scripts/job_summary.py``。不包含任何抓取/分析逻辑（见 AGENTS.md
单文件原则：核心逻辑仍在 boss_cdp_raw.py）。
"""

from __future__ import annotations

import argparse
import os
import queue
import re
import shlex
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

try:
    from scripts import boss_cdp_raw as boss
except ImportError:  # 直接以脚本方式运行时（工作目录=仓库根目录）
    import boss_cdp_raw as boss


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPT = os.path.join(SCRIPT_DIR, "boss_cdp_raw.py")
SUMMARY_SCRIPT = os.path.join(SCRIPT_DIR, "job_summary.py")
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
DEFAULT_RESULT_DIR = os.path.expanduser(boss.DEFAULT_RESULT_DIR)


# ---------------------------------------------------------------- 命令拼装

def build_scrape_args(
    keyword: str,
    city: str,
    pages: int,
    cdp_port: int = boss.DEFAULT_CDP_PORT,
    fmt: str = "json",
    detail: bool = False,
    analysis: bool = False,
    output: str | None = None,
    detail_output: str | None = None,
    merge: str | None = None,
) -> list[str]:
    """拼 boss_cdp_raw.py 的抓取命令（默认 json、不抓详情，保证尽快跑完）。"""
    args = [
        sys.executable,
        CORE_SCRIPT,
        "--keyword",
        keyword,
        "--city",
        city,
        "--pages",
        str(pages),
        "--cdp-port",
        str(cdp_port),
    ]
    if fmt and fmt.lower() == "csv":
        args += ["--format", "csv"]
    args.append("--detail" if detail else "--no-detail")
    if analysis:
        args.append("--analysis")
    if output:
        args += ["--output", output]
    if detail_output:
        args += ["--detail-output", detail_output]
    if merge:
        args += ["--merge", merge]
    return args


def split_keywords(raw: str) -> list[str]:
    """把用户输入拆成多个关键词：支持英文/中文逗号、分号、换行。"""
    parts = re.split(r"[,，;；\n\r]+", raw or "")
    return [part.strip() for part in parts if part.strip()]


def build_summary_args(
    top: int = 10,
    input_path: str | None = None,
    result_dir: str | None = None,
) -> list[str]:
    """拼 job_summary.py 的摘要命令（默认读最新结果文件并自动匹配详情）。"""
    args = [sys.executable, SUMMARY_SCRIPT, "--top", str(top)]
    if input_path:
        args += ["--input", input_path]
    if result_dir:
        args += ["--result-dir", result_dir]
    return args


def build_multi_keyword_steps(
    keywords: list[str],
    city: str,
    pages: int,
    cdp_port: int = boss.DEFAULT_CDP_PORT,
    fmt: str = "json",
    detail: bool = False,
    analysis: bool = False,
    result_dir: str | None = None,
    timestamp: str | None = None,
):
    """多关键词：逐个抓取，后续关键词用 --merge 合并进同一个结果文件。

    返回 (steps, final_path, part_paths)：
    - steps: [(命令, 显示名), ...]
    - final_path: 最终结果文件（单个/多个关键词都显式指定，摘要直接读它）
    - part_paths: 合并过程的临时分片文件（全部成功后清理）
    """
    result_dir = result_dir or DEFAULT_RESULT_DIR
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M")
    if len(keywords) == 1:
        output = os.path.join(result_dir, f"boss_jobs_{ts}.json")
        detail_output = os.path.join(result_dir, f"boss_details_{ts}.json") if detail else None
        args = build_scrape_args(
            keywords[0], city, pages, cdp_port, fmt, detail, analysis,
            output=output, detail_output=detail_output,
        )
        return [(args, f"抓取 [{keywords[0]}]")], output, []

    final_path = os.path.join(result_dir, f"boss_jobs_{ts}_multi.json")
    steps = []
    part_paths = []
    previous = final_path
    for index, keyword in enumerate(keywords):
        if index == 0:
            detail_output = os.path.join(result_dir, f"boss_details_{ts}_multi.json") if detail else None
            args = build_scrape_args(
                keyword, city, pages, cdp_port, fmt, detail, analysis,
                output=final_path, detail_output=detail_output,
            )
            steps.append((args, f"抓取 [{keyword}]"))
        else:
            part = os.path.join(result_dir, f"boss_jobs_{ts}_multi.part{index}.json")
            part_paths.append(part)
            detail_output = os.path.join(result_dir, f"boss_details_{ts}_multi.part{index}.json") if detail else None
            args = build_scrape_args(
                keyword, city, pages, cdp_port, fmt, detail, analysis,
                output=part, detail_output=detail_output, merge=previous,
            )
            steps.append((args, f"抓取并合并 [{keyword}]"))
            previous = part
    return steps, final_path, part_paths


def build_check_args(cdp_port: int) -> list[str]:
    return [sys.executable, CORE_SCRIPT, "--check", "--cdp-port", str(cdp_port)]


def build_setup_chrome_args(cdp_port: int) -> list[str]:
    # --no-wait-login：GUI 里启动后立即返回，登录由用户在弹出的 Chrome 里完成
    return [
        sys.executable,
        CORE_SCRIPT,
        "--setup-chrome",
        "--cdp-port",
        str(cdp_port),
        "--no-wait-login",
    ]


def build_smoke_args(cdp_port: int) -> list[str]:
    return [sys.executable, CORE_SCRIPT, "--smoke-test", "--cdp-port", str(cdp_port)]


def build_stop_chrome_args(cdp_port: int) -> list[str]:
    return [sys.executable, CORE_SCRIPT, "--stop-chrome", "--cdp-port", str(cdp_port)]


def should_auto_summary(exit_code: int) -> bool:
    """只在抓取成功退出时自动接跑摘要（与 --close-chrome 的成功路径惯例一致）。"""
    return exit_code == 0


def _quote(arg: str) -> str:
    return shlex.quote(arg)


# ---------------------------------------------------------------- 界面

class BossGui:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.proc: subprocess.Popen | None = None
        self.queue: queue.Queue = queue.Queue()
        self.busy = False
        self._scrape_steps: list = []
        self._scrape_index = 0
        self._scrape_final: str | None = None
        self._scrape_parts: list[str] = []
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._poll_queue()

    # ---- 控件 ----
    def _build_ui(self):
        self.root.title(f"BOSS直聘 抓取 + 摘要 v{boss.__version__}")
        self.root.geometry("880x660")
        self.root.minsize(720, 520)

        params = ttk.LabelFrame(self.root, text="抓取参数")
        params.pack(fill="x", padx=10, pady=(10, 4))

        self.keyword_var = tk.StringVar(value="AI Agent")
        self.city_var = tk.StringVar(value="上海")
        self.pages_var = tk.IntVar(value=3)
        self.port_var = tk.IntVar(value=boss.DEFAULT_CDP_PORT)
        self.fmt_var = tk.StringVar(value="json")
        self.detail_var = tk.BooleanVar(value=False)
        self.analysis_var = tk.BooleanVar(value=False)
        self.auto_summary_var = tk.BooleanVar(value=True)
        self.top_var = tk.IntVar(value=10)
        self.result_dir_var = tk.StringVar(value=DEFAULT_RESULT_DIR)

        row1 = ttk.Frame(params)
        row1.pack(fill="x", padx=8, pady=6)
        ttk.Label(row1, text="关键词（多个用 , 或 ; 分隔）").pack(side="left")
        ttk.Entry(row1, textvariable=self.keyword_var, width=26).pack(side="left", padx=(4, 12))
        ttk.Label(row1, text="城市").pack(side="left")
        ttk.Entry(row1, textvariable=self.city_var, width=12).pack(side="left", padx=(4, 12))
        ttk.Label(row1, text="页数 (1-10)").pack(side="left")
        ttk.Spinbox(row1, from_=1, to=10, textvariable=self.pages_var, width=5).pack(side="left", padx=(4, 12))
        ttk.Label(row1, text="CDP 端口").pack(side="left")
        ttk.Entry(row1, textvariable=self.port_var, width=7).pack(side="left", padx=(4, 4))

        row2 = ttk.Frame(params)
        row2.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row2, text="输出格式").pack(side="left")
        ttk.Combobox(
            row2, textvariable=self.fmt_var, values=("json", "csv"),
            state="readonly", width=6,
        ).pack(side="left", padx=(4, 14))
        ttk.Checkbutton(row2, text="抓详情页 (JD，较慢)", variable=self.detail_var).pack(side="left")
        ttk.Checkbutton(row2, text="分析报告", variable=self.analysis_var).pack(side="left", padx=(10, 0))
        ttk.Checkbutton(
            row2, text="抓取完成后自动生成摘要", variable=self.auto_summary_var,
        ).pack(side="left", padx=(16, 10))
        ttk.Label(row2, text="Top").pack(side="left")
        ttk.Spinbox(row2, from_=1, to=50, textvariable=self.top_var, width=4).pack(side="left", padx=(4, 0))

        row3 = ttk.Frame(params)
        row3.pack(fill="x", padx=8, pady=(0, 6))
        ttk.Label(row3, text="结果目录").pack(side="left")
        ttk.Entry(row3, textvariable=self.result_dir_var, width=58).pack(side="left", padx=(4, 6))
        ttk.Button(row3, text="浏览...", command=self._browse_result_dir).pack(side="left")

        actions = ttk.LabelFrame(self.root, text="操作")
        actions.pack(fill="x", padx=10, pady=4)
        buttons = ttk.Frame(actions)
        buttons.pack(fill="x", padx=8, pady=6)
        for text, command in (
            ("环境检查", self._run_check),
            ("启动 Chrome", self._run_setup_chrome),
            ("Smoke 测试", self._run_smoke),
            ("开始抓取", self._run_scrape),
            ("生成摘要", self._run_summary),
            ("关闭 Chrome", self._run_stop_chrome),
            ("停止", self._stop),
        ):
            ttk.Button(buttons, text=text, command=command).pack(side="left", padx=4)

        output_frame = ttk.LabelFrame(self.root, text="输出")
        output_frame.pack(fill="both", expand=True, padx=10, pady=4)
        self.output = scrolledtext.ScrolledText(
            output_frame, wrap="word", state="normal", font=("Consolas", 10),
        )
        self.output.pack(fill="both", expand=True, padx=6, pady=6)
        self.output.tag_configure("ok", foreground="#1a7f37")
        self.output.tag_configure("err", foreground="#b42318")
        self.output.tag_configure("cmd", foreground="#0b57d0")

        self.status_var = tk.StringVar(value="就绪")
        self.status = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        self.status.pack(fill="x", padx=10, pady=(0, 6))

    # ---- 公共 ----
    def _start(self, command: list[str], label: str, chain: bool = False):
        if self.proc and self.proc.poll() is None:
            messagebox.showwarning("任务运行中", "已有任务在运行，请先点「停止」。")
            return
        self._write_line(f"\n$ {' '.join(_quote(arg) for arg in command)}\n", "cmd")
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env["PYTHONUNBUFFERED"] = "1"
        try:
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env,
                creationflags=CREATE_NO_WINDOW,
            )
        except OSError as exc:
            messagebox.showerror("启动失败", str(exc))
            return
        self.proc = proc
        self._set_busy(label)
        threading.Thread(target=self._pump, args=(proc, label, chain), daemon=True).start()

    def _pump(self, proc: subprocess.Popen, label: str, chain: bool):
        try:
            for line in proc.stdout:
                self.queue.put(("out", line))
        except (OSError, ValueError):
            pass
        finally:
            code = proc.wait()
            self.queue.put(("done", code, label, chain))

    def _poll_queue(self):
        try:
            while True:
                item = self.queue.get_nowait()
                kind = item[0]
                if kind == "out":
                    self._write(item[1])
                elif kind == "done":
                    self._handle_done(item[1], item[2], item[3])
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def _handle_done(self, code: int, label: str, chain: bool):
        self.proc = None
        self._set_busy(None)
        ok = code == 0
        self._write_line(
            f"\n[完成] {label} 退出码 {code}（{'成功' if ok else '失败'}）",
            "ok" if ok else "err",
        )
        if chain:
            if should_auto_summary(code) and self._scrape_index < len(self._scrape_steps):
                self._write_line(
                    f"\n继续下一个关键词（{self._scrape_index + 1}/{len(self._scrape_steps)}）...",
                    "ok",
                )
                self._next_scrape_step()
                return
            if should_auto_summary(code):
                self._finalize_multi()
                self._write_line("抓取成功，自动运行摘要脚本 job_summary.py ...", "ok")
                self._start(
                    build_summary_args(
                        self.top_var.get(),
                        input_path=self._scrape_final,
                        result_dir=self.result_dir_var.get().strip() or None,
                    ),
                    "摘要生成",
                    chain=False,
                )
            else:
                self._write_line(
                    "抓取未正常结束，跳过摘要（登录失败/风控/异常退出时不接跑摘要）。",
                    "err",
                )

    def _stop(self):
        proc = self.proc
        if not proc or proc.poll() is not None:
            self._write_line("\n当前没有运行中的任务。")
            return
        self._write_line("\n[停止] 正在终止当前任务...", "err")
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if messagebox.askyesno("任务运行中", "当前任务尚未结束，关闭窗口将终止它。确定退出？"):
                self._stop()
        self.root.destroy()

    # ---- 按钮动作 ----
    def _run_check(self):
        self._start(build_check_args(self._port()), "环境检查", chain=False)

    def _run_setup_chrome(self):
        self._write_line("\n提示：启动后请在弹出的专用 Chrome 中登录 zhipin.com（若已登录则无需操作）。\n")
        self._start(build_setup_chrome_args(self._port()), "启动 Chrome", chain=False)

    def _run_smoke(self):
        self._start(build_smoke_args(self._port()), "Smoke 测试", chain=False)

    def _run_scrape(self):
        keywords = split_keywords(self.keyword_var.get())
        if not keywords:
            messagebox.showerror("参数错误", "请填写至少一个关键词。")
            return
        result_dir = self.result_dir_var.get().strip() or DEFAULT_RESULT_DIR
        try:
            os.makedirs(result_dir, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("目录不可用", f"无法创建结果目录：{exc}")
            return
        try:
            pages = int(self.pages_var.get())
            port = int(self.port_var.get())
        except (TypeError, ValueError):
            messagebox.showerror("参数错误", "页数和端口必须是整数。")
            return
        if not 1 <= pages <= 10:
            messagebox.showerror("参数错误", "页数必须在 1-10 之间。")
            return
        steps, final_path, part_paths = build_multi_keyword_steps(
            keywords=keywords,
            city=self.city_var.get().strip() or "上海",
            pages=pages,
            cdp_port=port,
            fmt=self.fmt_var.get(),
            detail=self.detail_var.get(),
            analysis=self.analysis_var.get(),
            result_dir=result_dir,
        )
        if len(keywords) > 1:
            self._write_line(
                f"\n多关键词模式：{len(keywords)} 个关键词将逐个抓取并自动合并去重。\n",
                "cmd",
            )
        self._scrape_steps = steps
        self._scrape_index = 0
        self._scrape_final = final_path
        self._scrape_parts = part_paths
        self._next_scrape_step()

    def _next_scrape_step(self):
        if not self._scrape_steps or self._scrape_index >= len(self._scrape_steps):
            return
        command, label = self._scrape_steps[self._scrape_index]
        self._scrape_index += 1
        self._start(command, label, chain=True)

    def _finalize_multi(self):
        """把最后一个合并分片改名为最终结果文件，并清理中间分片。"""
        if not self._scrape_parts:
            return
        last = self._scrape_parts[-1]
        if os.path.isfile(last):
            os.replace(last, self._scrape_final)
        for part in self._scrape_parts:
            if part != last and os.path.isfile(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
        self._scrape_parts = []

    def _run_summary(self):
        self._start(
            build_summary_args(
                self.top_var.get(),
                result_dir=self.result_dir_var.get().strip() or None,
            ),
            "摘要生成",
            chain=False,
        )

    def _run_stop_chrome(self):
        self._start(build_stop_chrome_args(self._port()), "关闭 Chrome", chain=False)

    # ---- 小工具 ----
    def _browse_result_dir(self):
        selected = filedialog.askdirectory(
            title="选择结果保存目录",
            initialdir=self.result_dir_var.get().strip() or DEFAULT_RESULT_DIR,
        )
        if selected:
            self.result_dir_var.set(selected)

    def _port(self) -> int:
        try:
            return int(self.port_var.get())
        except (TypeError, ValueError):
            return boss.DEFAULT_CDP_PORT

    def _set_busy(self, label):
        self.busy = label is not None
        self.status_var.set("运行中: " + label if label else "就绪")

    def _write(self, text: str):
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def _write_line(self, text: str, tag: str | None = None):
        self.output.insert(tk.END, text + "\n", tag or "")
        self.output.see(tk.END)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="boss-gui",
        description="BOSS直聘 抓取 + 摘要 桌面图形界面",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {boss.__version__}")
    parser.parse_args(argv)
    root = tk.Tk()
    BossGui(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())

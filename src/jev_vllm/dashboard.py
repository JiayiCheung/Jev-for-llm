"""Locate paired reports and serve the generated dashboard on localhost."""

import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def discover_reports(analysis_dir):
    """Return the newest baseline/adaptive join and its fixed/adaptive report."""
    analysis_dir = Path(analysis_dir)
    candidates = sorted(
        analysis_dir.glob("*/summary.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for summary_path in candidates:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        adaptive_id = summary.get("adaptive_id")
        joined = summary_path.parent
        if not adaptive_id or not (joined / "pairs.csv").is_file():
            continue
        for pairs_path in analysis_dir.glob("*/pairs.csv"):
            if pairs_path.parent == joined:
                continue
            with pairs_path.open(encoding="utf-8-sig", newline="") as stream:
                first = next(csv.DictReader(stream), None)
            if first and first.get("experiment_id") == adaptive_id and first.get("status") == "paired":
                return joined, pairs_path.parent, adaptive_id
    raise ValueError(
        f"No matching paired baseline/adaptive and fixed/adaptive reports under {analysis_dir}. "
        "Build both reports first, or specify --baseline-compare-dir and --fixed-compare-dir."
    )


def discover_experiments(analysis_dir, manifests_dir=None, auto_reports_dir=None):
    """Find analyzed batches without mixing records from different IDs."""
    manifests_dir = Path(manifests_dir or Path(analysis_dir).parent / "experiments")
    found = {}
    manual_paths = (path for path in Path(analysis_dir).glob("*/runs.csv")
                    if not path.parent.name.startswith("auto-"))
    auto_paths = Path(auto_reports_dir).glob("*/runs.csv") if auto_reports_dir else ()
    for csv_path in (*manual_paths, *auto_paths):
        with csv_path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        ids = {row.get("experiment_id") for row in rows if row.get("experiment_id")}
        if len(ids) != 1:
            continue
        batch_id = next(iter(ids))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", batch_id):
            continue
        created = csv_path.stat().st_mtime
        manifest_path = manifests_dir / f"{batch_id}.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("created_utc"):
                created = datetime.fromisoformat(manifest["created_utc"].replace("Z", "+00:00")).timestamp()
        modes = sorted({row.get("mode") for row in rows if row.get("mode")})
        if not modes or not set(modes) <= {"baseline", "fixed", "adaptive"}:
            continue
        entry = {"id": batch_id, "modes": modes, "report": csv_path.parent,
                 "tasks": len({row.get("task_id") for row in rows if row.get("task_id")}),
                 "runs": len(rows), "completed": sum(row.get("status") == "completed" for row in rows),
                 "mtime": csv_path.stat().st_mtime, "created": created,
                 "automatic": auto_reports_dir is not None and csv_path.parent.parent == Path(auto_reports_dir)}
        if batch_id not in found or (entry["automatic"], entry["mtime"]) > (found[batch_id]["automatic"], found[batch_id]["mtime"]):
            found[batch_id] = entry
    return sorted(found.values(), key=lambda entry: (entry["created"], entry["id"]))


def prepare_auto_reports(repo_root, dashboard_dir):
    """Incrementally index saved results once, then split by batch ID."""
    outputs = repo_root / "outputs"
    index_dir = dashboard_dir / "index"
    indexed_csv = index_dir / "runs.csv"
    indexed_mtime = indexed_csv.stat().st_mtime if indexed_csv.is_file() else -1
    changed = indexed_mtime < 0 or (repo_root / "scripts" / "analyze_results.py").stat().st_mtime > indexed_mtime or any(
        path.stat().st_mtime > indexed_mtime
        for path in outputs.rglob("result.json")
    )
    if not changed:
        return
    print("Indexing saved experiment results...", flush=True)
    subprocess.run([sys.executable, str(repo_root / "scripts" / "analyze_results.py"),
                    "--outputs", str(outputs), "--report-dir", str(index_dir)], check=True,
                   stdout=subprocess.DEVNULL)
    for name in ("runs", "pairs"):
        with (index_dir / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            groups = {}
            for row in reader:
                batch_id = row.get("experiment_id")
                if batch_id:
                    groups.setdefault(batch_id, []).append(row)
        for batch_id, rows in groups.items():
            slug = hashlib.sha256(batch_id.encode()).hexdigest()[:20]
            report_dir = dashboard_dir / "reports" / slug
            report_dir.mkdir(parents=True, exist_ok=True)
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
            target = report_dir / f"{name}.csv"
            contents = buffer.getvalue()
            if not target.is_file() or target.read_text(encoding="utf-8") != contents:
                target.write_text(contents, encoding="utf-8")


def build_catalog(repo_root, analysis_dir, output_dir):
    """Build separate lazy-loaded pages for every analyzed experiment."""
    experiments = discover_experiments(analysis_dir, repo_root / "outputs" / "experiments",
                                       output_dir / "reports")
    if not experiments:
        raise ValueError(f"No analyzed experiments under {analysis_dir}. Run scripts/analyze_results.py for a batch first.")
    joins = {}
    summaries = sorted(Path(analysis_dir).glob("*/summary.json"),
                       key=lambda path: path.stat().st_mtime, reverse=True)
    for summary_path in summaries:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        adaptive_id = summary.get("adaptive_id")
        if adaptive_id and (summary_path.parent / "pairs.csv").is_file():
            joins.setdefault(adaptive_id, summary_path.parent)
    output_dir.mkdir(parents=True, exist_ok=True)
    cards = []
    for experiment in experiments:
        batch_id = experiment["id"]
        slug = hashlib.sha256(batch_id.encode()).hexdigest()[:20]
        batch_output = output_dir / "batches" / slug
        report = experiment["report"]
        if set(experiment["modes"]) == {"fixed", "adaptive"} and (report / "pairs.csv").is_file():
            command = [sys.executable, str(repo_root / "scripts" / "build_dashboard.py"),
                       "--fixed-compare-dir", str(report), "--output-dir", str(batch_output)]
            if batch_id in joins:
                command += ["--baseline-compare-dir", str(joins[batch_id])]
            kind = "paired"
        elif len(experiment["modes"]) == 1:
            command = [sys.executable, str(repo_root / "scripts" / "build_run_dashboard.py"),
                       "--report-dir", str(report), "--output-dir", str(batch_output)]
            kind = "single"
        else:
            continue
        if kind == "paired":
            with (report / "pairs.csv").open(encoding="utf-8-sig", newline="") as stream:
                paired = sum(row.get("status") == "paired" for row in csv.DictReader(stream))
            if paired == 0:
                continue
        source_paths = [report / "runs.csv", report / "pairs.csv", repo_root / "scripts" / "build_dashboard.py",
                        repo_root / "scripts" / "build_run_dashboard.py",
                        *list((repo_root / "scripts" / "dashboard").glob("*"))]
        if batch_id in joins:
            source_paths.append(joins[batch_id] / "pairs.csv")
        current = batch_output / "index.html"
        if not current.is_file() or not (batch_output / "data" / "overview.js").is_file() or any(path.is_file() and path.stat().st_mtime > current.stat().st_mtime for path in source_paths):
            print(f"Preparing dashboard for {batch_id}...", flush=True)
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
        modes = (["baseline", "fixed", "adaptive"] if batch_id in joins else ["fixed", "adaptive"]) if kind == "paired" else experiment["modes"]
        cards.append({"id": batch_id, "slug": slug, "kind": kind, "modes": modes,
                      "tasks": experiment["tasks"], "runs": experiment["runs"], "completed": experiment["completed"],
                      "created": experiment["created"]})
    if not cards:
        raise ValueError("No completed single-mode or paired experiment results were found")
    payload = "window.JEV_BATCHES = " + json.dumps(
        [{"id": card["id"], "slug": card["slug"], "modes": card["modes"], "tasks": card["tasks"], "created": card["created"]}
         for card in cards], ensure_ascii=False, separators=(",", ":")) + ";\n"
    for card in cards:
        target = output_dir / "batches" / card["slug"] / "data" / "batches.js"
        if not target.is_file() or target.read_text(encoding="utf-8") != payload:
            target.write_text(payload, encoding="utf-8")
    return cards


def launch_dashboard(repo_root, *, baseline_dir=None, fixed_dir=None, output_dir=None,
                     analysis_dir=None, port=0, open_browser=True):
    repo_root = Path(repo_root)
    if (baseline_dir is None) != (fixed_dir is None):
        raise ValueError("Specify both --baseline-compare-dir and --fixed-compare-dir together")
    if baseline_dir is None:
        analysis_dir = Path(analysis_dir or repo_root / "outputs" / "analysis")
        output_dir = Path(output_dir) if output_dir else repo_root / "outputs" / "dashboard"
        prepare_auto_reports(repo_root, output_dir)
        batches = build_catalog(repo_root, analysis_dir, output_dir)
        start_path = f"batches/{batches[0]['slug']}/"
        print(f"Experiment batches available: {len(batches)}", flush=True)
    else:
        baseline_dir, fixed_dir = Path(baseline_dir), Path(fixed_dir)
        adaptive_id = json.loads((baseline_dir / "summary.json").read_text(encoding="utf-8"))["adaptive_id"]
        output_dir = Path(output_dir) if output_dir else repo_root / "outputs" / "dashboard" / "exports" / f"{adaptive_id}-dashboard"
        subprocess.run([
            sys.executable, str(repo_root / "scripts" / "build_dashboard.py"),
            "--baseline-compare-dir", str(baseline_dir),
            "--fixed-compare-dir", str(fixed_dir),
            "--output-dir", str(output_dir),
        ], check=True)
        start_path = ""

    detail_indexes = {}
    for index_path in output_dir.glob("batches/*/data/detail-index.json"):
        detail_indexes[index_path.parents[1].name] = json.loads(index_path.read_text(encoding="utf-8"))

    class DashboardHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(output_dir.resolve()), **kwargs)

        def end_headers(self):
            # The pages are regenerated whenever the dashboard code changes: never serve a stale copy.
            self.send_header("Cache-Control", "no-cache")
            super().end_headers()

        def log_request(self, code="-", size="-"):
            # Only failed requests are worth a line; every page loads dozens of data files.
            if str(code)[:1] in ("4", "5"):
                super().log_request(code, size)

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == "/" and start_path:
                self.send_response(302)
                self.send_header("Location", "/" + start_path)
                self.end_headers()
                return
            match = re.fullmatch(r"/batches/([0-9a-f]{20})/data/tasks/([0-9a-f]{24})\.js", path)
            if match and match.group(1) in detail_indexes:
                item = detail_indexes[match.group(1)].get(match.group(2))
                if item is None:
                    self.send_error(404, "Unknown task")
                    return
                from scripts.build_dashboard import compact_run
                try:
                    record = compact_run(item["path"], item["metrics"], include_task=True)
                    task = record.pop("task")
                    detail = {"task": task.get("prompt", ""),
                              "reference": task.get("reference_answer", task.get("reference", "")),
                              "run": record}
                    payload = ("window.JEV_TASKS[" + json.dumps(match.group(2)) + "] = " +
                               json.dumps(detail, ensure_ascii=False, separators=(",", ":")) + ";\n").encode("utf-8")
                except (OSError, ValueError, TypeError, KeyError) as exc:
                    self.send_error(500, f"Could not load task detail: {exc}")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            return super().do_GET()

    with ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler) as server:
        url = f"http://127.0.0.1:{server.server_port}/{start_path}"
        print(f"Dashboard: {url}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        if open_browser and not webbrowser.open(url):
            print("Browser did not open automatically; paste the URL above into your browser.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("Dashboard stopped.")
    return 0

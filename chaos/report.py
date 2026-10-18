import html
import json
import os
from dataclasses import asdict


def _spark(r, w=420, h=70):
    pts = [s for s in r.series if s[0] >= -10]
    t_end = max(s[0] for s in pts) or 1
    tmin = -10
    x = lambda t: 6 + (t - tmin) / (t_end - tmin) * (w - 12)
    y = lambda v: 6 + (1 - v) * (h - 12)
    line = " ".join(f"{x(t):.1f},{y(v):.1f}" for t, v, _ in pts)
    marks = [(0, "var(--bad)", "inject")]
    if r.mttd_s is not None:
        marks.append((r.mttd_s, "var(--warn)", "detect"))
    if r.rto_actual_s is not None:
        marks.append((r.rto_actual_s, "var(--ok)", "recovered"))
    m = "".join(f'<line x1="{x(t):.1f}" x2="{x(t):.1f}" y1="4" y2="{h-4}" stroke="{c}" '
                f'stroke-dasharray="3 3"/><text x="{x(t)+3:.1f}" y="12" font-size="9" fill="{c}">{n}</text>'
                for t, c, n in marks)
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" aria-label="success rate over time">'
            f'<polyline fill="none" stroke="var(--line)" stroke-width="1.6" points="{line}"/>{m}</svg>')


def _fmt(v, suf=""):
    return "–" if v is None else f"{v}{suf}"


CSS = """
:root{--bg:#fff;--fg:#1c1c1c;--mut:#666;--card:#f6f6f4;--line:#2a6fdb;--ok:#2e8b57;--warn:#d98a00;--bad:#c0392b;--bd:#ddd}
@media (prefers-color-scheme:dark){:root{--bg:#161616;--fg:#eee;--mut:#9a9a9a;--card:#222;--line:#6aa3ff;--ok:#4cc38a;--warn:#f0a93b;--bad:#ff6b5b;--bd:#333}}
body{font:14px/1.5 system-ui,sans-serif;background:var(--bg);color:var(--fg);max-width:1100px;margin:0 auto;padding:24px}
h1{font-size:22px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.card{background:var(--card);border-radius:8px;padding:10px 12px}.card b{display:block;font-size:20px}.card span{color:var(--mut);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{padding:6px 8px;border-bottom:1px solid var(--bd);text-align:left}
.ok{color:var(--ok)}.bad{color:var(--bad)}details{margin:6px 0;background:var(--card);border-radius:8px;padding:8px 12px}
summary{cursor:pointer}small{color:var(--mut)}
"""


def write_reports(results, summary, out_dir, meta):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.json"), "w") as f:
        json.dump({"meta": meta, "summary": summary, "experiments": [asdict(r) for r in results]}, f, indent=2)

    cards = [
        ("Recovery success", f"{summary['recovery_success_rate_pct']}%"), ("MTTD", _fmt(summary["mttd_s"], " s")),
        ("MTTR", _fmt(summary["mttr_s"], " s")), ("RTO met", f"{summary['rto_met_pct']}%"),
        ("RPO met", f"{summary['rpo_met_pct']}%"), ("Availability", f"{summary['availability_pct']}%"),
        ("Failure rate", f"{summary['failure_rate_pct']}%"),
        ("Error budget used", f"{summary['error_budget_consumed_pct']}%"),
        ("Worst degradation", f"+{summary['worst_degradation_pct']}% latency"),
        ("Data loss", f"{summary['total_data_loss_records']} records"),
    ]
    cards_html = "".join(f'<div class="card"><b>{v}</b><span>{k}</span></div>' for k, v in cards)
    rows, details = [], []
    for r in results:
        ok = r.recovered
        rows.append(
            f"<tr><td>{r.fault}</td><td>{r.signal}</td><td>{_fmt(r.mttd_s)}</td><td>{_fmt(r.mttr_s)}</td>"
            f"<td class={'ok' if r.rto_met else 'bad'}>{_fmt(r.rto_actual_s)} / {r.rto_target_s}</td>"
            f"<td class={'ok' if r.rpo_met else 'bad'}>{r.rpo_actual_s} / {r.rpo_target_s}</td>"
            f"<td>{r.availability_pct}%</td><td>{r.failure_rate_pct}%</td><td>{r.error_budget_consumed_pct}%</td>"
            f"<td>+{r.degradation_pct}%</td><td>{r.data_loss_records}</td>"
            f"<td class={'ok' if ok else 'bad'}>{'self-healed' if r.self_healed else 'recovered' if ok else 'ESCALATED'}</td></tr>")
        acts = "; ".join(f"{a['action']} ({a['start_s']}s→{_fmt(a['end_s'])}s, {'ok' if a['ok'] else 'failed'})"
                         for a in r.actions) or "none"
        details.append(f"<details><summary><b>{r.fault}</b> – {html.escape(r.description)}</summary>"
                       f"{_spark(r)}<small>Actions: {html.escape(acts)}</small></details>")
    doc = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Chaos &amp; DR report</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>
<h1>Chaos Engineering &amp; Autonomous Disaster Recovery – Report</h1>
<small>backend: {meta['backend']} · experiments: {summary['experiments']} · SLO {summary['slo']*100:.2f}% · seed {meta['seed']}</small>
<div class="cards">{cards_html}</div>
<div style="overflow-x:auto"><table><tr><th>Fault</th><th>Signal</th><th>MTTD s</th><th>MTTR s</th><th>RTO act/target s</th>
<th>RPO act/target s</th><th>Avail.</th><th>Fail rate</th><th>Budget</th><th>Degr.</th><th>Lost</th><th>Outcome</th></tr>
{''.join(rows)}</table></div><h2>Timelines</h2>{''.join(details)}
<p><small>MTTD = inject→detect · MTTR = detect→recovered · RTO actual = inject→recovered · RPO actual = lost writes ÷ write rate.</small></p>
</body></html>"""
    with open(os.path.join(out_dir, "report.html"), "w") as f:
        f.write(doc)

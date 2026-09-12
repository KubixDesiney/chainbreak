"""Build the GitHub Pages site under ``site/`` from the sealed evidence bundles.

Nothing on the site is hand-written HTML of a *report*. Every report page is
re-rendered by ``chainbreak report --format html`` from the bundle inside the
committed archive in ``examples/reports/``, so the page and the downloadable
evidence cannot drift apart. This script then injects a site-level provenance
banner ahead of the report's own header -- it adds a stamp, it never edits a
rendered finding.

Why ``--allow-unsealed`` is required, and why that is not a defect: a bundle
that has been through ``chainbreak evidence export --public`` has had its
artifacts rewritten *after* sealing, so the manifest root no longer matches
the bytes on disk. Scrubbing and the integrity root are in permanent tension
-- you can publish the measurement or you can publish a bundle that verifies,
not both -- and CHAINBREAK resolves it by keeping the original root and
stamping every derived finding ``bundle_root_verified: false``. The report
pages say so in their own header. See ``docs/site-provenance.md``.

Run ``scripts/verify_public_site_scrub.py site`` afterwards; that gate, not
this script, decides whether the output may be published.
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_REPO_ROOT: Final = Path(__file__).resolve().parent.parent

# The measured-scope caveat every page carries, in the same words the reports
# use internally (reporting/language.py) and README.md uses for M17 evidence.
_SCOPE_CAVEAT: Final = (
    "Every number here is a measurement of one account, one region and one point in time, "
    "produced by one scenario. NOT_MEASURED is not a pass. These results are evidence about "
    "this run; they do not support general claims about AWS or about any other account."
)


@dataclass(frozen=True)
class Page:
    slug: str
    archive: str
    run_id: str
    title: str
    kind: str  # "aws" | "apparatus"
    blurb: str


_PAGES: Final = (
    Page(
        slug="aws-scope-attenuation",
        archive="examples/reports/aws-m17-valid-block01-scrubbed-sample.tar.gz",
        run_id="01M0A5WS8Q912NJSP0FEH1DWSK",
        title="AWS scope-attenuation report",
        kind="aws",
        blurb=(
            "A real measurement against AWS IAM role chaining in eu-west-3. "
            "SCOPE_ATTENUATION came back DIVERGENT: a delegated agent held two capabilities "
            "its delegation chain did not intend it to hold."
        ),
    ),
    Page(
        slug="apparatus-check-fake",
        archive="examples/reports/apparatus-check-fake-scope-attenuation.tar.gz",
        run_id="01M080YJ8MFNMNJE5VSTCF8CYD",
        title="Fake-provider apparatus check",
        kind="apparatus",
        blurb=(
            "The same scenario run against the deterministic in-process laboratory. "
            "It demonstrates that the analysis, the finding structure and the rendering work. "
            "It measures nothing about AWS, or about any real provider."
        ),
    ),
)

_STYLE: Final = """
  :root { color-scheme: light; }
  body { font-family: -apple-system, "Segoe UI", Roboto, sans-serif; max-width: 960px;
         margin: 0 auto; padding: 2rem 1rem 4rem; color: #1a1a1a; background: #fff;
         line-height: 1.6; }
  a { color: #0b5394; }
  h1 { margin-bottom: 0.25rem; font-size: 2rem; }
  .tagline { color: #555; margin-top: 0; font-size: 1.05rem; }
  .stamp { border: 2px solid #f2b701; background: #fff3cd; padding: 0.75rem 1rem;
           margin: 1.25rem 0; }
  .stamp.apparatus { border-color: #b35c00; background: #ffe6cc; }
  .stamp .label { font-weight: 700; text-transform: uppercase; letter-spacing: 0.03em;
                  display: block; margin-bottom: 0.35rem; font-size: 0.85rem; }
  .caveat { border-left: 4px solid #e45756; background: #fdecea; padding: 0.75rem 1rem;
            margin: 1.25rem 0; }
  .cards { display: grid; gap: 1rem; grid-template-columns: 1fr; margin: 1.5rem 0; }
  @media (min-width: 720px) { .cards { grid-template-columns: 1fr 1fr; } }
  .card { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.15rem; }
  .card h3 { margin: 0 0 0.4rem; }
  .card .kind { font-size: 0.75rem; font-weight: 700; text-transform: uppercase;
                letter-spacing: 0.04em; padding: 0.15rem 0.45rem; border-radius: 3px; }
  .kind.aws { background: #d7e8f5; color: #0b5394; }
  .kind.apparatus { background: #ffe6cc; color: #b35c00; }
  dl.meta { display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 1rem;
            font-size: 0.9rem; margin: 0.6rem 0 0; }
  dl.meta dt { font-weight: 600; color: #555; }
  dl.meta dd { margin: 0; font-family: ui-monospace, SFMono-Regular, monospace; }
  code { font-family: ui-monospace, SFMono-Regular, monospace; background: #f5f5f5;
         padding: 0.1rem 0.3rem; border-radius: 3px; }
  pre { background: #f5f5f5; padding: 0.85rem 1rem; border-radius: 6px; overflow-x: auto; }
  pre code { background: none; padding: 0; }
  footer { margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #ddd; color: #666;
           font-size: 0.9rem; }
  .sitebar { background: #1a1a1a; color: #fff; padding: 0.6rem 1rem; margin: -2rem -1rem 1.5rem;
             font-size: 0.9rem; }
  .sitebar a { color: #9cc9ef; text-decoration: none; margin-right: 1rem; }
"""


def _caveat() -> str:
    return f'<div class="caveat"><strong>Measured scope.</strong> {_SCOPE_CAVEAT}</div>'


def _stamp_box(kind: str, env: dict, prov: dict, run_id: str, subject: str = "This page") -> str:
    """The provider stamp, without the caveat -- so the landing page can show
    one box per report it links to and still print the caveat exactly once.

    ``subject`` names what the stamp is about: a report page stamps itself,
    while the landing page stamps each report it links to."""
    provider = env.get("provider", "unknown")
    if kind == "apparatus":
        label = "Fake-provider apparatus check &mdash; not a measurement of any real provider"
        body = (
            f"{subject} was produced by <code>provider: {html.escape(provider)}</code>, "
            "CHAINBREAK's deterministic in-process laboratory. It is an "
            "<strong>apparatus check</strong>: it exercises the analysis and the rendering "
            "against known ground truth. <strong>It is not an AWS result</strong> and no "
            "number in it describes the behaviour of AWS or any other real provider."
        )
    else:
        label = "Real measurement &mdash; single account, single region, single point in time"
        body = (
            f"{subject} was produced by <code>provider: {html.escape(provider)}</code> "
            f"(adapter {html.escape(str(prov.get('provider_adapter_version', '?')))}) "
            f"in region <code>{html.escape(str(env.get('region', '?')))}</code>, "
            f"run <code>{html.escape(run_id)}</code>. Account and namespace are scrubbed."
        )
    return f'<div class="stamp {kind}"><span class="label">{label}</span>{body}</div>'


def _stamp(kind: str, env: dict, prov: dict, run_id: str) -> str:
    """Stamp plus caveat: what every report page carries."""
    return _stamp_box(kind, env, prov, run_id) + _caveat()


def _sitebar(active: str) -> str:
    links = [("index.html", "CHAINBREAK"), *((p.slug + ".html", p.title) for p in _PAGES)]
    parts = []
    for href, text in links:
        weight = ' style="font-weight:700"' if href == active else ""
        parts.append(f'<a href="{href}"{weight}>{html.escape(text)}</a>')
    parts.append(
        '<a href="https://github.com/KubixDesiney/chainbreak" style="float:right">'
        "Source &amp; evidence &rarr;</a>"
    )
    return f'<div class="sitebar">{"".join(parts)}</div>'


def _read_bundle_meta(archive: Path, run_id: str) -> tuple[dict, dict]:
    with tarfile.open(archive, "r:gz") as tar:
        env = json.loads(tar.extractfile(f"{run_id}/bundle/environment.json").read())
        man = json.loads(tar.extractfile(f"{run_id}/bundle/manifest.json").read())
    return env, man.get("provenance", {})


def _render_report(archive: Path, run_id: str, chainbreak: str) -> str:
    """Re-render the report from the bundle inside ``archive``."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with tarfile.open(archive, "r:gz") as tar:
            tar.extractall(root, filter="data")
        runs_root = root / "runs"
        shutil.copytree(root / run_id / "bundle", runs_root / run_id)
        out = root / "report.html"
        result = subprocess.run(
            [
                chainbreak,
                "report",
                run_id,
                "--format",
                "html",
                "--runs-root",
                str(runs_root),
                "--allow-unsealed",
                "-o",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise SystemExit(f"chainbreak report failed for {run_id}:\n{result.stderr}")
        return out.read_text(encoding="utf-8")


def _inject(report_html: str, page: Page, env: dict, prov: dict) -> str:
    """Add the site bar and the provenance stamp ahead of the report's own
    content, without touching a single rendered finding."""
    banner = _sitebar(f"{page.slug}.html") + _stamp(page.kind, env, prov, page.run_id)
    extra_style = "<style>\n" + _STYLE + "\n  body { max-width: 960px; }\n</style>\n"
    report_html = report_html.replace("</head>", extra_style + "</head>", 1)
    report_html = report_html.replace("<body>", "<body>\n" + banner, 1)
    footer = (
        "<footer><p>Re-rendered by <code>scripts/build_site.py</code> from the sealed bundle in "
        f"<code>{html.escape(page.archive)}</code> via "
        "<code>chainbreak report --format html</code>. Every file on this site passed "
        "<code>scripts/verify_public_site_scrub.py</code> before publication &mdash; see "
        '<a href="index.html#verification">how this was verified</a>.</p></footer>'
    )
    return report_html.replace("</body>", footer + "\n</body>", 1)


def _landing(meta: dict[str, tuple[dict, dict]]) -> str:
    # Both stamps, in full, above the fold. This site publishes exactly one
    # real measurement and exactly one apparatus check, and a reader must not
    # have to click through to find out which is which.
    stamps = (
        "".join(
            _stamp_box(
                page.kind,
                *meta[page.slug],
                page.run_id,
                subject=f'The <a href="{page.slug}.html">{html.escape(page.title.lower())}</a> '
                f"on this site",
            )
            for page in _PAGES
        )
        + _caveat()
    )
    cards = []
    for page in _PAGES:
        env, _prov = meta[page.slug]
        kind_label = "AWS measurement" if page.kind == "aws" else "Apparatus check"
        cards.append(f"""
    <div class="card">
      <span class="kind {page.kind}">{kind_label}</span>
      <h3><a href="{page.slug}.html">{html.escape(page.title)}</a></h3>
      <p>{page.blurb}</p>
      <dl class="meta">
        <dt>provider</dt><dd>{html.escape(str(env.get("provider")))}</dd>
        <dt>region</dt><dd>{html.escape(str(env.get("region")))}</dd>
        <dt>run</dt><dd>{html.escape(page.run_id)}</dd>
      </dl>
    </div>""")

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CHAINBREAK &mdash; authorization behaviour in delegated cloud systems</title>
<style>{_STYLE}</style>
</head>
<body>
{_sitebar("index.html")}
<h1>CHAINBREAK</h1>
<p class="tagline">An empirical benchmark for authorization behaviour in delegated and
agentic cloud systems. It measures what a delegated identity <em>can actually do</em>,
by probing &mdash; not what a policy says it should be able to do.</p>

{stamps}

<p>These are real CHAINBREAK reports, rendered. Read them without installing anything.</p>

<div class="cards">{"".join(cards)}
</div>

<h2>What the AWS report found</h2>
<p>In one <code>eu-west-3</code> account, a two-hop IAM role chain was given a session policy
intended to narrow an agent's authority. It did narrow &mdash; but the middle agent still
returned <code>ALLOWED</code> for <code>keyvalue.write</code> and <code>objectstore.list</code>
in every trial, because those capabilities came from the role's <em>own</em> permission policy
rather than the delegated scope. The session policy never granted them and never took them
away.</p>
<p>CHAINBREAK reports that as <code>AUTHORITY_EXPANSION</code> at <code>REVIEW</code> severity,
with the observation and the interpretation kept in separate fields, and it declines to score
the three categories the scenario never exercised.</p>

<h2 id="verification">How this site was verified</h2>
<p>Publishing evidence is how accounts leak. Every file here &mdash; each page, and each
archive attached to the release &mdash; was scanned before publication by
<code>scripts/verify_public_site_scrub.py</code>, which imports the same compiled patterns
<code>chainbreak evidence export --public</code> uses
(<a href="https://github.com/KubixDesiney/chainbreak/blob/main/EVIDENCE_SCHEMA.md">EVIDENCE_SCHEMA.md</a>
section 11) and applies them to HTML, Markdown and every member of every
<code>.tar.gz</code> &mdash; including the HTML-entity-decoded text, so an identifier cannot
hide behind an escape. Residual account IDs, ARNs, hostnames, live namespaces, session names,
policy documents and credential-shaped blobs: <strong>zero</strong>.</p>
<p>The gate is not decorative. It caught a live benchmark namespace in an archive that had
been committed as &ldquo;scrubbed&rdquo; a day before namespace scrubbing was added to the
exporter; that archive was re-scrubbed before anything was published.</p>

<h2>Run it yourself, without an AWS account</h2>
<p>The scrubbed evidence archives are attached to the
<a href="https://github.com/KubixDesiney/chainbreak/releases/tag/v0.1.0">v0.1.0 release</a>.
Download one and analyse it:</p>
<pre><code>pip install "chainbreak[report]"
tar -xzf aws-m17-valid-block01-scrubbed-sample.tar.gz
chainbreak analyze 01M0A5WS8Q912NJSP0FEH1DWSK \\
  --runs-root 01M0A5WS8Q912NJSP0FEH1DWSK --allow-unsealed
chainbreak report 01M0A5WS8Q912NJSP0FEH1DWSK \\
  --runs-root 01M0A5WS8Q912NJSP0FEH1DWSK --allow-unsealed --format terminal</code></pre>
<p><code>--allow-unsealed</code> is required and is not a defect: scrubbing rewrites artifacts
after the bundle was sealed, so a published bundle's integrity root no longer matches its own
bytes. CHAINBREAK keeps the original root rather than re-sealing over the scrub, and stamps
every finding derived from it <code>bundle_root_verified: false</code> &mdash; visible in the
header of both reports above.</p>
<p>Or generate a fresh apparatus bundle with no download at all:</p>
<pre><code>chainbreak run scenarios/scope-attenuation/basic.yaml --provider fake --seed 1729
chainbreak analyze &lt;run-id&gt;
chainbreak report &lt;run-id&gt; --format terminal</code></pre>

<footer>
<p>CHAINBREAK is licensed Apache-2.0.
<a href="https://github.com/KubixDesiney/chainbreak">Source, scenarios and full evidence
schema on GitHub</a>.
Pages on this site are re-rendered from sealed bundles by
<code>scripts/build_site.py</code> and gated by
<code>scripts/verify_public_site_scrub.py</code>.</p>
</footer>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=_REPO_ROOT / "site")
    parser.add_argument("--chainbreak", default="chainbreak", help="chainbreak executable.")
    args = parser.parse_args(argv)

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    meta: dict[str, tuple[dict, dict]] = {}

    for page in _PAGES:
        archive = _REPO_ROOT / page.archive
        env, prov = _read_bundle_meta(archive, page.run_id)
        meta[page.slug] = (env, prov)
        rendered = _render_report(archive, page.run_id, args.chainbreak)
        (out / f"{page.slug}.html").write_text(_inject(rendered, page, env, prov), encoding="utf-8")
        print(f"rendered {page.slug}.html  <- {page.archive} ({page.run_id})")

    (out / "index.html").write_text(_landing(meta), encoding="utf-8")
    print("rendered index.html")

    # Jekyll would otherwise try to process these as a site source.
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"\nsite built -> {out}")
    print("NOW RUN THE GATE:  python scripts/verify_public_site_scrub.py site")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# CHAINBREAK -- deterministic fake-provider runner (M18 F6, REPRODUCIBILITY.md
# section 7: "Reproducing without AWS").
#
# This image runs the offline path only: `chainbreak run --provider fake`,
# `analyze`, and `report`. It does not install boto3 or anything from the
# `aws` extra, so there is no code path inside this image that could reach a
# real AWS account even by accident -- not a credential, not an SDK call
# (S2: "no credentials and no AWS configuration").
#
# Verified deterministic (REPRODUCIBILITY.md, M18 acceptance criterion 3),
# precisely stated: the same scenario + seed run inside and outside this
# container produces byte-identical graph.json/scenario.json/policy_states
# .jsonl/credentials.jsonl, and a `chainbreak compare` between the two
# bundles reports zero divergence. observations.jsonl/events.jsonl are
# NOT expected to be byte-identical -- both embed identifiers salted per
# run_id (ADR-013), which differs on every invocation by design, container
# or not. This is a packaging guarantee, not a new determinism mechanism --
# the fake provider is already fully seeded (M5); this Dockerfile only has
# to avoid introducing anything environment-dependent (locale, timezone,
# hash randomization) on top of that.

FROM python:3.12-slim AS build

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir --root-user-action=ignore build==1.* && \
    python -m build --wheel --outdir /build/dist

FROM python:3.12-slim

LABEL org.opencontainers.image.title="chainbreak" \
      org.opencontainers.image.description="An empirical benchmark for authorization behavior in delegated and agentic cloud systems -- fake-provider runner" \
      org.opencontainers.image.licenses="Apache-2.0"

# Deterministic Python hashing and no .pyc write-back: neither affects the
# fake provider's own seeded determinism, but PYTHONHASHSEED in particular
# is the kind of ambient per-process randomness this image should not
# introduce on top of it (dict/set iteration order is already
# canonicalized at the JSON layer -- core/canonical.py -- but there is no
# reason to add a second source of run-to-run variation on top of that one).
ENV PYTHONHASHSEED=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin chainbreak

COPY --from=build /build/dist/*.whl /tmp/wheels/
# report extra (jinja2, plotly) so `analyze`/`report` work offline too, per
# REPRODUCIBILITY.md section 7's full run -> analyze -> report walkthrough.
# aws/dev/analysis extras are deliberately excluded (S2; and boto3/pyarrow
# would otherwise be most of this image's weight for a provider this image
# can never actually use). The wheel's real, PEP 427 filename (including its
# version and tags) must be preserved -- pip rejects a renamed .whl -- so the
# extras suffix is appended via a shell-expanded variable instead of a fixed
# COPY destination name.
RUN whl="$(ls /tmp/wheels/*.whl)" && \
    pip install --no-cache-dir --root-user-action=ignore "${whl}[report]" && \
    rm -rf /tmp/wheels

USER chainbreak
WORKDIR /home/chainbreak
COPY --chown=chainbreak:chainbreak scenarios/ ./scenarios/

ENTRYPOINT ["chainbreak"]
CMD ["--help"]

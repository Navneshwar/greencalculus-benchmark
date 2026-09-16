#!/usr/bin/env python3
"""Which domains do search-enabled models actually read?

Reads aeo/search_answers.jsonl (the 14 Sep search-on baseline) and counts the
retrieved-source domains behind the 125 answers. This is the evidence the MCP
distribution decisions were waiting on: a directory worth paying to enter is one
that shows up in the sources models retrieve, not one that merely lists us.

The headline metric is ANSWER PRESENCE -- in how many of the 125 answers does a
domain appear at least once -- not raw mention count. A single answer citing one
domain nine times is one answer's worth of evidence, and raw counts let a chatty
model decide the ranking.

CAVEAT, and it bounds every number here: Gemini returns part of its citations as
vertexaisearch.cloud.google.com grounding redirects, which hide the real domain.
Those are counted and reported separately rather than silently dropped; the
domain table is therefore a table of the RESOLVABLE citations only.

    python3 aeo/domain_map.py            # the whole run
    python3 aeo/domain_map.py --intent agent
"""

import argparse
import collections
import json
import pathlib
import sys
from urllib.parse import urlparse

HERE = pathlib.Path(__file__).resolve().parent
ANSWERS = HERE / "search_answers.jsonl"
OPAQUE = "vertexaisearch.cloud.google.com"

# Surfaces the distribution plan has a decision riding on. Listed so that an
# absence is reported explicitly -- "not in the table" and "cited zero times"
# read identically otherwise, and only one of them is evidence.
MCP_SURFACES = [
    "glama.ai",
    "pulsemcp.com",
    "smithery.ai",
    "mcp.so",
    "apify.com",
    "lobehub.com",
    "mcpservers.org",
    "registry.modelcontextprotocol.io",
    "modelcontextprotocol.io",
    "github.com",
    "cursor.directory",
    "playbooks.com",
    "mcpmarket.com",
]

OURS = "greencalculus.com"


def normalise(url: str) -> str:
    """A citation may be a bare domain or a full URL; return a bare host."""
    host = urlparse(url).netloc if url.startswith("http") else url
    return host.lower().removeprefix("www.")


def load(intent=None, prompt_contains=None):
    rows = [json.loads(line) for line in ANSWERS.open()]
    if intent:
        rows = [r for r in rows if r["intent"] == intent]
    if prompt_contains:
        needle = prompt_contains.lower()
        rows = [r for r in rows if needle in r["prompt"].lower()]
    return rows


def tabulate(rows):
    """answer-presence, model-breadth and raw mentions, per domain."""
    answers = collections.Counter()
    models = collections.defaultdict(set)
    mentions = collections.Counter()
    opaque_answers = 0
    opaque_mentions = 0

    for row in rows:
        seen = set()
        had_opaque = False
        for url in row["cited_urls"]:
            host = normalise(url)
            if host == OPAQUE:
                opaque_mentions += 1
                had_opaque = True
                continue
            mentions[host] += 1
            seen.add(host)
        for host in seen:
            answers[host] += 1
            models[host].add(row["model"])
        if had_opaque:
            opaque_answers += 1

    return answers, models, mentions, opaque_answers, opaque_mentions


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--intent", help="restrict to one intent bucket")
    ap.add_argument("--prompt-contains", help="restrict to prompts containing this")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = ap.parse_args()

    rows = load(args.intent, args.prompt_contains)
    if not rows:
        sys.exit("no rows matched")

    n = len(rows)
    answers, models, mentions, opaque_answers, opaque_mentions = tabulate(rows)
    searched = sum(r["searched"] for r in rows)
    resolvable = sum(mentions.values())

    if args.json:
        json.dump(
            {
                "answers": n,
                "searched": searched,
                "resolvable_citations": resolvable,
                "opaque_citations": opaque_mentions,
                "domains": {
                    h: {"answers": c, "models": len(models[h]), "mentions": mentions[h]}
                    for h, c in answers.most_common()
                },
            },
            sys.stdout,
            indent=2,
        )
        return

    scope = []
    if args.intent:
        scope.append(f"intent={args.intent}")
    if args.prompt_contains:
        scope.append(f"prompt~{args.prompt_contains!r}")
    print(f"scope: {' '.join(scope) or 'the whole run'}")
    print(f"answers: {n}   of which actually searched: {searched}")
    print(f"citations: {resolvable} resolvable, {opaque_mentions} opaque "
          f"(Gemini grounding redirects, in {opaque_answers} answers)")
    print(f"distinct domains: {len(answers)}\n")

    print(f"{'domain':44} {'answers':>8} {'share':>7} {'models':>7} {'cites':>6}")
    print("-" * 76)
    for host, c in answers.most_common(args.top):
        print(f"{host:44} {c:>8} {c / n:>6.0%} {len(models[host]):>7} {mentions[host]:>6}")

    print(f"\n{'MCP surface':44} {'answers':>8} {'share':>7} {'models':>7} {'cites':>6}")
    print("-" * 76)
    for host in MCP_SURFACES:
        c = answers.get(host, 0)
        flag = "" if c else "   <- never cited"
        print(f"{host:44} {c:>8} {c / n:>6.0%} {len(models[host]):>7} "
              f"{mentions.get(host, 0):>6}{flag}")

    c = answers.get(OURS, 0)
    print(f"\n{OURS}: cited in {c} of {n} answers ({c / n:.0%}), "
          f"{len(models[OURS])} distinct models, {mentions.get(OURS, 0)} mentions")


if __name__ == "__main__":
    main()

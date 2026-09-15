#!/usr/bin/env python3
"""The SEARCH-ENABLED arm: the same 25 prompts, with web access switched ON.

The baseline (run.py) measures what a model BELIEVES — fixed at training time,
and the surface no amount of work in 2026 can move. This arm measures what a
model can FIND, which responds to work in weeks. They are different questions
and they get reported side by side, never merged.

The prompts are byte-identical to the baseline. Never edit them: a changed
instrument measures nothing.

EVERY ROW RECORDS WHETHER THE MODEL ACTUALLY SEARCHED. A provider that silently
ignores the tool would otherwise produce answers indistinguishable from the
baseline, and the arm would report "no change" when it had simply not run. The
flag comes from the provider's own response structure, not from the prose.
"""
import json, os, re, sys, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from prompts import PROMPTS

OUT = Path(__file__).parent / "search_answers.jsonl"
URL_RE = re.compile(r'https?://[^\s\)\]"<>]+')

# List rates, each verified against the provider's own pricing page 2026-09-14.
# ($/M input, $/M output, $ per search unit, unit). Gemini grounding is free for
# the first 5,000 searches/month across all Gemini 3.x models; this arm uses ~50,
# so it is priced at zero and the ceiling below is what catches it if that is
# ever wrong. The xAI search rate is the ONE figure not confirmed from a primary
# source — their agent-tools pricing page 404s — so treat grok spend as an
# estimate until the console says otherwise.
RATES = {
    "claude-opus-5":          (5.00, 25.00, 0.010, "search"),
    "gpt-5.5":                (5.00, 30.00, 0.010, "search"),
    "gemini-3.1-pro-preview": (2.00, 12.00, 0.000, "request"),
    "gemini-3.6-flash":       (0.75,  3.75, 0.000, "request"),
    "grok-4.6":               (2.00,  6.00, 0.025, "search"),
}
# Hard ceiling. Google bills postpaid with no cap of its own, and the retry loop
# below will happily spend into a malformed response, so the run stops itself.
MAX_SPEND = float(os.environ.get("GC_MAX_SPEND", "25"))
MAX_CALLS = int(os.environ.get("GC_MAX_CALLS", "400"))
SPENT = [0.0]
CALLS = [0]


def price(model, usage, n_searches):
    """Cost of one answer, from the provider's own usage block."""
    r = RATES.get(model)
    if not r:
        return 0.0
    pin, pout, srate, unit = r
    inp = (usage.get("input") or 0) / 1e6 * pin
    out = (usage.get("output") or 0) / 1e6 * pout
    srch = srate * (1 if unit == "request" else n_searches)
    return inp + out + srch


def post(url, payload, headers, timeout=600):
    r = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                               headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _usage(d, provider):
    """Normalise each provider's usage block.

    Recorded because the first costing of this arm had to BRACKET Anthropic's
    input tokens rather than state them — the harness threw the numbers away.
    Search results are injected into context, so input tokens are the whole
    cost story; without this a re-run cannot be priced from evidence.
    """
    u = d.get("usage") or {}
    if provider == "gemini":
        u = d.get("usageMetadata") or {}
        return {"input": u.get("promptTokenCount"), "output": u.get("candidatesTokenCount"),
                "total": u.get("totalTokenCount")}
    return {"input": u.get("input_tokens"), "output": u.get("output_tokens"),
            "cached": u.get("cache_read_input_tokens") or (u.get("input_tokens_details") or {}).get("cached_tokens"),
            "server_tool": u.get("server_tool_use")}


def ask_claude(model, prompt):
    d = post("https://api.anthropic.com/v1/messages",
             {"model": model, "max_tokens": 16000,
              "tools": [{"type": os.environ.get("GC_WEB_SEARCH_TYPE", "web_search_20250305"),
                         "name": "web_search", "max_uses": 8}],
              "messages": [{"role": "user", "content": prompt}]},
             {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    blocks = d["content"]
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    n = sum(1 for b in blocks if b.get("type") == "server_tool_use")
    urls = []
    for b in blocks:
        if b.get("type") == "web_search_tool_result":
            for r in (b.get("content") or []):
                if isinstance(r, dict) and r.get("url"):
                    urls.append(r["url"])
    return text, n, urls, _usage(d, "anthropic")


def ask_gemini(model, prompt):
    k = os.environ["GEMINI_API_KEY"]
    d = post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={k}",
             {"contents": [{"parts": [{"text": prompt}]}],
              "tools": [{"google_search": {}}],
              "generationConfig": {"maxOutputTokens": 16000}}, {})
    c = d["candidates"][0]
    text = "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []))
    gm = c.get("groundingMetadata") or {}
    n = len(gm.get("webSearchQueries") or [])
    urls = [ch.get("web", {}).get("uri", "") for ch in (gm.get("groundingChunks") or [])]
    # Gemini returns vertexaisearch redirect URLs; the readable domain is in .title
    urls += [ch.get("web", {}).get("title", "") for ch in (gm.get("groundingChunks") or [])]
    return text, n, [u for u in urls if u], _usage(d, "gemini")


def _parse_responses(d):
    """xAI and OpenAI both speak the Responses API. One parser, so the two cannot
    drift apart in how they count a search — which would silently make the
    `searched` flag mean different things per provider."""
    out = d.get("output", [])
    text = "".join(c.get("text", "") for o in out if o.get("type") == "message"
                   for c in (o.get("content") or []) if c.get("type") in ("output_text", "text"))
    n = sum(1 for o in out if o.get("type") == "web_search_call")
    urls = URL_RE.findall(json.dumps(out))
    return text, n, urls


def ask_grok(model, prompt):
    # Live Search (search_parameters) was deprecated 410 — this is the Agent Tools route.
    d = post("https://api.x.ai/v1/responses",
             {"model": model, "input": prompt, "tools": [{"type": "web_search"}]},
             {"Authorization": f"Bearer {os.environ['XAI_API_KEY']}"})
    text, n, urls = _parse_responses(d)
    return text, n, urls, _usage(d, "xai")


def ask_gpt(model, prompt):
    """OpenAI's built-in web_search lives on the Responses API, so this route does
    NOT mirror run_tools.py's chat/completions path for the same model. Note that
    wherever the two are read side by side."""
    d = post("https://api.openai.com/v1/responses",
             {"model": model, "input": prompt, "tools": [{"type": "web_search"}],
              "max_output_tokens": 16000},
             {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"})
    text, n, urls = _parse_responses(d)
    return text, n, urls, _usage(d, "openai")


def ask(model, prompt):
    if model.startswith("claude"):
        return ask_claude(model, prompt)
    if model.startswith("gemini"):
        return ask_gemini(model, prompt)
    if model.startswith("grok"):
        return ask_grok(model, prompt)
    if model.startswith("gpt"):
        return ask_gpt(model, prompt)
    raise ValueError(f"no search route for {model}")


def main():
    models = sys.argv[1:] or ["gemini-3.6-flash", "gemini-3.1-pro-preview",
                              "grok-4.6", "claude-opus-5", "gpt-5.5"]
    done = set()
    if OUT.exists():
        for l in OUT.open():
            if l.strip():
                r = json.loads(l); done.add((r["model"], r["prompt"]))
    t0 = time.time()
    with OUT.open("a") as fh:
        for model in models:
            for intent, prompt in PROMPTS:
                if (model, prompt) in done:
                    continue
                for attempt in range(3):
                    try:
                        text, n, urls, usage = ask(model, prompt); break
                    except Exception as e:
                        print(f"  {model:24} retry {attempt+1}: {str(e)[:60]}", flush=True)
                        time.sleep(20); text = None
                if text is None:
                    print(f"  {model:24} FAILED {intent}", flush=True); continue
                cost = price(model, usage, n)
                SPENT[0] += cost; CALLS[0] += 1
                blob = (text + " " + " ".join(urls)).lower()
                fh.write(json.dumps({
                    "model": model, "intent": intent, "prompt": prompt, "answer": text,
                    "searched": n > 0, "n_searches": n,
                    "cited_urls": sorted(set(urls))[:40],
                    "usage": usage,
                    "greencalculus_in_text": "greencalculus" in text.lower(),
                    "greencalculus_in_sources": "greencalculus" in " ".join(urls).lower(),
                }) + "\n")
                fh.flush()
                gc = "GC!" if "greencalculus" in blob else "   "
                print(f"  {model:24} {intent:11} {len(text):>6}ch  {n:>2} searches {gc} "
                      f"${cost:.3f}  running ${SPENT[0]:.2f}  ({time.time()-t0:.0f}s)", flush=True)
                if SPENT[0] > MAX_SPEND or CALLS[0] > MAX_CALLS:
                    print(f"\nSTOPPING: ${SPENT[0]:.2f} / {CALLS[0]} calls exceeds the ceiling "
                          f"(GC_MAX_SPEND={MAX_SPEND}, GC_MAX_CALLS={MAX_CALLS}). "
                          f"Rerun to resume — finished answers are on disk.", flush=True)
                    return
    print(f"\ndone in {time.time()-t0:.0f}s, {CALLS[0]} calls, ~${SPENT[0]:.2f} -> {OUT.name}")


if __name__ == "__main__":
    main()

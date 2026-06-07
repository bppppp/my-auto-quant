#!/usr/bin/env python
"""
Concurrent strategy generation test script
Generates N strategies, performs hard validation and quality eval, summarizes results
"""
import sys
sys.path.insert(0, ".")

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import time

from config import _load_env_file
_load_env_file()

from strategies.agents.base_agent import (
    build_llm, load_prompt, parse_strategy_json, validate_md_structure,
    write_md, strategy_dir_for, original_md_path, validate_auto_name
)
from strategies.agents.quality_eval import run_quality_eval
from strategies.config import get_llm_settings

@dataclass
class GenResult:
    name: str
    success: bool = False
    hard_errors: list = field(default_factory=list)
    quality_score: float = 0.0
    quality_passed: bool = False
    error_message: str = ""
    gen_time: float = 0.0
    narrative_len: int = 0

def gen_one(task_id: int) -> GenResult:
    start = time.time()
    r = GenResult(name=f"task_{task_id}")
    try:
        settings = get_llm_settings(temperature=0.3, enable_thinking=True)
        llm = build_llm(settings)
        system_prompt = load_prompt("generate")
        user_prompt = """Generate a Chinese A-share mid-term swing strategy according to system prompt.
        
Requirements:
- Annual return > 20% (hard rule)
- Return/drawdown >= 1.0 (hard rule)
- test_universe: select from HS300/CSI1000/CYB_STAR_50
- strategy_narrative: >= 800 chars, 4 sections (strategy idea / 3-market treatment / multi-signal / risk)
- params[].description: >= 30 chars
"""
        
        resp = llm.invoke(system_prompt, user_prompt)
        data = parse_strategy_json(resp)
        
        if not isinstance(data, dict):
            r.error_message = "output not dict"
            return r
        
        for k in ("name", "test_universe", "frontmatter", "strategy_narrative"):
            if k not in data:
                r.error_message = f"missing {k}"
                return r
        
        body = data.get("strategy_narrative", "")
        r.narrative_len = len(body)
        
        fm = data["frontmatter"]
        fm.setdefault("test_universe", data["test_universe"])
        errors = validate_md_structure(fm, body, mode="generate")
        
        hard_errs = [e for e in errors if not str(e.code).endswith("-soft")]
        r.hard_errors = [str(e) for e in hard_errs]
        
        if hard_errs:
            r.error_message = f"hard validation failed {len(hard_errs)}"
            return r
        
        eval_r = run_quality_eval(fm, body, settings=settings)
        r.quality_score = eval_r.get("_quality_total", 0)
        r.quality_passed = eval_r.get("passed", False)
        
        if not r.quality_passed:
            r.error_message = f"quality_eval failed {r.quality_score:.1f}/60"
            return r
        
        name = validate_auto_name(data["name"])
        r.name = name
        write_md(strategy_dir_for(name, track="main") / f"{name}_v1.md", fm, body)
        write_md(original_md_path(name), fm, body, immutable=True)
        
        r.success = True
        print(f"[Task {task_id}] OK: {name}")
    except Exception as e:
        r.error_message = f"{type(e).__name__}: {e}"
        print(f"[Task {task_id}] FAIL: {r.error_message}")
    
    r.gen_time = time.time() - start
    return r

def run_test(n: int = 10, workers: int = 3):
    print("=" * 60)
    print(f"Concurrent test: {n} strategies (workers={workers})")
    print("=" * 60)
    
    results = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(gen_one, i): i for i in range(1, n + 1)}
        for f in as_completed(futures):
            try:
                results.append(f.result())
            except Exception as e:
                print(f"Exception: {e}")
    
    return results

def summarize(results):
    total = len(results)
    passed = sum(1 for r in results if r.success)
    failed = total - passed
    
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"Total: {total}")
    print(f"Success: {passed} ({passed/total*100:.1f}%)")
    print(f"Failed: {failed} ({failed/total*100:.1f}%)")
    
    if passed > 0:
        times = [r.gen_time for r in results if r.success]
        lens = [r.narrative_len for r in results if r.success]
        scores = [r.quality_score for r in results if r.success]
        print(f"Avg time: {sum(times)/len(times):.1f}s")
        print(f"Avg narrative: {sum(lens)/len(lens):.0f} chars")
        print(f"Avg quality: {sum(scores)/len(scores):.1f}/60")
    
    print()
    print("Success cases:")
    for r in results:
        if r.success:
            print(f"  [OK] {r.name} ({r.gen_time:.1f}s, q={r.quality_score:.1f})")
    
    print()
    print("Failed cases:")
    for r in results:
        if not r.success:
            print(f"  [FAIL] {r.name}: {r.error_message}")
            for e in r.hard_errors[:2]:
                print(f"    {e}")
    
    print("=" * 60)
    return passed

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("-n", "--count", type=int, default=10)
    p.add_argument("-w", "--workers", type=int, default=3)
    args = p.parse_args()
    
    results = run_test(args.count, args.workers)
    passed = summarize(results)
    sys.exit(0 if passed > 0 else 1)

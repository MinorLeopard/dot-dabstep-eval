# Dot x DABStep Evaluation Harness

## Goal
Build a reproducible evaluation harness to:
1) load DABStep tasks
2) call Dot API for each question
3) extract a single final answer
4) score using DABStep rules
5) produce breakdowns + failure analysis
6) support iterative Dot configuration experiments

## Rules (must)
- DO NOT hardcode answers or use ground truth during inference.
- Every run must write results to results/<run_id>.jsonl with:
  question_id, difficulty, prompt, dot_response_raw, parsed_answer, ground_truth, score, error_type
- Force Dot output format:
  FINAL_ANSWER: <answer>
- If FINAL_ANSWER missing -> score=0 and error_type="format_missing"
- Keep code clean: src/ layout, typed functions, logging, pytest.

## Commands
Provide Makefile targets:
- setup
- test
- run_eval (small sample)
- run_eval_full
- analyze (failure clustering)

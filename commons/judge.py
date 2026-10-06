"""A small LLM judge for labelling text an agent wrote (a post, a message) with one of a few labels.

    judge = Judge("logs/my_batch/judgments.json")
    label = judge(prompt, ["promotes", "neutral", "warns"])
    judge.prefetch(many_prompts, labels)   # label a batch in parallel first, then calls hit the cache

Every answer is cached in a JSON file, keyed by the prompt, so re-running an analysis costs nothing and
the labels can be checked and kept with the logs. Prompts should end by asking for exactly one label.
Answers that match no label, and requests the model declines even after fallback, come back as
"unclear: ..." or "refused" and aren't cached.
"""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_MODEL = "claude-sonnet-5-5"


class Judge:
    def __init__(self, cache: str | Path, model: str = DEFAULT_MODEL):
        self.path = Path(cache)
        self.model = model
        self.cache = json.loads(self.path.read_text()) if self.path.exists() else {}
        self.client = None
        self.lock = threading.Lock()

    def prefetch(self, prompts: list[str], labels: list[str], workers: int = 16) -> None:
        """Label many prompts at once, in parallel, so later calls are answered from the cache."""
        todo = list(dict.fromkeys(p for p in prompts if p not in self.cache))
        with ThreadPoolExecutor(workers) as pool:
            list(pool.map(lambda p: self(p, labels, save=False), todo))
        self.save()

    def save(self) -> None:
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.cache, indent=1, ensure_ascii=False))

    def __call__(self, prompt: str, labels: list[str], save: bool = True) -> str:
        if prompt not in self.cache:
            import anthropic

            with self.lock:
                self.client = self.client or anthropic.Anthropic()
            # Agent transcripts (shell commands, log edits) can trip the model's safety classifiers.
            # Server-side fallback reruns a declined request on another model instead of failing.
            msg = self.client.beta.messages.create(
                model=self.model,
                max_tokens=2000,
                output_config={"effort": "low"},
                messages=[{"role": "user", "content": prompt}],
                betas=["server-side-fallback-2026-07-01"],
                extra_body={"fallbacks": "default"},
            )
            if msg.stop_reason == "refusal":
                return "refused"  # not cached, so a later run can retry
            text = "".join(b.text for b in msg.content if b.type == "text").strip().lower()
            # The last label mentioned wins, so "not promotes, warns" reads as warns.
            found = sorted((text.rfind(l), l) for l in labels if l in text)
            if not found:
                return f"unclear: {text[:60]}"
            with self.lock:
                self.cache[prompt] = found[-1][1]
            if save:
                self.save()
        return self.cache[prompt]

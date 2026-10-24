"""Live smoke test: chat with Rita in the terminal using the real OpenAI API.

Run:  OPENAI_API_KEY=... uv run python -m scripts.llm_smoke
In-memory only (no DB). Ctrl-C to quit.
"""
from __future__ import annotations

from agent.runner import run_turn


def main() -> None:
    history: list[dict] = []
    extracted: dict = {}
    print("Rita (escribe 'salir' para terminar)\n")
    while True:  # empty history → the fixed greeting, no model call
        r = run_turn(history, extracted, client=None)
        history.append({"role": "assistant", "content": r.reply})
        print(f"Rita › {r.reply}")
        if r.completed:
            print(f"\n[cerrado · status={r.status}]\n{r.summary}\n{extracted}")
            return
        user = input("Tú  › ").strip()
        if user.lower() in {"salir", "exit", "quit"}:
            return
        history.append({"role": "user", "content": user})


if __name__ == "__main__":
    main()

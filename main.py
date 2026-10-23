# -*- coding: utf-8 -*-
"""Nodus komut satiri arayuzu:  python main.py "gorev metni"
Streamlit arayuzuyle ayni ajan dongusunu ve guvenlik politikasini kullanir."""
import sys
from dotenv import load_dotenv

load_dotenv()

from agent_core import NodusAgent
from orchestrator import describe_action, execute_with_healing, make_observation, run_autonomous_workflow


def main():
    task = " ".join(sys.argv[1:]).strip() or input("Gorev: ").strip()
    if not task:
        return
    agent = NodusAgent()
    MODELS = []   # model havuzunu providers.Router yonetir
    model, why = agent.select_best_model(task)
    print(f"[Router] {why}")

    wr = run_autonomous_workflow(agent, model, task, [{"role": "user", "content": task}], MODELS, task)
    while True:
        print(wr["reply"])
        action = wr["pending_action"]
        if not action:
            break
        print(f"\n[ONAY GEREKIYOR] {action.get('_risk_reason')}")
        print(describe_action(action)[0] or action)
        try:
            answer = input("Calistirilsin mi? [e/H]: ").strip().lower()
        except EOFError:
            answer = ""
        if answer != "e":
            print("Islem reddedildi.")
            break
        res_text, _ = execute_with_healing(agent, action, model, MODELS)
        resume = wr["resume"]
        obs = make_observation(action.get("action", ""), res_text)
        history = resume["history"] + [{"role": "assistant", "content": resume["response"]}, {"role": "user", "content": obs}]
        wr = run_autonomous_workflow(agent, model, obs, history, MODELS, task, tainted=resume["tainted"])


if __name__ == "__main__":
    main()

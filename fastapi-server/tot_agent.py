"""
Tree of Thought agent built with LangGraph.
Generates multiple reasoning strategies, evaluates them, backtracks on failure,
and replans from learnings when all branches fall short.
"""
import json
import os
import re
import uuid
import datetime
from typing import TypedDict, List, Optional, Callable, Awaitable

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import BaseTool

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend

from prompts.deep_agent_browser import prompt as base_prompt

INTERRUPT_TOOLS = {
    "get_user_confirmation": True,
    "get_user_input_from_options": True,
}


class PlanBranch(TypedDict):
    approach: str
    steps: List[str]
    score: float
    rationale: str
    status: str  # "pending" | "tried" | "succeeded" | "failed"


class ToTState(TypedDict):
    messages: List
    question: str
    branches: List[PlanBranch]
    selected_plan: str
    selected_steps: List[str]
    current_idx: int
    final_answer: str
    errors: List[str]
    feedback_score: int
    replan_count: int
    datapoints_found: bool
    verified_datapoints: str
    inconsistencies_found: bool
    saved_final_path: str
    user_action: str  # "retry" | "recreate" | "context" | "stop"


def _strip_json(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n", 1)
        content = lines[1] if len(lines) > 1 else content[3:]
    if content.endswith("```"):
        content = content[:-3]
    return content.strip()


def _pending_branches(branches: List[PlanBranch]) -> List[int]:
    return [i for i, b in enumerate(branches) if b.get("status") == "pending"]


def _last_ai_text(msgs: List) -> str:
    """Return the last non-tool AIMessage text from a deep agent result."""
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and m.content and not getattr(m, "tool_calls", None):
            return m.content
    for m in reversed(msgs):
        if isinstance(m, AIMessage) and m.content:
            return m.content
    return ""


def create_tot_agent(llm, tools: List[BaseTool], session_project_dir: str = "", on_event: Optional[Callable[[str, str], Awaitable[None]]] = None, resolve_hitl: Optional[Callable[[str, dict, str], Awaitable[dict]]] = None):
    """
    Tree of Thought agent with:
    1. Generate multiple strategies
    2. Evaluate & score each
    3. Select best pending strategy, execute via deep agent
    4. Check if result references data points → verify via a second deep agent; if
       inconsistencies are found, merge the verified data back into a coherent response
    5. Feedback: score result quality 1-10
    6. If score > 7 → accept. Else backtrack or replan.
    7. Replan: generate fresh strategies from failed learnings (max 1 replan cycle).

    Deep agents use the same tools and HITL interrupts (interrupt_on) as the main
    agent in app.py. resolve_hitl(tool_name, args, description) is awaited whenever
    an inner agent interrupts for user input; if None, interruptions auto-respond.
    """

    async def _log(typ: str, msg: str):
        if on_event:
            await on_event(typ, msg)

    async def _run_agent_with_hitl(agent, history: List, config: dict) -> dict:
        """Invoke an inner deep agent and loop through HITL interrupts (same as app.py)."""
        result = await agent.ainvoke({"messages": history}, config=config)
        while True:
            state_snapshot = await agent.aget_state(config)
            if not state_snapshot.next:
                break
            task = state_snapshot.tasks[0]
            if not task.interrupts:
                break
            # langchain's HumanInTheLoopMiddleware aggregates all interrupt tools of
            # a message into one interrupt; the resume payload must carry exactly one
            # decision per action_request.
            resume_map = {}
            for it in task.interrupts:
                hitl_request = it.value
                action_requests = hitl_request.get("action_requests", [])
                if not action_requests:
                    continue
                decisions = []
                for action in action_requests:
                    tool_name = action.get("name", "unknown")
                    tool_args = action.get("args", {})
                    await _log("tot_phase", f"Awaiting user decision for {tool_name}...")
                    if resolve_hitl is None:
                        decision = {"type": "respond", "message": "Proceed with the default action."}
                    else:
                        decision = await resolve_hitl(tool_name, tool_args, action.get("description", ""))
                    decisions.append(decision)
                resume_map[it.id] = {"decisions": decisions}
            if not resume_map:
                break
            if len(resume_map) == 1 and len(next(iter(resume_map.values()))["decisions"]) == 1:
                resume_value = next(iter(resume_map.values()))
            else:
                resume_value = resume_map
            result = await agent.ainvoke(Command(resume=resume_value), config=config)
        return result

    async def generate_plans(state: ToTState) -> dict:
        is_replan = state.get("replan_count", 0) > 0
        if is_replan:
            await _log("tot_phase", "Replanning based on failed strategies...")
            failed = [b for b in state["branches"] if b.get("status") == "failed"]
            lessons = "\n".join(
                f"- {b['approach']}: {b.get('rationale', 'No rationale')}"
                for b in failed
            )
            plan_prompt = f"""You are a strategic planner. Previous strategies failed for this task.

User task: {state['question']}

Failed strategies with their rationale:
{lessons}

Learn from these failures. Generate 2 new, fundamentally different approaches that avoid the same pitfalls.

Format your response as valid JSON:
{{
  "branches": [
    {{
      "approach": "Approach name",
      "steps": ["step 1", "step 2", ...],
      "rationale": "Why this new approach should work"
    }}
  ]
}}"""
        else:
            await _log("tot_phase", "Generating diverse strategies...")
            plan_prompt = f"""You are a strategic planner. Given a user task, generate 2-3 distinct approaches to solve it.

User task: {state['question']}

For each approach, provide:
1. A concise name/description of the approach
2. A step-by-step plan (3-6 steps)
3. The rationale for why this approach might work

Format your response as valid JSON:
{{
  "branches": [
    {{
      "approach": "Approach name",
      "steps": ["step 1", "step 2", ...],
      "rationale": "Why this approach works"
    }}
  ]
}}

Generate diverse, genuinely different approaches. Consider different angles, tools, and strategies."""
        msg = HumanMessage(content=plan_prompt)
        response = await llm.ainvoke([msg])
        content = _strip_json(response.content)
        try:
            data = json.loads(content)
            branches = data.get("branches", [])
        except (json.JSONDecodeError, KeyError):
            branches = []
        if not branches:
            branches = [{"approach": "Direct approach", "steps": ["Analyze the task", "Execute step by step", "Return result"], "rationale": "Standard approach"}]
        for b in branches:
            b.setdefault("score", 0.0)
            b["status"] = "pending"
        names = [b["approach"] for b in branches]
        await _log("tot_branches", json.dumps(names))
        tag = "Replanned" if is_replan else "Identified"
        await _log("tot_progress", f"{tag} {len(branches)} strategies: {' | '.join(names)}")
        return {"branches": state["branches"] + branches}

    async def evaluate_plans(state: ToTState) -> dict:
        branches = state["branches"]
        pending = [b for b in branches if b.get("status") == "pending"]
        if not pending:
            return {}
        await _log("tot_phase", "Evaluating strategies...")
        eval_prompt = "You are a critic. Evaluate each approach for the user's task and score it 1-10.\n\n"
        eval_prompt += f"User task: {state['question']}\n\n"
        for i, b in enumerate(branches):
            if b.get("status") != "pending":
                continue
            eval_prompt += f"--- Approach {i}: {b['approach']} ---\n"
            for s in b.get("steps", []):
                eval_prompt += f"- {s}\n"
            eval_prompt += f"Rationale: {b['rationale']}\n\n"
        eval_prompt += """Respond in valid JSON:
{
  "scores": [
    {"index": 0, "score": 7, "reasoning": "Brief reasoning"},
    {"index": 1, "score": 8, "reasoning": "Brief reasoning"}
  ]
}
Score based on: feasibility, thoroughness, efficiency, and relevance to the task.
Use the original index from the list above."""
        msg = HumanMessage(content=eval_prompt)
        response = await llm.ainvoke([msg])
        content = _strip_json(response.content)
        try:
            data = json.loads(content)
            for s in data.get("scores", []):
                idx = s.get("index")
                if idx is not None and 0 <= idx < len(branches) and branches[idx].get("status") == "pending":
                    branches[idx]["score"] = float(s.get("score", 5))
        except (json.JSONDecodeError, KeyError, IndexError):
            pass
        for b in branches:
            if b.get("status") == "pending" and b.get("score", 0) == 0.0:
                b["score"] = 5.0
        scores = {b["approach"]: f"{b['score']}/10" for b in branches if b.get("status") == "pending"}
        await _log("tot_scores", json.dumps(scores))
        await _log("tot_progress", f"Evaluated: {' | '.join(f'{k} {v}' for k, v in scores.items())}")
        return {"branches": branches}

    async def select_plan(state: ToTState) -> dict:
        branches = state["branches"]
        pending = _pending_branches(branches)
        if not pending:
            await _log("tot_progress", "No remaining strategies to try.")
            return {"final_answer": "All approaches were exhausted without a successful result.", "errors": state.get("errors", []) + ["No branches remaining"]}
        idx = max(pending, key=lambda i: branches[i].get("score", 0))
        best = branches[idx]
        branches[idx]["status"] = "tried"
        await _log("tot_selected", best["approach"])
        await _log("tot_progress", f"Selected strategy: {best['approach']} ({best['score']}/10)")
        return {
            "branches": branches,
            "selected_plan": best["approach"],
            "selected_steps": best["steps"],
            "current_idx": idx,
        }

    async def execute_plan(state: ToTState) -> dict:
        idx = state.get("current_idx", -1)
        plan_name = state.get("selected_plan", "unknown")
        await _log("tot_phase", f"Executing: {plan_name}")
        full_prompt = base_prompt + "\n\n" + f"""## Selected Strategy: {state['selected_plan']}

### Execution Plan:
{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(state['selected_steps']))}

Follow this plan step by step. Use the available tools to execute each step.
After completing all steps, provide a comprehensive final answer summarizing what was done and the results.

### Output Format — Case Study / Report (REQUIRED)
Because this task requires analysis and/or web search, the final answer MUST always be written as a structured Case Study / Report. Use these sections:

# Case Study: <short title derived from the user's task>
## 1. Objective
The goal of the task and the questions it answers.
## 2. Approach / Methodology
The strategy used, the tools/actions taken, and the sources consulted.
## 3. Findings
The concrete results, data points, and evidence gathered (with source URLs).
## 4. Analysis
Interpretation of the findings and how they answer the objective.
## 5. Conclusion
A clear summary of the outcome and any limitations.
## 6. References
Every source consulted, as URLs.

Write the complete report as your final answer — do not summarize away the sections."""
        history = state["messages"]
        checkpointer = MemorySaver()
        thread_id = str(uuid.uuid4())
        agent = create_deep_agent(
            model=llm,
            tools=tools,
            backend=FilesystemBackend(root_dir=os.path.join(session_project_dir, "files"), virtual_mode=True),
            system_prompt=full_prompt,
            interrupt_on=INTERRUPT_TOOLS,
            checkpointer=checkpointer,
        )
        branches = list(state["branches"])
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 1000}
        try:
            result = await _run_agent_with_hitl(agent, history, config)
            final = _last_ai_text(result.get("messages", []))
            if 0 <= idx < len(branches):
                branches[idx]["status"] = "succeeded"
            await _log("tot_progress", f"Strategy produced result: {plan_name}")
            summary = HumanMessage(content=f"[Strategy: {plan_name}] Result:\n{final or 'Task completed.'}")
            await _log("tot_message", summary.content)
            return {"final_answer": final or "Task completed.", "branches": branches, "messages": state["messages"] + [summary]}
        except Exception as e:
            err = str(e)[:300]
            if 0 <= idx < len(branches):
                branches[idx]["status"] = "failed"
            await _log("tot_backtrack", plan_name)
            await _log("tot_progress", f"Strategy failed: {plan_name}")
            summary = HumanMessage(content=f"[Strategy: {plan_name}] Failed with error: {err}")
            await _log("tot_message", summary.content)
            return {"errors": state.get("errors", []) + [err], "branches": branches, "messages": state["messages"] + [summary]}

    async def check_datapoints(state: ToTState) -> dict:
        final_answer = state.get("final_answer", "")
        if not final_answer:
            return {"datapoints_found": False}
        await _log("tot_phase", "Checking if response references data points...")
        prompt = f"""Determine whether the following agent response references specific data points: numbers, statistics, figures, values, facts, or derived data that came from the task and should be verified for accuracy.

            Response:
            {final_answer[:2000]}

            Reply with ONLY JSON: {{"has_datapoints": true}} if the response contains any concrete data/figures that warrant verification, otherwise {{"has_datapoints": false}}."""
        msg = HumanMessage(content=prompt)
        try:
            response = await llm.ainvoke([msg])
            content = _strip_json(response.content)
            data = json.loads(content)
            found = bool(data.get("has_datapoints", False))
        except Exception:
            found = False
        await _log("tot_progress", f"Data points detected: {found}")
        return {"datapoints_found": found}

    async def verify_data(state: ToTState) -> dict:
        final_answer = state.get("final_answer", "")
        await _log("tot_phase", "Verifying data points...")
        full_prompt = base_prompt + "\n\n" + f"""## Data Verification Task

        The agent produced the following result for the user's task:

        {final_answer[:3000]}

        Verify every data point, number, statistic, and interpretation in this result. Cross-check the figures using the available tools (browser, files, computation) as needed.

        Respond with ONLY JSON:
        {{
          "verified_datapoints": "The verified list of data points with confirmed, corrected, or unverifiable figures",
          "inconsistencies_found": true
        }}"""
        history = state["messages"]
        checkpointer = MemorySaver()
        thread_id = str(uuid.uuid4())
        agent = create_deep_agent(
            model=llm,
            tools=tools,
            backend=FilesystemBackend(root_dir=os.path.join(session_project_dir, "files"), virtual_mode=True),
            system_prompt=full_prompt,
            interrupt_on=INTERRUPT_TOOLS,
            checkpointer=checkpointer,
        )
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 1000}
        try:
            result = await _run_agent_with_hitl(agent, history, config)
            verified = _last_ai_text(result.get("messages", []))
            verified_datapoints = ""
            inconsistencies_found = False
            if verified:
                try:
                    data = json.loads(_strip_json(verified))
                    verified_datapoints = str(data.get("verified_datapoints", "") or "")
                    inconsistencies_found = bool(data.get("inconsistencies_found", False))
                except Exception:
                    verified_datapoints = verified
                    inconsistencies_found = True
            summary = HumanMessage(content=f"[Data verification] Inconsistencies found: {inconsistencies_found}\n{verified_datapoints or 'Verification completed.'}")
            await _log("tot_message", summary.content)
            await _log("tot_progress", f"Data verification complete. Inconsistencies found: {inconsistencies_found}")
            return {
                "verified_datapoints": verified_datapoints,
                "inconsistencies_found": inconsistencies_found,
                "messages": state["messages"] + [summary],
            }
        except Exception as e:
            err = str(e)[:300]
            await _log("tot_progress", f"Data verification failed: {err}")
            return {"errors": state.get("errors", []) + [err]}

    async def prepare_verified_data_for_feedback(state: ToTState) -> dict:
        final_answer = state.get("final_answer", "")
        verified_datapoints = state.get("verified_datapoints", "")
        await _log("tot_phase", "Merging verified data into the response...")
        full_prompt = base_prompt + "\n\n" + f"""## Consistency Merge Task

        Merge the verified data points into the original response to produce one coherent, consistent report.

        ### Original response:
        {final_answer[:4000]}

        ### Verified data points:
        {verified_datapoints[:4000]}

        Rules:
        1. Every factual claim, number, statistic, and inference in the final report must be coherent with the verified data points.
        2. Rewrite any inference that contradicts the verified data so it agrees with them.
        3. Remove completely any claim that cannot be reconciled with the verified data.
        4. Maintain the overall structure, tone, and completeness of the original response.
        5. Incorporate the verified figures where they add precision.

        Output the final coherent report as plain text (no JSON)."""
        history = state["messages"]
        checkpointer = MemorySaver()
        thread_id = str(uuid.uuid4())
        agent = create_deep_agent(
            model=llm,
            tools=tools,
            backend=FilesystemBackend(root_dir=os.path.join(session_project_dir, "files"), virtual_mode=True),
            system_prompt=full_prompt,
            interrupt_on=INTERRUPT_TOOLS,
            checkpointer=checkpointer,
        )
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 1000}
        try:
            result = await _run_agent_with_hitl(agent, history, config)
            merged = _last_ai_text(result.get("messages", []))
            summary = HumanMessage(content=f"[Consistency merge] Final coherent report:\n{merged or final_answer}")
            await _log("tot_message", summary.content)
            await _log("tot_progress", "Verified data merged into response.")
            return {
                "final_answer": merged or final_answer,
                "messages": state["messages"] + [summary],
            }
        except Exception as e:
            err = str(e)[:300]
            await _log("tot_progress", f"Consistency merge failed: {err}")
            return {"errors": state.get("errors", []) + [err]}

    async def feedback(state: ToTState) -> dict:
        final_answer = state.get("final_answer", "")
        branches = list(state["branches"])

        # If execution threw an exception (no final_answer), skip scoring
        if not final_answer:
            return {"branches": branches}

        # Save the final response to disk if not already saved
        update = {}
        saved_path = state.get("saved_final_path", "")
        already_saved = False
        if saved_path and os.path.isfile(saved_path):
            try:
                with open(saved_path, "r", encoding="utf-8") as f:
                    already_saved = f.read() == final_answer
            except Exception:
                already_saved = False
        if not already_saved:
            # Save the case study/report under a folder named after the user's prompt.
            report_dir = os.path.join(session_project_dir, "files")
            safe_name = re.sub(r'[^\w\-]+', '_', state.get("question", "report")).strip('_')[:40] or "report"
            report_dir = os.path.join(report_dir, safe_name)
            os.makedirs(report_dir, exist_ok=True)
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"case_study_{timestamp}.md"
            saved_path = os.path.join(report_dir, filename)
            report_text = (
                f"# Case Study: {state['question']}\n\n"
                f"- **Task**: {state['question']}\n"
                f"- **Plan used**: {state.get('selected_plan', '')}\n"
                f"- **Date**: {datetime.datetime.now().isoformat(timespec='seconds')}\n\n"
                f"## Steps\n"
                f"{chr(10).join(f'{i+1}. {s}' for i, s in enumerate(state.get('selected_steps', [])))}\n\n"
                f"## Report\n"
                f"{final_answer}"
            )
            with open(saved_path, "w", encoding="utf-8") as f:
                f.write(report_text)
            update["saved_final_path"] = saved_path
            await _log("tot_progress", f"Case study saved: {saved_path}")

        await _log("tot_phase", "Evaluating result quality...")
        eval_prompt = f"""Evaluate the quality of this result for the user's task.

User task: {state['question']}

Result:
{final_answer[:1000]}

Score the result 1-10 based on: completeness, accuracy, and usefulness.
Only score above 7 if the result fully and correctly addresses the task.
Respond in JSON: {{"score": 8, "reasoning": "Brief reasoning"}}"""
        msg = HumanMessage(content=eval_prompt)
        try:
            response = await llm.ainvoke([msg])
            content = _strip_json(response.content)
            data = json.loads(content)
            score = int(data.get("score", 0))
        except Exception:
            score = 0
        score = max(0, min(10, score))
        await _log("tot_progress", f"Result quality score: {score}/10")
        return {"feedback_score": score, "branches": branches, **update}

    def route_after_feedback(state: ToTState) -> str:
        final_answer = state.get("final_answer", "")
        score = state.get("feedback_score", 0)

        # Execution threw — no result to evaluate
        if not final_answer:
            if _pending_branches(state.get("branches", [])):
                return "select_plan"
            return "replan" if state.get("replan_count", 0) < 1 else END

        # Accept only if scored >= 7, otherwise ask the user how to proceed
        if score >= 7:
            return END
        return "ask_user_action"

    async def ask_user_action(state: ToTState) -> dict:
        await _log("tot_phase", "Result scored below 6 — asking user how to proceed...")
        options = [
            "1. Retry with an other strategy",
            "2. Recreate strategy from scratch",
            "3. I will provide more context",
            "4. Stop execution.",
        ]
        action = "recreate"
        if resolve_hitl is not None:
            decision = await resolve_hitl(
                "get_user_input_from_options",
                {"options": options},
                "The result scored below 6. Choose how to proceed:",
            )
            message = (decision.get("message") or "").strip()
            if message.startswith("1"):
                action = "retry"
            elif message.startswith("2"):
                action = "recreate"
            elif message.startswith("3"):
                action = "context"
            elif message.startswith("4"):
                action = "stop"
        await _log("tot_progress", f"User chose: {action}")

        update = {"user_action": action}
        if action == "context":
            await _log("tot_phase", "Waiting for additional context from user...")
            context = ""
            if resolve_hitl is not None:
                ctx_decision = await resolve_hitl(
                    "get_user_context",
                    {},
                    "Please provide the additional context for the task:",
                )
                context = (ctx_decision.get("message") or "").strip()
            if context:
                update["question"] = f"{state['question']}\n\nAdditional context from user:\n{context}"
                await _log("tot_progress", "Additional context received — recreating strategies.")
            else:
                await _log("tot_progress", "No context provided — recreating strategies as-is.")
            action = "recreate"
            update["user_action"] = action
        if action == "recreate":
            update["replan_count"] = state.get("replan_count", 0) + 1
        return update

    def route_after_user_action(state: ToTState) -> str:
        action = state.get("user_action", "")
        if action == "stop":
            return END
        if action == "retry":
            if _pending_branches(state.get("branches", [])):
                return "select_plan"
            return "replan" if state.get("replan_count", 0) < 1 else END
        return "replan"

    async def replan(state: ToTState) -> dict:
        await _log("tot_phase", "Replanning from failed strategies...")
        return {"replan_count": state.get("replan_count", 0) + 1}

    # ── BUILD GRAPH ───────────────────────────────
    workflow = StateGraph(ToTState)
    workflow.add_node("generate_plans", generate_plans)
    workflow.add_node("evaluate_plans", evaluate_plans)
    workflow.add_node("select_plan", select_plan)
    workflow.add_node("execute_plan", execute_plan)
    workflow.add_node("check_datapoints", check_datapoints)
    workflow.add_node("verify_data", verify_data)
    workflow.add_node("prepare_verified_data_for_feedback", prepare_verified_data_for_feedback)
    workflow.add_node("feedback", feedback)
    workflow.add_node("ask_user_action", ask_user_action)
    workflow.add_node("replan", replan)

    workflow.set_entry_point("generate_plans")
    workflow.add_edge("generate_plans", "evaluate_plans")
    workflow.add_edge("evaluate_plans", "select_plan")
    workflow.add_edge("select_plan", "execute_plan")
    workflow.add_edge("execute_plan", "check_datapoints")
    workflow.add_conditional_edges("check_datapoints", lambda state: "verify_data" if state.get("datapoints_found") else "feedback", {
        "verify_data": "verify_data",
        "feedback": "feedback",
    })
    workflow.add_conditional_edges("verify_data", lambda state: "prepare_verified_data_for_feedback" if state.get("inconsistencies_found") else "feedback", {
        "prepare_verified_data_for_feedback": "prepare_verified_data_for_feedback",
        "feedback": "feedback",
    })
    workflow.add_edge("prepare_verified_data_for_feedback", "feedback")
    workflow.add_conditional_edges("feedback", route_after_feedback, {
        "select_plan": "select_plan",
        "replan": "replan",
        "ask_user_action": "ask_user_action",
        END: END,
    })
    workflow.add_conditional_edges("ask_user_action", route_after_user_action, {
        "select_plan": "select_plan",
        "replan": "replan",
        END: END,
    })
    workflow.add_edge("replan", "generate_plans")

    return workflow.compile()

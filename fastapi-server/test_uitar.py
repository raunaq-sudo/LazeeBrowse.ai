#!/usr/bin/env python3

import argparse
import re

from mlx_vlm import load, generate


# ============================================================
# UI-TARS prompt
# ============================================================

SYSTEM_PROMPT = r"""
You are a GUI agent.

You are given a screenshot and a task.

Your job is to determine the NEXT action required.

IMPORTANT:
- Output ONLY ONE action.
- Do NOT output multiple actions.
- Do NOT repeat previous actions.
- Do NOT output tool results.
- Do NOT output Action 2, Action 3, etc.
- Do NOT output explanations after the action.
- Do NOT output finished() unless the task is actually complete.

## Output Format

Thought: <very short reasoning>
Action: <one action>

## Available Actions

click(start_box='<|box_start|>(x,y)<|box_end|>')

left_double(start_box='<|box_start|>(x,y)<|box_end|>')

right_single(start_box='<|box_start|>(x,y)<|box_end|>')

drag(start_box='<|box_start|>(x,y)<|box_end|>', end_box='<|box_start|>(x,y)<|box_end|>')

type(content='<text>')

hotkey(key='<key>')

scroll(start_box='<|box_start|>(x,y)<|box_end|>', direction='<up|down|left|right>')

wait()

finished()
"""


# ============================================================
# Dummy tools
# ============================================================

def dummy_click(x, y):
    print(f"[DUMMY TOOL] click(x={x}, y={y})")
    return "click executed"


def dummy_double_click(x, y):
    print(f"[DUMMY TOOL] double_click(x={x}, y={y})")
    return "double click executed"


def dummy_right_click(x, y):
    print(f"[DUMMY TOOL] right_click(x={x}, y={y})")
    return "right click executed"


def dummy_type(text):
    print(f"[DUMMY TOOL] type(text={text!r})")
    return "type executed"


def dummy_hotkey(key):
    print(f"[DUMMY TOOL] hotkey(key={key!r})")
    return "hotkey executed"


def dummy_scroll(direction):
    print(f"[DUMMY TOOL] scroll(direction={direction!r})")
    return "scroll executed"


def dummy_wait():
    print("[DUMMY TOOL] wait()")
    return "wait executed"


# ============================================================
# Parse ONE action
# ============================================================

def parse_action(output):

    # --------------------------------------------------------
    # Extract Action:
    # --------------------------------------------------------

    match = re.search(
        r"Action:\s*(.*?)(?:\n|$)",
        output,
        re.IGNORECASE,
    )

    if match:
        action_text = match.group(1).strip()
    else:
        # Sometimes the model omits "Action:"
        # and directly outputs click(...)
        match = re.search(
            r"(click|left_double|right_single|drag|type|hotkey|scroll|wait|finished)\s*\(",
            output,
            re.IGNORECASE,
        )

        if not match:
            return None

        action_text = output[match.start():]

    # Remove everything after the first closing action
    # so repeated hallucinated actions don't get parsed.
    action_text = action_text.split("\n")[0].strip()

    # --------------------------------------------------------
    # click
    # --------------------------------------------------------

    match = re.search(
        r"click\s*\(\s*start_box=['\"]"
        r"<\|box_start\|>\(\s*(\d+)\s*,\s*(\d+)\s*\)"
        r"<\|box_end\|>"
        r"['\"]\s*\)",
        action_text,
    )

    if match:
        return {
            "name": "click",
            "args": {
                "x": int(match.group(1)),
                "y": int(match.group(2)),
            },
        }

    # --------------------------------------------------------
    # double click
    # --------------------------------------------------------

    match = re.search(
        r"left_double\s*\(\s*start_box=['\"]"
        r"<\|box_start\|>\(\s*(\d+)\s*,\s*(\d+)\s*\)"
        r"<\|box_end\|>"
        r"['\"]\s*\)",
        action_text,
    )

    if match:
        return {
            "name": "left_double",
            "args": {
                "x": int(match.group(1)),
                "y": int(match.group(2)),
            },
        }

    # --------------------------------------------------------
    # right click
    # --------------------------------------------------------

    match = re.search(
        r"right_single\s*\(\s*start_box=['\"]"
        r"<\|box_start\|>\(\s*(\d+)\s*,\s*(\d+)\s*\)"
        r"<\|box_end\|>"
        r"['\"]\s*\)",
        action_text,
    )

    if match:
        return {
            "name": "right_single",
            "args": {
                "x": int(match.group(1)),
                "y": int(match.group(2)),
            },
        }

    # --------------------------------------------------------
    # type
    # --------------------------------------------------------

    match = re.search(
        r"type\s*\(\s*content=['\"](.*?)['\"]\s*\)",
        action_text,
        re.DOTALL,
    )

    if match:
        return {
            "name": "type",
            "args": {
                "text": match.group(1),
            },
        }

    # --------------------------------------------------------
    # hotkey
    # --------------------------------------------------------

    match = re.search(
        r"hotkey\s*\(\s*key=['\"](.*?)['\"]\s*\)",
        action_text,
    )

    if match:
        return {
            "name": "hotkey",
            "args": {
                "key": match.group(1),
            },
        }

    # --------------------------------------------------------
    # scroll
    # --------------------------------------------------------

    match = re.search(
        r"scroll\s*\("
        r".*?direction=['\"](up|down|left|right)['\"]"
        r".*?\)",
        action_text,
        re.IGNORECASE,
    )

    if match:
        return {
            "name": "scroll",
            "args": {
                "direction": match.group(1),
            },
        }

    # --------------------------------------------------------
    # wait
    # --------------------------------------------------------

    if re.search(r"wait\s*\(\s*\)", action_text):
        return {
            "name": "wait",
            "args": {},
        }

    # --------------------------------------------------------
    # finished
    # --------------------------------------------------------

    if re.search(r"finished\s*\(\s*\)", action_text):
        return {
            "name": "finished",
            "args": {},
        }

    return None


# ============================================================
# Execute dummy tool
# ============================================================

def execute(action):

    name = action["name"]
    args = action["args"]

    if name == "click":
        return dummy_click(**args)

    if name == "left_double":
        return dummy_double_click(**args)

    if name == "right_single":
        return dummy_right_click(**args)

    if name == "type":
        return dummy_type(**args)

    if name == "hotkey":
        return dummy_hotkey(**args)

    if name == "scroll":
        return dummy_scroll(**args)

    if name == "wait":
        return dummy_wait()

    if name == "finished":
        return "finished"

    return "unknown"


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "model",
        help="MLX UI-TARS model path",
    )

    parser.add_argument(
        "image",
        help="Screenshot path",
    )

    parser.add_argument(
        "instruction",
        help="Task",
    )

    parser.add_argument(
        "--steps",
        type=int,
        default=10,
    )

    args = parser.parse_args()

    print("\nLoading model...")
    model, processor = load(args.model)
    print("Model loaded.\n")

    # Only keep a concise history.
    history = []

    for step in range(1, args.steps + 1):

        print("=" * 60)
        print(f"STEP {step}")
        print("=" * 60)

        prompt = SYSTEM_PROMPT

        prompt += "\n\n## Task\n"
        prompt += args.instruction

        if history:

            prompt += "\n\n## Actions Already Executed\n"

            for action in history:
                prompt += f"- {action}"

        prompt += """

Now output exactly ONE next action.
"""

        result = generate(
            model,
            processor,
            prompt=prompt,
            image=args.image,
            max_tokens=80,
            temperature=0.0,
        )

        output = result.text.strip()

        print("\nMODEL OUTPUT:")
        print(output)

        action = parse_action(output)

        if action is None:
            print("\n[ERROR] Could not parse action.")
            break

        print("\nPARSED:")
        print(action)

        # ----------------------------------------------------
        # Finished
        # ----------------------------------------------------

        if action["name"] == "finished":

            print("\n[DUMMY TOOL] finished()")
            print("\nTask completed.")
            break

        # ----------------------------------------------------
        # Prevent exact repeated actions
        # ----------------------------------------------------

        action_signature = (
            action["name"],
            tuple(action["args"].items()),
        )

        if action_signature in history:

            print("\n[WARNING] Model repeated the same action.")
            print("Stopping to prevent an infinite loop.")
            break

        # ----------------------------------------------------
        # Execute dummy tool
        # ----------------------------------------------------

        result = execute(action)

        print(f"[RESULT] {result}")

        # ----------------------------------------------------
        # Store only the action, NOT the model's generated text
        # ----------------------------------------------------

        history.append(action_signature)

        print()


if __name__ == "__main__":
    main()

"""
Test the full multi-agent flow.
Run: python scripts/test_flow.py
"""
import asyncio
import httpx
import json
import time

BASE_URL = "http://localhost:8000"

async def test_full_flow():
    event_input = {
        "topic": "Artificial Intelligence and Machine Learning",
        "domain": "conference",
        "city": "Bangalore",
        "country": "India",
        "budget_usd": 500000,
        "target_audience": 1000,
        "dates": "2026-09-15 to 2026-09-17"
    }

    print("Starting conference planning...")
    async with httpx.AsyncClient(timeout=300) as client:

        # Start planning
        r = await client.post(f"{BASE_URL}/plan", json=event_input)
        r.raise_for_status()
        session = r.json()
        session_id = session["session_id"]
        print(f"Session ID: {session_id}")

        # Poll for completion
        while True:
            r = await client.get(f"{BASE_URL}/sessions/{session_id}")
            data = r.json()
            status = data.get("status", "unknown")
            print(f"Status: {status}")

            if data.get("logs"):
                for log in data["logs"][-3:]:  # last 3 logs
                    print(f"  {log}")

            if status == "completed":
                print("\n=== FINAL PLAN COMPLETED ===")
                plan = data.get("final_plan", {})
                
                # 1. Save entire final plan
                with open("final_plan.txt", "w", encoding="utf-8") as f:
                    # Write it as a clean integer without any artificial Python string truncation
                    f.write(json.dumps(plan, indent=2, default=str))
                print("- Saved full output to final_plan.txt")

                # 2. Extract out what is considered sub-agent outputs
                # Some keys map directly to agent outputs (e.g., 'venue_options', 'speakers')
                if isinstance(plan, str):
                    try:
                        plan = json.loads(plan)
                    except Exception:
                        pass
                
                if isinstance(plan, dict):
                    for key, val in plan.items():
                        try:
                            output_str = json.dumps(val, indent=2, default=str)
                        except Exception:
                            output_str = str(val)
                        
                        agent_file = f"{key}.txt"
                        with open(agent_file, "w", encoding="utf-8") as f:
                            f.write(output_str)
                        print(f"- Saved {key} data to {agent_file}")
                
                break
            elif status == "failed":
                print(f"Failed: {data.get('error')}")
                break
            await asyncio.sleep(2)

if __name__ == "__main__":
    asyncio.run(test_full_flow())
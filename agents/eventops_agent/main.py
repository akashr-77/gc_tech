# agents/eventops_agent/main.py
import uvicorn
from agents.eventops_agent.agent import EventOpsAgent

agent = EventOpsAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
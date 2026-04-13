import uvicorn
from agents.exhibitor_agent.agent import ExhibitorAgent

agent = ExhibitorAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)

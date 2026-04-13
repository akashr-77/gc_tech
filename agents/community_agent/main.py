import uvicorn
from agents.community_agent.agent import CommunityAgent

agent = CommunityAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8006)

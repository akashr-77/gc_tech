import uvicorn
from agents.speaker_agent.agent import SpeakerAgent

agent = SpeakerAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)

# agents/venue_agent/main.py
import uvicorn
from agents.venue_agent.agent import VenueAgent

agent = VenueAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
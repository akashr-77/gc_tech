import uvicorn
from agents.pricing_agent.agent import PricingAgent

agent = PricingAgent()
app = agent.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)

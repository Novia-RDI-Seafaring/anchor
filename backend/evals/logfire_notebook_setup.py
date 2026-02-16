import os
import logfire
from dotenv import load_dotenv

# 1. Load environment variables from .env
# Adjust path if your notebook is in a different directory
load_dotenv("../.env") 

# 2. Configure Logfire
token = os.getenv("LOGFIRE_TOKEN")
if token and token != "None":
    logfire.configure(token=token)
    print("Logfire configured with token.")
else:
    logfire.configure(send_to_logfire=False)
    print("Logfire configured for console output (no token found).")

# 3. Instrument Pydantic AI (important for LLM tracking)
logfire.instrument_pydantic_ai()

print("Ready to track LLM output and context!")

from dotenv import load_dotenv
import os
from google import genai

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
print("KEY LOADED:", key[:15] if key else "NONE")

client = genai.Client(api_key=key)

interaction = client.interactions.create(
    model="gemini-3.6-flash",
    input="Say hello in one word"
)

print(interaction.output_text)
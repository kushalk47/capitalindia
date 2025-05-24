# chatbot_service/chatbot.py
import google.generativeai as genai
import os
import io
from PIL import Image
import time
import random

class GeminiChatbot:
    def __init__(self, api_keys: list[str]): # Accept a list of API keys
        if not api_keys:
            raise ValueError("No API keys provided for GeminiChatbot.")
        self.api_keys = api_keys
        self.current_key_index = 0
        self.max_retries_per_call = len(self.api_keys) # Try all keys if one fails
        self.model_text = None
        self.model_vision = None
        self.chat = None
        self._configure_gemini() # Initial configuration with the first key

        print("GeminiChatbot initialized successfully with multiple API keys.")

    def _configure_gemini(self):
        """Configures genai with the current API key."""
        if not self.api_keys:
            raise ValueError("No API keys available to configure GeminiChatbot.")

        current_api_key = self.api_keys[self.current_key_index]
        genai.configure(api_key=current_api_key)
        
        # Re-initialize models and chat history when switching keys
        # This is important to ensure the new configuration takes effect.
        self.model_text = genai.GenerativeModel('gemini-1.5-flash')
        self.model_vision = genai.GenerativeModel('gemini-1.5-flash')
        self.chat = self.model_text.start_chat(history=[])
        print(f"Gemini configured with key from index: {self.current_key_index}")


    def _rotate_api_key(self):
        """Rotates to the next API key in the list."""
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        print(f"Rotating to next API key. New index: {self.current_key_index}")
        self._configure_gemini() # Re-configure with the new key

    def _make_gemini_call(self, call_type: str, *args, **kwargs):
        """
        Generic method to handle Gemini API calls with key rotation and retries.
        """
        for attempt in range(self.max_retries_per_call):
            try:
                if call_type == "text_query":
                    # Use the configured chat instance
                    response = self.chat.send_message(*args, **kwargs)
                elif call_type == "vision_analysis":
                    # Use the configured vision model
                    response = self.model_vision.generate_content(*args, **kwargs)
                else:
                    raise ValueError(f"Unknown call_type: {call_type}")
                return response # If successful, return response

            except Exception as e:
                error_message = str(e).lower()
                print(f"Attempt {attempt + 1} with API key index {self.current_key_index} failed: {e}")

                # Check for rate limit specific errors or common API errors
                if "rate limit" in error_message or "quota" in error_message or "429" in error_message or "resource exhausted" in error_message:
                    print("Rate limit likely hit. Rotating API key...")
                    self._rotate_api_key()
                    # A small delay before retrying with the new key
                    time.sleep(1 + random.random() * 0.5) # Add some randomness
                else:
                    # For other types of errors, still rotate to see if it's key-related,
                    # but maybe raise immediately or after fewer retries.
                    print("Non-rate limit error encountered. Rotating API key for next attempt.")
                    self._rotate_api_key()
                    time.sleep(0.5 + random.random() * 0.2) # Shorter delay for non-rate limit errors
                    # If this is the last attempt and it's not a rate limit, re-raise the error.
                    if attempt == self.max_retries_per_call - 1:
                        raise # Re-raise the original error if all keys fail

        raise Exception("All API keys failed after multiple attempts.")


    def send_text_query(self, user_query: str) -> str:
        """
        Sends a text query to the Gemini text model, utilizing chat history,
        with API key rotation and retries.
        """
        try:
            response = self._make_gemini_call("text_query", user_query)
            return response.text
        except Exception as e:
            print(f"Error getting text response from Gemini after all retries: {e}")
            return f"Sorry, I couldn't process your text request. Error: {e}"

    def analyze_chart_image(self, image: Image.Image, user_query: str) -> str:
        """
        Analyzes a chart image using the Gemini Vision model, with API key rotation and retries.
        """
        if not image:
            raise ValueError("No PIL Image object provided for analysis.")

        try:
            contents = [user_query, image]
            response = self._make_gemini_call("vision_analysis", contents)

            if response and response.text:
                return response.text
            else:
                return "AI analysis could not generate a response. Please try again or with a clearer chart."

        except Exception as e:
            print(f"ERROR in analyze_chart_image (GeminiChatbot) after all retries: {e}")
            import traceback
            traceback.print_exc()
            raise ValueError(f"Failed to analyze image with AI: {e}")
from flask import Flask, render_template, request, jsonify
import json
import re
import requests
import pandas as pd
from functools import lru_cache
import os
from datetime import datetime

# Initialize the Flask app
app = Flask(__name__)

# Replace with your DeepSeek API key
DEEPSEEK_API_KEY = "sk-70b2c28863fc45b69315790475179f13"
DEEPSEEK_API_ENDPOINT = "https://api.deepseek.com/v1/chat/completions"  # Replace with the actual API endpoint

# Path to the Excel file
EXCEL_FILE_PATH = "../../alumni_seminars_withid.xlsx"
JSON_FILE_PATH = "seminars.json"

def load_seminars_from_excel():
    """
    Load seminars from the Excel file and save them as a JSON file.
    """
    try:
        # Read the Excel file
        df = pd.read_excel(EXCEL_FILE_PATH)
        
        # Debug: Print the first few rows of the DataFrame
        print("First few rows of the Excel file:")
        print(df.head())
        
        # Manually parse the 'Date' column if needed
        df["Date"] = pd.to_datetime(df["Date"])
        
        # Replace NaN values with empty strings for Slides, Video, and Audio
        df["Slides"] = df["Slides"].fillna(" ")
        df["Video"] = df["Video"].fillna(" ")
        df["Audio"] = df["Audio"].fillna(" ")
        
        # Convert the DataFrame to a list of dictionaries
        seminars = df.to_dict(orient='records')
        
        # Debug: Print the first few seminars
        print("First few seminars:")
        print(seminars[:5])
        
        # Save the seminars as a JSON file
        if seminars:
            with open(JSON_FILE_PATH, "w", encoding="utf-8") as file:
                json.dump(seminars, file, ensure_ascii=False, indent=4, default=str)  # Use default=str to handle datetime objects
            print("JSON file created/updated successfully.")
        else:
            print("Warning: No seminars found in the Excel file. JSON file not created.")
        return seminars
    except Exception as e:
        print(f"Error loading seminars from Excel: {e}")
        return []

def load_seminars_from_json():
    """
    Load seminars from the JSON file.
    """
    try:
        with open(JSON_FILE_PATH, "r", encoding="utf-8") as file:
            seminars = json.load(file)
        
        # Debug: Print the first few seminars from the JSON file
        print("First few seminars from JSON file:")
        print(seminars[:5])
        
        # Convert the 'Date' strings back to datetime objects
        for seminar in seminars:
            seminar["Date"] = pd.to_datetime(seminar["Date"])
        print("JSON file loaded successfully.")
        return seminars
    except Exception as e:
        print(f"Error loading seminars from JSON: {e}")
        return []

def should_recreate_json():
    """
    Check if the JSON file should be recreated based on the timestamps of the Excel and JSON files.
    """
    if not os.path.exists(JSON_FILE_PATH):
        # If the JSON file doesn't exist, recreate it
        return True

    # Get the modification timestamps of both files
    excel_timestamp = os.path.getmtime(EXCEL_FILE_PATH)
    json_timestamp = os.path.getmtime(JSON_FILE_PATH)

    # If the Excel file is newer than the JSON file, recreate the JSON file
    return excel_timestamp > json_timestamp

# Load seminars data when the server starts
if should_recreate_json():
    seminars = load_seminars_from_excel()
else:
    seminars = load_seminars_from_json()

# Convert seminars to JSON string for caching
seminars_json = json.dumps(seminars, ensure_ascii=False, default=str)  # Use default=str to handle datetime objects

# Cache for storing API responses
@lru_cache(maxsize=100)
def cached_chat_with_deepseek(query, seminars_json, conversation_history):
    """
    Cache the results of DeepSeek API calls to avoid redundant requests.
    :param query: The user's query.
    :param seminars_json: JSON string of the seminars data.
    :param conversation_history: List of previous messages in the conversation.
    :return: The response from DeepSeek.
    """
    # Prepare the prompt for DeepSeek
    prompt = f"""
    You are a helpful assistant that provides information about seminars.
    Here is the list of seminars in JSON format: {seminars_json}
    The user has asked: {query}
    Please provide a helpful and conversational response.
    If the response contains information about a seminar, return the IDs of the matching seminars in JSON format like json{{'seminars':[1,2,3]}}.
    """

    # Prepare the request payload for DeepSeek API
    messages = [
        {"role": "system", "content": "You are a helpful assistant that provides information about seminars. If the response contains information about a seminar, return the IDs of the matching seminars in JSON format like json{'seminars':[1,2,3]}. Consider the conversation history when responding."}
    ]
    # Add conversation history to the payload
    for role, content in conversation_history:
        messages.append({"role": role, "content": content})
    # Add the current user query
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": "deepseek-chat",  # Replace with the appropriate model name
        "messages": messages,
        "max_tokens": 8000  # Increase the token limit
    }

    # Make the API request to DeepSeek
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    response = requests.post(
        DEEPSEEK_API_ENDPOINT,
        headers=headers,
        json=payload
    )

    # Check if the request was successful
    if response.status_code == 200:
        if "application/json" in response.headers.get("Content-Type", ""):
            try:
                # Parse the response content as JSON
                results = response.json()
                # Extract the response content
                response_content = results["choices"][0]["message"]["content"]
                print("DeepSeek response:", response_content)  # Debug print
                return response_content
            except KeyError as e:
                return "Error: The API response is missing required fields."
        else:
            return "Error: API returned non-JSON response."
    else:
        return f"Error: {response.status_code} - {response.text}"

def handle_local_query(query, seminars):
    """
    Handle simple queries locally without calling the API.
    :param query: The user's query.
    :param seminars: List of seminars as Python dictionaries.
    :return: A response if the query can be handled locally, otherwise None.
    """
    # Example: Handle queries about the total number of seminars
    if "how many seminars in total" in query.lower():
        return f"There are {len(seminars)} seminars in total."

    # Example: Handle queries about the number of seminars in a specific year
    if "how many seminars in" in query.lower():
        try:
            # Extract the year from the query
            year_match = re.search(r"\d{4}", query)
            if year_match:
                year = year_match.group(0)
                # Filter seminars for the specified year
                seminars_in_year = [
                    seminar for seminar in seminars
                    if pd.to_datetime(seminar["Date"]).year == int(year)
                ]
                return f"There are {len(seminars_in_year)} seminars in {year}."
            else:
                return "Sorry, I couldn't understand the year in your query."
        except Exception as e:
            print(f"Error handling year-based query: {e}")
            return "Sorry, I couldn't understand the year in your query."

    # Example: Handle queries about a specific speaker
    if "who is speaking on" in query.lower() or "speaker for" in query.lower():
        try:
            # Extract the seminar title from the query
            title = re.search(r"on (.+)\?", query).group(1)
            # Find the seminar with the matching title
            seminar = next((seminar for seminar in seminars if title.lower() in seminar["Title"].lower()), None)
            if seminar:
                return f"The speaker for '{seminar['Title']}' is {seminar['Speaker']}."
            else:
                return f"Sorry, I couldn't find a seminar with the title '{title}'."
        except:
            return "Sorry, I couldn't understand your query."

    # If the query cannot be handled locally, return None
    return None

# Global conversation history
conversation_history = []

@app.route("/")
def home():
    """Render the chat interface."""
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    """Handle user queries and return chatbot responses."""
    global conversation_history, seminars_json  # Declare seminars_json as global

    # Get the user's query from the request
    query = request.json.get("query")
    if not query:
        return jsonify({"response": "Error: No query provided."})

    print(f"Received query: {query}")  # Debug print

    # Try to handle the query locally first
    local_response = handle_local_query(query, seminars)
    if local_response:
        print(f"Local response: {local_response}")  # Debug print
        # Add the user query and chatbot response to the conversation history
        conversation_history.append(("user", query))
        conversation_history.append(("assistant", local_response))
        return jsonify({"response": local_response, "type": "text"})

    # If the query cannot be handled locally, call the DeepSeek API
    response = cached_chat_with_deepseek(query, seminars_json, tuple(conversation_history))
    print(f"DeepSeek API response: {response}")  # Debug print

    # Check if the response contains JSON data (IDs of matching seminars)
    try:
        # Extract the JSON object containing the list of IDs
        json_match = re.search(r'json\s*\{([\s\S]*?)\}', response)
        if json_match:
            # Parse the JSON object
            json_data = json.loads(f'{{{json_match.group(1)}}}')
            if "seminars" in json_data:
                # Fetch the full seminar details based on the IDs
                matching_seminars = [seminar for seminar in seminars if seminar["Id"] in json_data["seminars"]]
                if matching_seminars:
                    # Convert the 'Date' field to a datetime object if it's a string
                    for seminar in matching_seminars:
                        if isinstance(seminar["Date"], str):
                            seminar["Date"] = pd.to_datetime(seminar["Date"])
                        # Convert the datetime object to an ISO format string
                        seminar["Date"] = seminar["Date"].isoformat()
                    # Return the full seminar details as JSON
                    return jsonify({"response": matching_seminars, "type": "seminars"})
    except json.JSONDecodeError:
        pass  # Response is not JSON, treat it as plain text

    # Add the user query and chatbot response to the conversation history
    conversation_history.append(("user", query))
    conversation_history.append(("assistant", response))

    # Limit the conversation history to the last 10 messages (adjust as needed)
    if len(conversation_history) > 10:  # 5 user + 5 assistant messages
        conversation_history = conversation_history[-10:]

    # Default to plain text response
    return jsonify({"response": response, "type": "text"})

if __name__ == "__main__":
    app.run(debug=True)

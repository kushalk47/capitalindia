CapitalIndia - Stock Analysis Chatbot
Overview
CapitalIndia is a FastAPI-based application designed to provide stock market insights through a Retrieval-Augmented Generation (RAG) chatbot. The chatbot processes user queries about Tesla stock data, converts them into database queries, and leverages the Gemini model to generate meaningful responses. The application also includes features for candlestick pattern analysis, such as resistance levels, to assist with technical analysis.
Features

Chatbot Interface: Accepts natural language queries about Tesla stock data (e.g., "What is the average closing price?" or "What is the highest closing price?").
RAG Agent: Combines a custom parser with the Gemini model to convert user prompts into database queries and generate responses.
Database Integration: Stores and queries Tesla stock data for accurate and real-time insights.
Candlestick Pattern Analysis: Identifies key patterns, such as resistance levels, to support technical stock analysis.
FastAPI Backend: Provides a robust and scalable API for handling user requests and responses.

capitalindia/
├── chatbotervice/
│   ├── chatbot.py       # Main chatbot logic for handling user queries and responses
│   └── parser.py        # Converts user prompts into database queries
├── database/            # Contains Tesla stock data and database schema
├── requirements.txt     # Project dependencies
└── main.py              # FastAPI application entry point

Installation

Clone the Repository:
git clone https://github.com/kushalk47/capitalindia.git
cd capitalindia


Set Up a Virtual Environment:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate


Install Dependencies:
pip install -r requirements.txt


Configure the Database:

Ensure the Tesla stock database is set up (e.g., SQLite, PostgreSQL, or other supported DB).
Update the database connection settings in the configuration file or environment variables.


Run the Application:
uvicorn main:app --reload


Access the API:

The FastAPI application will be available at http://localhost:8000.
Use the /docs endpoint to access the interactive API documentation (Swagger UI).



Usage

Querying Stock Data:

Send queries to the chatbot via the API or a frontend interface (if implemented).
Example queries:
"What is the average closing price of Tesla stock?"
"What is the highest closing price in the last month?"
"Show me the resistance levels for Tesla stock."




Candlestick Pattern Analysis:

The application identifies resistance levels and other candlestick patterns to provide technical insights.
Access these features through specific API endpoints or integrated chatbot responses.



Example API Request
curl -X POST "http://localhost:8000/chat" -H "Content-Type: application/json" -d '{"query": "What is the average closing price of Tesla stock?"}'

Dependencies

FastAPI: For building the API server.
Uvicorn: ASGI server for running the FastAPI application.
SQLAlchemy: For database interactions (if used).
Gemini API: For natural language processing and response generation.
Python 3.8+: Required for running the application.

Future Improvements

Add support for additional stock data (beyond Tesla).
Enhance candlestick pattern recognition with more advanced technical indicators.
Implement a frontend interface for easier user interaction.
Optimize database queries for faster response times.

Contributing
Contributions are welcome! Please fork the repository, create a new branch, and submit a pull request with your changes.
License
This project is licensed under the MIT License.
Contact
For any questions or issues, please reach out via GitHub Issues.

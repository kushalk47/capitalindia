# chatbot_service/parser.py

from sqlalchemy.orm import Session
from sqlalchemy import text 
import calendar 
import datetime # Keep this global import for other uses like parsing dates if needed

from models import StockData 
from .chatbot import GeminiChatbot # This import remains the same

class QueryParser:
    def __init__(self, db: Session, gemini_chatbot: GeminiChatbot):
        self.db = db
        self.gemini_chatbot = gemini_chatbot 

        self.db_schema = """
        You are interacting with a SQLite database named 'tesla_stock.db'.
        The database contains a single table named 'tesla_stock'.
        The schema for the 'tesla_stock' table is as follows:

        CREATE TABLE tesla_stock (
            id INTEGER PRIMARY KEY,
            timestamp DATE UNIQUE,
            open_price REAL,
            high_price REAL,
            low_price REAL,
            close_price REAL,
            volume INTEGER,
            direction TEXT, -- 'LONG' or 'SHORT'
            support_lower REAL,
            support_upper REAL,
            resistance_lower REAL,
            resistance_upper REAL
        );

        When referencing dates, use the 'timestamp' column. SQLite date comparisons work directly on 'YYYY-MM-DD' strings.
        For example, to filter by year, use `strftime('%Y', timestamp) = '2023'`.
        To filter by month, use `strftime('%m', timestamp) = '01'` (for January).
        To filter by date range, use `timestamp BETWEEN 'YYYY-MM-DD' AND 'YYYY-MM-DD'`.
        """
        
        self.forbidden_keywords = [
            "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "CREATE",
            "REPLACE", "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
            ";" # Keep this to prevent multi-statement SQL unless you explicitly want to allow it later
        ]

    def _get_sql_from_gemini(self, user_query: str) -> str | None:
        prompt = f"""
        You are an AI assistant that converts natural language questions into SQL queries for a stock database.
        Use the provided database schema to write accurate and efficient SQL queries.
        
        {self.db_schema}

        Rules for SQL Generation:
        - Generate ONLY the SQL query. Do NOT include any explanations, comments, or extra text.
        - Ensure the query is syntactically correct for SQLite.
        - Only generate SELECT queries. Do NOT generate any DDL (CREATE, ALTER, DROP) or DML (INSERT, UPDATE, DELETE) statements.
        - If the query cannot be answered by a single, valid SQL statement, return "N/A".
        - For queries that might return many rows (e.g., "all closing prices"), include a LIMIT clause (e.g., LIMIT 10).
        - For aggregate functions, use appropriate SQLite functions like MIN, MAX, AVG, COUNT, SUM.
        - When a comparison is requested (e.g., "compare X vs Y"), strive to generate a single SELECT query that returns both X and Y as separate columns, possibly using subqueries or conditional aggregation. For example:
          `SELECT (SELECT AVG(volume) FROM tesla_stock WHERE strftime('%Y', timestamp) = '2022') AS avg_2022_volume, (SELECT AVG(volume) FROM tesla_stock WHERE strftime('%Y', timestamp) = '2023') AS avg_2023_volume;`
        - For month names in natural language, convert them to their corresponding 'MM' number (e.g., January -> '01').

        User query: "{user_query}"

        SQL Query:
        """
        try:
            # This call will now automatically handle key rotation and retries
            response = self.gemini_chatbot.model_text.generate_content(prompt) 
            sql_query = response.text.strip()
            
            if sql_query.startswith("```sql"):
                sql_query = sql_query[len("```sql"):].strip()
            if sql_query.endswith("```"):
                sql_query = sql_query[:-len("```")].strip()

            # Enhanced check for forbidden keywords and multiple statements
            # We explicitly allow the ';' at the end of a single statement, but not multiple ';' inside
            normalized_query = sql_query.strip().upper()
            if normalized_query.endswith(';'):
                normalized_query = normalized_query[:-1].strip() # Remove trailing semicolon for internal check

            for keyword in self.forbidden_keywords:
                # Ensure we don't catch a legitimate part of a column name or string
                # This simple check is usually sufficient but can be improved with regex word boundaries
                if keyword in normalized_query:
                    print(f"Warning: Forbidden keyword '{keyword}' detected in generated SQL.")
                    return None 
            
            # Check for multiple statements by looking for semicolons NOT at the very end
            if ';' in sql_query.strip(';').strip(): # This remains strict to prevent multiple statements
                print("Warning: Multiple statements detected in generated SQL.")
                return None

            if not sql_query: # Check if Gemini returned an empty string
                return None

            return sql_query
        except Exception as e:
            print(f"Error generating SQL from Gemini: {e}")
            return None

    def parse_and_execute(self, user_query: str) -> dict:
        # No hardcoded logic here for now, we rely solely on Gemini's SQL generation
        generated_sql = self._get_sql_from_gemini(user_query)

        if not generated_sql or "N/A" in generated_sql.upper():
            print(f"Gemini did not generate valid SQL for: {user_query}")
            return {"type": "gemini_response", "content": "I apologize, but I couldn't generate a valid SQL query to answer that. Could you please rephrase or ask a simpler question about the stock data?"}

        try:
            result = self.db.execute(text(generated_sql))
            rows = result.fetchall()
            
            if not rows:
                return {"type": "db_response", "content": "I couldn't find any data matching your query."}

            response_parts = []
            
            # Check if the query returned specific column names for a comparison, e.g., 'avg_2022_volume', 'avg_2023_volume'
            column_names_list = result.keys() 
            if len(rows) == 1 and all(col.startswith('avg_') and col.endswith('_volume') for col in column_names_list):
                    # This is a specific handler for the 'compare average volume' type of query
                avg_2022 = rows[0]._mapping.get('avg_2022_volume')
                avg_2023 = rows[0]._mapping.get('avg_2023_volume')

                if avg_2022 is not None and avg_2023 is not None:
                    comparison_text = f"The average daily volume in 2022 was {avg_2022:,.0f} and in 2023 it was {avg_2023:,.0f}."
                    if avg_2023 > avg_2022:
                        diff = avg_2023 - avg_2022
                        comparison_text += f" This is an increase of {diff:,.0f}."
                    elif avg_2023 < avg_2022:
                        diff = avg_2022 - avg_2023
                        comparison_text += f" This is a decrease of {diff:,.0f}."
                    response_parts.append(comparison_text)
                else:
                    response_parts.append("I retrieved some data but couldn't interpret the comparison for average volumes.")
            elif len(rows) == 1 and len(rows[0]) == 1:
                # Single aggregate value (e.g., COUNT, AVG, MIN, MAX)
                value = rows[0][0] 
                import builtins 
                if builtins.isinstance(value, (builtins.float, builtins.int)): 
                    if "volume" in user_query.lower() or "count" in user_query.lower():
                        response_parts.append(f"The result is: {value:,.0f}")
                    else:
                        response_parts.append(f"The result is: ${value:,.2f}")
                else:
                    response_parts.append(f"The result is: {value}")
            elif len(rows) > 0:
                # Multiple rows or columns
                
                response_parts.append("Here's what I found:")
                
                max_display_rows = 10
                for i, row in enumerate(rows):
                    if i >= max_display_rows:
                        response_parts.append(f"... (and {len(rows) - max_display_rows} more results. Please refine your query for specific data.)")
                        break
                    
                    row_str_parts = []
                    for col_name in column_names_list:
                        col_val = row._mapping[col_name] 
                        display_col_name = col_name.replace('_', ' ').title()
                        
                        formatted_val = "N/A" 
                        import builtins 
                        import datetime as dt 
                        
                        try: 
                            if col_val is None:
                                formatted_val = "N/A"
                            elif builtins.isinstance(col_val, builtins.float):
                                formatted_val = f"${col_val:,.2f}"
                            elif builtins.isinstance(col_val, builtins.int):
                                if 'volume' in display_col_name.lower() or 'id' in display_col_name.lower():
                                    formatted_val = f"{col_val:,.0f}"
                                else:
                                    formatted_val = builtins.str(col_val) 
                            elif builtins.isinstance(col_val, dt.date): 
                                formatted_val = col_val.strftime('%Y-%m-%d')
                            elif builtins.isinstance(col_val, builtins.str): 
                                formatted_val = col_val
                            else: 
                                formatted_val = builtins.str(col_val)
                        except TypeError as te:
                            print(f"!!! DEBUG: TypeError in formatting for col_name='{col_name}', col_val='{col_val}' (type: {type(col_val)})")
                            print(f"!!! DEBUG: Error: {te}")
                            formatted_val = f"ERROR_FORMATTING({type(col_val)})"
                            
                        row_str_parts.append(f"{display_col_name}: {formatted_val}")

                    response_parts.append(" - " + ", ".join(row_str_parts))
                
            return {"type": "db_response", "content": "\n".join(response_parts)}

        except Exception as e:
            print(f"Error executing generated SQL or formatting results: {e}")
            print(f"Failed SQL Query: {generated_sql}")
            return {"type": "gemini_response", "content": "I encountered an error trying to retrieve that data from the database. Please try rephrasing your query."}
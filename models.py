import os
import pandas as pd
from sqlalchemy import create_engine, Column, Integer, String, Date, Float
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# --- Database Configuration ---
DATABASE_FILE = "tesla_stock.db"
DATABASE_URL = f"sqlite:///{DATABASE_FILE}"
# IMPORTANT: Make sure your CSV file is named "TSLA stock data.csv" or update this path
CSV_FILE = "cleaneddata.csv"

# Create a SQLAlchemy engine
engine = create_engine(DATABASE_URL)

# Base class for declarative models
Base = declarative_base()

# Configure sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Define the StockData Model ---
class StockData(Base):
    __tablename__ = "tesla_stock"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(Date, unique=True, nullable=False)
    direction = Column(String, nullable=True) # Can be 'LONG', 'SHORT', or NULL
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Integer, nullable=False)

    # Pre-calculated min/max for support and resistance bands
    support_lower = Column(Float, nullable=True) # Will be NULL if no support values
    support_upper = Column(Float, nullable=True)
    resistance_lower = Column(Float, nullable=True)
    resistance_upper = Column(Float, nullable=True)

    def __repr__(self):
        return f"<StockData(timestamp='{self.timestamp}', close={self.close_price})>"

# --- Database Initialization and Data Ingestion Logic ---
def initialize_database():
    """
    Creates tables if they don't exist and populates data from CSV if the table is empty.
    """
    Base.metadata.create_all(engine) # Create all tables defined in Base

    db = SessionLocal()
    try:
        # Check if the table is empty
        if db.query(StockData).count() == 0:
            print(f"Database table '{StockData.__tablename__}' is empty. Importing data from '{CSV_FILE}'...")
            import_data_from_csv(db)
            print("Data import complete.")
        else:
            print(f"Database table '{StockData.__tablename__}' already contains data. Skipping CSV import.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        # Rollback in case of error to leave the DB in a consistent state
        db.rollback()
    finally:
        db.close()

def import_data_from_csv(db):
    """
    Reads data from the CSV file and populates the database.
    """
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(f"CSV file not found at: {CSV_FILE}. Please ensure it's in the same directory.")

    df = pd.read_csv(CSV_FILE)

    # Clean column names to remove leading/trailing spaces if any
    df.columns = df.columns.str.strip()

    # --- Crucial check: Verify expected columns are present ---
    expected_columns = ['timestamp', 'direction', 'Support', 'Resistance', 'open', 'high', 'low', 'close', 'volume']
    if not all(col in df.columns for col in expected_columns):
        missing_cols = [col for col in expected_columns if col not in df.columns]
        raise ValueError(f"CSV is missing expected columns: {missing_cols}. Please check your CSV file header.")

    # Data cleaning and type conversion
    df['timestamp'] = pd.to_datetime(df['timestamp']).dt.date # Convert to date objects

    # Rename columns to match model attributes for direct mapping
    df.rename(columns={
        'open': 'open_price',
        'high': 'high_price',
        'low': 'low_price',
        'close': 'close_price'
    }, inplace=True)

    # Process Support and Resistance columns
    stock_data_to_add = []
    for index, row in df.iterrows():
        # Function to parse list string and get min/max
        def parse_min_max_list(list_str):
            # Ensure it's treated as a string, handle NaN/None
            if pd.isna(list_str) or not str(list_str).strip('[]').strip():
                return None, None
            try:
                # Remove brackets, split by comma, convert to float, filter out empty strings
                values = [float(val.strip()) for val in str(list_str).strip('[]').split(',') if val.strip()]
                if values:
                    return min(values), max(values)
                return None, None
            except ValueError:
                print(f"Warning: Could not parse list string: '{list_str}' at timestamp {row['timestamp']}. Skipping support/resistance for this row.")
                return None, None

        min_support, max_support = parse_min_max_list(row.get('Support'))
        min_resistance, max_resistance = parse_min_max_list(row.get('Resistance'))

        stock_data_to_add.append(StockData(
            timestamp=row['timestamp'],
            # Ensure direction is None if NaN/empty, otherwise its string value
            direction=row['direction'] if pd.notna(row['direction']) and str(row['direction']).strip() != '' else None,
            open_price=row['open_price'],
            high_price=row['high_price'],
            low_price=row['low_price'],
            close_price=row['close_price'],
            volume=row['volume'],
            support_lower=min_support,
            support_upper=max_support,
            resistance_lower=min_resistance,
            resistance_upper=max_resistance,
        ))
    
    # Debugging: Print a few rows to ensure data looks correct before bulk insert
    # print("\n--- Sample data to be inserted ---")
    # for i, item in enumerate(stock_data_to_add[:5]): # Print first 5 items
    #     print(f"Row {i+1}: Timestamp={item.timestamp}, Direction={item.direction}, Close={item.close_price}, S_Lower={item.support_lower}, R_Upper={item.resistance_upper}")
    # print("----------------------------------\n")

    db.bulk_save_objects(stock_data_to_add) # More efficient for many objects
    db.commit()

# Dependency for FastAPI to get a database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# This block will run when models.py is imported or executed directly
if __name__ == "__main__":
    print("Running models.py directly for database initialization...")
    # First, delete the old DB file to ensure a clean start if there was an error
    if os.path.exists(DATABASE_FILE):
        os.remove(DATABASE_FILE)
        print(f"Removed existing database file: {DATABASE_FILE}")
    
    initialize_database()
    print("Database initialization process finished.")
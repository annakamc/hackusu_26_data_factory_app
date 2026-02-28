"""
Quick diagnostic: check RemainingUsefulLife values in the engine table.
Usage:
  python scripts/check_rul.py

Make sure env vars for Databricks are set (or run locally with SQLite mock after running database/setup_db.py).
"""
import os
from services import db_service

def main():
    print("Engine table:", db_service.ENGINE_TABLE)
    try:
        # Use the same function used by the app
        df = db_service._sql_query(f"SELECT id, Cycle, RemainingUsefulLife FROM {db_service.ENGINE_TABLE} LIMIT 100")
    except Exception as e:
        print("Query failed:", e)
        return

    if df.empty:
        print("No rows returned.")
        return

    print(df.head(10).to_string(index=False))
    col = "RemainingUsefulLife"
    if col not in df.columns:
        print(f"Column '{col}' not present in result: {list(df.columns)}")
        return

    print("\nSummary:")
    try:
        print(df[col].describe())
    except Exception:
        print("Could not describe column (non-numeric type)")

    zeros = (df[col] == 0).sum()
    total = len(df)
    print(f"Zeros: {zeros} / {total} ({zeros/total:.2%})")

if __name__ == '__main__':
    main()

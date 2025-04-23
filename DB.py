import psycopg2
import os
import sys
import hashlib
from datetime import datetime, timezone, timedelta

def get_db_connection(DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD):
    """Establishes connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        print("Database connection successful.")
        return conn
    except psycopg2.Error as e:
        print(f"ERROR: Unable to connect to the database: {e}")
        sys.exit(1)

def store_verification_data(conn, source_data, claim_data, evaluation_data, evidence_list, GEMINI_MODEL_NAME):
    """Stores all collected data into the database using a transaction."""
    cursor = None
    try:
        cursor = conn.cursor()
        print(f"Storing data for source URL: {source_data['source_url']}")
        # 1. Check/Insert Source
        cursor.execute("SELECT source_id FROM Sources WHERE source_url = %s", (source_data['source_url'],))
        existing_source = cursor.fetchone()
        if existing_source:
            source_id = existing_source[0]
            print(f"Source already exists with ID: {source_id}. Skipping Source insertion.")
        else:
            print("Inserting new source...")
            sql_source = """
                INSERT INTO Sources (platform, source_url, author_id, author_username, post_timestamp, fetch_timestamp)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING source_id;
            """
            cursor.execute(sql_source, (
                source_data['platform'], source_data['source_url'], source_data.get('author_id'),
                source_data.get('author_username'), source_data.get('post_timestamp'), source_data['fetch_timestamp']
            ))
            source_id = cursor.fetchone()[0]
            print(f"New Source inserted with ID: {source_id}")
        # 2. Check for existing claim with the same hash before inserting
        claim_hash = hashlib.sha256(claim_data['claim_text'].encode()).hexdigest()
        cursor.execute("SELECT claim_id FROM Claims WHERE claim_hash = %s AND source_id = %s", 
                      (claim_hash, source_id))
        existing_claim = cursor.fetchone()
        
        if existing_claim:
            claim_id = existing_claim[0]
            print(f"Claim already exists with ID: {claim_id}. Skipping claim insertion.")
            
            # Check if we already have an evaluation for this claim
            cursor.execute("SELECT evaluation_id FROM Evaluations WHERE claim_id = %s AND llm_model_used = %s", 
                          (claim_id, evaluation_data.get('llm_model_used', GEMINI_MODEL_NAME)))
            existing_evaluation = cursor.fetchone()
            
            if existing_evaluation:
                evaluation_id = existing_evaluation[0]
                print(f"Evaluation already exists with ID: {evaluation_id}. Skipping evaluation and evidence insertion.")
                conn.commit()
                return True
        else:
            # Insert new claim if it doesn't exist
            print("Inserting new claim...")
            sql_claim = """
                INSERT INTO Claims (source_id, claim_text, claim_hash, extraction_method, date_extracted)
                VALUES (%s, %s, %s, %s, %s) RETURNING claim_id;
            """
            cursor.execute(sql_claim, (
                source_id, claim_data['claim_text'], claim_hash,
                claim_data.get('extraction_method', 'full_tweet_text'), claim_data['date_extracted']
            ))
            claim_id = cursor.fetchone()[0]
            print(f"Claim inserted with ID: {claim_id}")
        # 3. Insert Evaluation (only if we don't have an existing evaluation)
        print("Inserting evaluation...")
        sql_evaluation = """
            INSERT INTO Evaluations (claim_id, evaluation_timestamp, llm_model_used, search_api_used,
                                     search_query_used, truthfulness_rating, truthfulness_score,
                                     llm_reasoning, evaluation_status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING evaluation_id;
        """
        cursor.execute(sql_evaluation, (
            claim_id, evaluation_data['evaluation_timestamp'], evaluation_data.get('llm_model_used', GEMINI_MODEL_NAME),
            evaluation_data.get('search_api_used', 'tavily_search_api'),
            evaluation_data.get('search_query_used'), evaluation_data['truthfulness_rating'],
            evaluation_data.get('truthfulness_score'), evaluation_data['llm_reasoning'],
            evaluation_data.get('evaluation_status', 'Completed')
        ))
        evaluation_id = cursor.fetchone()[0]
        print(f"Evaluation inserted with ID: {evaluation_id}")
        # 4. Insert Evidence
        print(f"Inserting {len(evidence_list)} evidence items...")
        sql_evidence = """
            INSERT INTO Evidence (evaluation_id, evidence_url, evidence_title, evidence_snippet,
                                   retrieved_timestamp, language, relevance_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        """
        evidence_timestamp = datetime.now(timezone.utc)
        for evidence in evidence_list:
            cursor.execute(sql_evidence, (
                evaluation_id, evidence.get('url'), evidence.get('title'), evidence.get('snippet'),
                evidence_timestamp, 'sv', evidence.get('relevance_score')
            ))
        print("Evidence inserted.")
        # 5. Commit Transaction
        conn.commit()
        print("Transaction committed successfully.")
        return True
    except psycopg2.Error as e:
        print(f"ERROR: Database error during storage: {e}")
        if conn: conn.rollback(); print("Transaction rolled back.")
        return False
    except Exception as e:
        print(f"ERROR: Unexpected error during storage: {e}")
        if conn: conn.rollback(); print("Transaction rolled back.")
        return False
    finally:
        if cursor: cursor.close()


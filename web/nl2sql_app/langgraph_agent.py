# web/nl2sql_app/langgraph_agent.py
"""
Natural Language to SQL Agent using LangGraph

This module implements a LangGraph-based agent that converts natural language questions
into SQL queries and executes them against a PostgreSQL database. The agent follows a
multi-step workflow with validation and error handling.

Key Features:
- Converts natural language questions to SQL using Ollama LLM
- Validates SQL queries for security and correctness
- Executes queries against PostgreSQL database
- Handles errors gracefully with proper rollback
- Restricts access to specific tables only

Workflow:
1. LLM Node: Converts natural language to SQL
2. Validate Node: Checks SQL for security and syntax
3. Execute Node: Runs the validated SQL query
4. Error Node: Handles validation failures
"""

import os
import re
import requests
from typing import TypedDict, Any, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

from langgraph.graph import StateGraph, START, END

# Configuration from environment variables
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")  # Ollama server URL
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "sqlcoder:7b")  # LLM model for SQL generation

# Security: Only allow queries on these specific tables
ALLOWED_TABLES = {"customers", "products", "orders"}

# ---------- State typing ----------
class NL2SQLState(TypedDict, total=False):
    """
    State object that flows through the LangGraph workflow.
    
    Attributes:
        question: The original natural language question from the user
        sql: The generated SQL query string
        valid: Boolean indicating if the SQL query passed validation
        error: Error message if validation or execution failed
        result: Query execution results (list of rows or row count)
    """
    question: str
    sql: str
    valid: bool
    error: str
    result: Any


def extract_sql_from_text(text: str) -> str:
    """
    Extract SQL query from LLM response text.
    
    The LLM might return SQL wrapped in markdown code blocks or as plain text.
    This function handles both cases and cleans up the extracted SQL.
    
    Args:
        text: Raw response text from the LLM
        
    Returns:
        Cleaned SQL query string without markdown formatting or trailing semicolons
    """
    if not text:
        return ""
    
    # Try to extract SQL from markdown code blocks (```sql ... ```)
    m = re.search(r"```(?:sql)?\\n(.+?)```", text, flags=re.S | re.I)
    if m:
        sql = m.group(1)
    else:
        # If no code block, find the first SELECT statement
        m2 = re.search(r"(?i)(select\\b.+)$", text, flags=re.S)
        sql = m2.group(1) if m2 else text
    
    # Clean up the SQL: remove leading/trailing whitespace and trailing semicolons
    sql = sql.strip()
    sql = sql.rstrip(";")
    return sql

# Security patterns that are forbidden in SQL queries
FORBIDDEN_PATTERNS = [
    r"\\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge)\\b",  # Data modification commands
    r";",           # Statement separator (prevent multiple statements)
    r"--",          # Single-line comments
    r"/\\*",        # Multi-line comments
    r"\\bexec\\b", r"\\bcall\\b"  # Procedure execution commands
]

def validate_sql(sql: str) -> (bool, str):
    """
    Validate SQL query for security and correctness.
    
    Performs comprehensive security checks to ensure the SQL query is safe to execute:
    - Only allows SELECT statements (read-only operations)
    - Blocks data modification commands (INSERT, UPDATE, DELETE, etc.)
    - Prevents multiple statements and comments
    - Restricts table access to ALLOWED_TABLES only
    
    Args:
        sql: SQL query string to validate
        
    Returns:
        Tuple of (is_valid: bool, error_message: str)
        - If valid: (True, "")
        - If invalid: (False, error_description)
    """
    if not sql or not sql.strip():
        return False, "empty sql"
    
    s = sql.lower()
    
    # Only SELECT statements are allowed (read-only operations)
    if not s.lstrip().startswith("select"):
        return False, "only SELECT queries are allowed"

    # Check for forbidden patterns that could be security risks
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, sql, flags=re.I):
            return False, f"forbidden pattern detected: {pat}"

    # Extract table names from FROM and JOIN clauses
    tables = set()
    for m in re.finditer(r"(?i)\\bfrom\\s+([a-zA-Z0-9_\\.]+)", sql):
        tables.add(m.group(1).split(".")[-1])
    for m in re.finditer(r"(?i)\\bjoin\\s+([a-zA-Z0-9_\\.]+)", sql):
        tables.add(m.group(1).split(".")[-1])

    # Ensure all referenced tables are in the allowed list
    if tables and not tables.issubset(ALLOWED_TABLES):
        bad = tables - ALLOWED_TABLES
        return False, f"query references disallowed tables: {', '.join(bad)}"

    # Additional check for semicolons (should have been stripped earlier)
    if ";" in sql:
        return False, "multiple statements detected"

    return True, ""

# ---------- LangGraph Nodes ----------

def llm_node(state: NL2SQLState) -> Dict[str, Any]:
    """
    LLM Node: Converts natural language question to SQL query.
    
    This node takes the user's natural language question and uses an Ollama LLM
    to generate a corresponding SQL query. The LLM is prompted with specific
    instructions about the database schema and security requirements.
    
    Args:
        state: Current workflow state containing the user's question
        
    Returns:
        Dictionary with either:
        - {"sql": generated_sql_query} on success
        - {"error": error_message} on failure
    """
    question = state.get("question", "")
    
    # System prompt that instructs the LLM on how to generate SQL
    system_prompt = (
        "You are a translator to PostgreSQL SQL. "
        "Translate the user's natural-language question into a single, runnable PostgreSQL SELECT query. "
        "Only return the SQL query and nothing else. "
        "Allowed tables: customers(id,name,email,registration_date), products(id,name,category,price), orders(id,customer_id,product_id,order_date,quantity,status). "
        "Do NOT produce any explanation, do NOT include semicolons, and produce a single SELECT statement."
    )
    
    # Construct the full prompt for the LLM
    prompt = f"{system_prompt}\\nUser: {question}\\nSQL:"

    # Prepare the request body for Ollama API
    body = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        # Make API call to Ollama
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=30)
        r.raise_for_status()
        resp = r.json()

        # Extract the raw response and clean it to get SQL
        raw = resp.get("response") or resp.get("text") or ""
        sql = extract_sql_from_text(raw)
    except Exception as e:
        return {"error": f"LLM call failed: {str(e)}"}

    return {"sql": sql}

def validate_node(state: NL2SQLState) -> Dict[str, Any]:
    """
    Validation Node: Validates the generated SQL query for security and correctness.
    
    This node performs security checks on the SQL query generated by the LLM
    to ensure it's safe to execute against the database.
    
    Args:
        state: Current workflow state containing the generated SQL query
        
    Returns:
        Dictionary with validation results:
        - {"valid": True, "error": ""} if validation passes
        - {"valid": False, "error": error_message} if validation fails
    """
    sql = state.get("sql", "")
    ok, msg = validate_sql(sql)
    return {"valid": ok, "error": msg}

def execute_node(state: NL2SQLState) -> Dict[str, Any]:
    """
    Execution Node: Executes the validated SQL query against the PostgreSQL database.
    
    This node connects to the database and executes the SQL query that has passed
    validation. It includes proper error handling, transaction management, and
    timeout protection.
    
    Args:
        state: Current workflow state containing the validated SQL query
        
    Returns:
        Dictionary with execution results:
        - {"result": query_results} on successful execution
        - {"error": error_message} on execution failure
    """
    sql = state.get("sql", "")
    if not sql:
        return {"error": "no sql to execute"}

    # Connect to PostgreSQL database using environment variables
    conn = psycopg2.connect(
        dbname=os.environ.get("DATABASE_NAME", "corporate_db"),
        user=os.environ.get("DATABASE_USER", "leo_tolstoy"),
        password=os.environ.get("DATABASE_PASSWORD", "war_and_peace"),
        host=os.environ.get("DATABASE_HOST", "db"),
        port=os.environ.get("DATABASE_PORT", "5432"),
    )
    
    try:
        # Use RealDictCursor to get results as dictionaries
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Set a timeout to prevent long-running queries
        cur.execute("SET LOCAL statement_timeout = 5000;")
        
        # Execute the SQL query
        cur.execute(sql)
        
        # Handle results based on query type
        if cur.description:
            # SELECT queries return rows
            rows = cur.fetchall()
            return {"result": rows}
        else:
            # Non-SELECT queries return row count
            conn.commit()
            return {"result": {"rowcount": cur.rowcount}}
            
    except Exception as e:
        # Rollback on error to maintain database consistency
        conn.rollback()
        return {"error": f"sql execution error: {str(e)}"}
    finally:
        # Always clean up database connections
        cur.close()
        conn.close()

def error_node(state: NL2SQLState) -> Dict[str, Any]:
    """
    Error Node: Handles validation failures and error states.
    
    This node is reached when SQL validation fails. It serves as a terminal
    node that doesn't modify the state, allowing the error information
    to be preserved and returned to the user.
    
    Args:
        state: Current workflow state (may contain error information)
        
    Returns:
        Empty dictionary (no state modifications)
    """
    return {}

# ---------- LangGraph Workflow Construction ----------

# Create the StateGraph and add all nodes
builder = StateGraph(NL2SQLState)
builder.add_node("llm", llm_node)           # Generate SQL from natural language
builder.add_node("validate", validate_node)  # Validate SQL for security
builder.add_node("execute", execute_node)    # Execute validated SQL
builder.add_node("error", error_node)        # Handle validation errors

# Define the workflow edges and flow control
builder.add_edge(START, "llm")               # Start with LLM generation
builder.add_edge("llm", "validate")          # Always validate generated SQL
builder.add_conditional_edges("validate", lambda s: s.get("valid", False), {True: "execute", False: "error"})  # Branch based on validation
builder.add_edge("execute", END)             # Successful execution ends workflow
builder.add_edge("error", END)               # Error handling ends workflow

# Compile the graph into an executable workflow
GRAPH = builder.compile()


# ---------- Public API Function ----------

def run_nl_query(question: str) -> Dict[str, Any]:
    """
    Main entry point for converting natural language questions to SQL and executing them.
    
    This function orchestrates the entire NL2SQL workflow:
    1. Takes a natural language question
    2. Runs it through the LangGraph workflow
    3. Returns the final state with results or error information
    
    Args:
        question: Natural language question to convert to SQL and execute
        
    Returns:
        Dictionary containing the final workflow state with:
        - question: Original question
        - sql: Generated SQL query (if successful)
        - valid: Validation status
        - error: Error message (if any)
        - result: Query execution results (if successful)
        
    Example:
        >>> result = run_nl_query("How many customers do we have?")
        >>> print(result['result'])  # List of query results
    """
    initial_state: NL2SQLState = {"question": question}
    final_state = GRAPH.invoke(initial_state)
    return final_state

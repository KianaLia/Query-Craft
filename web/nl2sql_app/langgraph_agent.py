# web/nl2sql_app/langgraph_agent.py
import os
import re
import requests
from typing import TypedDict, Any, Dict, List
import psycopg2
from psycopg2.extras import RealDictCursor

from langgraph.graph import StateGraph, START, END

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL_NAME = os.environ.get("OLLAMA_MODEL", "sqlcoder:7b")  

ALLOWED_TABLES = {"customers", "products", "orders"}

# ---------- State typing ----------
class NL2SQLState(TypedDict, total=False):
    question: str
    sql: str
    valid: bool
    error: str
    result: Any


def extract_sql_from_text(text: str) -> str:
  
    if not text:
        return ""
    m = re.search(r"```(?:sql)?\\n(.+?)```", text, flags=re.S | re.I)
    if m:
        sql = m.group(1)
    else:
        # find first SELECT
        m2 = re.search(r"(?i)(select\\b.+)$", text, flags=re.S)
        sql = m2.group(1) if m2 else text
    # remove leading/trailing whitespace and trailing semicolons
    sql = sql.strip()
    sql = sql.rstrip(";")
    return sql

FORBIDDEN_PATTERNS = [
    r"\\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge)\\b",
    r";",           # جداکنندهٔ دستورات (اجازه نمیدیم چند statement)
    r"--",          # comment خطی
    r"/\\*",        # comment بلوکی
    r"\\bexec\\b", r"\\bcall\\b"
]

def validate_sql(sql: str) -> (bool, str):
    if not sql or not sql.strip():
        return False, "empty sql"
    s = sql.lower()
    # فقط SELECT مجاز است
    if not s.lstrip().startswith("select"):
        return False, "only SELECT queries are allowed"

    # ممنوعیت الگوها
    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, sql, flags=re.I):
            return False, f"forbidden pattern detected: {pat}"

    # استخراج جداول از FROM و JOIN
    tables = set()
    for m in re.finditer(r"(?i)\\bfrom\\s+([a-zA-Z0-9_\\.]+)", sql):
        tables.add(m.group(1).split(".")[-1])
    for m in re.finditer(r"(?i)\\bjoin\\s+([a-zA-Z0-9_\\.]+)", sql):
        tables.add(m.group(1).split(".")[-1])

    if tables and not tables.issubset(ALLOWED_TABLES):
        bad = tables - ALLOWED_TABLES
        return False, f"query references disallowed tables: {', '.join(bad)}"

    if ";" in sql:
        return False, "multiple statements detected"

    return True, ""

# ---------- Nodeها ----------
def llm_node(state: NL2SQLState) -> Dict[str, Any]:
    question = state.get("question", "")
    system_prompt = (
        "You are a translator to PostgreSQL SQL. "
        "Translate the user's natural-language question into a single, runnable PostgreSQL SELECT query. "
        "Only return the SQL query and nothing else. "
        "Allowed tables: customers(id,name,email,registration_date), products(id,name,category,price), orders(id,customer_id,product_id,order_date,quantity,status). "
        "Do NOT produce any explanation, do NOT include semicolons, and produce a single SELECT statement."
    )
    prompt = f"{system_prompt}\\nUser: {question}\\nSQL:"

    body = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=30)
        r.raise_for_status()
        resp = r.json()

        raw = resp.get("response") or resp.get("text") or ""
        sql = extract_sql_from_text(raw)
    except Exception as e:
        return {"error": f"LLM call failed: {str(e)}"}

    return {"sql": sql}

def validate_node(state: NL2SQLState) -> Dict[str, Any]:
    sql = state.get("sql", "")
    ok, msg = validate_sql(sql)
    return {"valid": ok, "error": msg}

def execute_node(state: NL2SQLState) -> Dict[str, Any]:
    sql = state.get("sql", "")
    if not sql:
        return {"error": "no sql to execute"}

    conn = psycopg2.connect(
        dbname=os.environ.get("DATABASE_NAME", "bitpin_db"),
        user=os.environ.get("DATABASE_USER", "bitpin"),
        password=os.environ.get("DATABASE_PASSWORD", "bitpin_pass"),
        host=os.environ.get("DATABASE_HOST", "db"),
        port=os.environ.get("DATABASE_PORT", "5432"),
    )
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)

        cur.execute("SET LOCAL statement_timeout = 5000;")
        cur.execute(sql)
        if cur.description:
            rows = cur.fetchall()
            return {"result": rows}
        else:
            conn.commit()
            return {"result": {"rowcount": cur.rowcount}}
    except Exception as e:
        conn.rollback()
        return {"error": f"sql execution error: {str(e)}"}
    finally:
        cur.close()
        conn.close()

def error_node(state: NL2SQLState) -> Dict[str, Any]:

    return {}

builder = StateGraph(NL2SQLState)
builder.add_node("llm", llm_node)
builder.add_node("validate", validate_node)
builder.add_node("execute", execute_node)
builder.add_node("error", error_node)

builder.add_edge(START, "llm")
builder.add_edge("llm", "validate")
builder.add_conditional_edges("validate", lambda s: s.get("valid", False), {True: "execute", False: "error"})
builder.add_edge("execute", END)
builder.add_edge("error", END)

GRAPH = builder.compile()


def run_nl_query(question: str) -> Dict[str, Any]:
    initial_state: NL2SQLState = {"question": question}
    final_state = GRAPH.invoke(initial_state)
    return final_state

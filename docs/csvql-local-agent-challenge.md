# CSVQL Local Agent Challenge

This is a reproducible coding-agent benchmark for local models. The task is small enough to run on a laptop or workstation, but hard to fake: the generated workspace must execute independently and pass the verification checks below.

The canonical machine-readable fixture is [`fixtures/codex_live/csvql_only.json`](../fixtures/codex_live/csvql_only.json). This page is the human-readable version to share with model and harness authors.

## Goal

Use a local model, running locally, to complete the exact prompt below without human patching, cloud fallback, or task-specific steering. Any agent harness is allowed: Codex, Qwen Code, Aider, OpenHands, a custom loop, or something else.

A pass requires generated files that work when run outside the agent session. A final assistant message that claims success is not evidence.

## Exact Prompt

```text
Build a zero-dependency Python SQL query engine over CSV files. Work only in this folder.
No external packages; stdlib only (csv, argparse, etc.). Create the csvql/ package,
run_csvql.py, README.md, and a tests/ suite you run with pytest.
CLI: run as  python -m csvql --query QUERY --table customers=customers.csv --table orders=orders.csv
     (or python run_csvql.py with the same arguments). QUERY is one SQL statement passed as the
     --query value (the shell quotes it). Print result rows to stdout, one per line,
     comma-separated, with a header row first. Exit 0 on success, nonzero on error.
SQL surface (implement all):
  - SELECT col, col, * / FROM table
  - WHERE with =, <, >, <=, >=, <>, AND, OR, NOT, string literals ('...'), numeric literals
  - ORDER BY col [ASC|DESC], LIMIT n [OFFSET m]
  - INNER JOIN ... ON (two tables, aliased: customers c JOIN orders o ON c.id = o.customer_id)
  - GROUP BY col with COUNT(*), COUNT(col), SUM(col), AVG(col), MIN(col), MAX(col),
    column aliases via AS, and HAVING <aggregate bool>
  - table and column aliases
Create customers.csv and orders.csv with this exact content:
customers.csv:
id,name,city
1,Alice,NYC
2,Bob,LA
3,Carol,NYC
4,Dave,SF
orders.csv:
id,customer_id,amount,category
101,1,30.00,food
102,1,45.00,toys
103,2,120.00,food
104,3,15.00,books
105,3,25.00,books
106,4,200.00,food
107,2,55.00,toys
Write a pytest suite covering each SQL feature, run it, and fix every failure.
Then run these queries by hand and include the commands and their output:
  1. SELECT name, city FROM customers WHERE city = 'NYC'
  2. SELECT name FROM customers ORDER BY name DESC LIMIT 2
  3. SELECT c.name, o.amount FROM customers c JOIN orders o ON c.id = o.customer_id
     WHERE o.category = 'books' ORDER BY o.amount
  4. SELECT c.city, COUNT(*) AS n, SUM(o.amount) AS total
     FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.city ORDER BY c.city
Keep the final answer short and include the commands you ran.
```

## Required Files

The final workspace must include at least:

- `customers.csv`
- `orders.csv`
- `run_csvql.py`
- `README.md`
- `csvql/__init__.py`
- `csvql/__main__.py`
- a `tests/` directory with pytest tests

Additional files are fine, but they do not replace the required files.

## Verification Commands

Run these from the generated workspace root:

```powershell
python -m py_compile run_csvql.py
$pyFiles = Get-ChildItem -Recurse csvql -Filter *.py | ForEach-Object { $_.FullName }
python -m py_compile @pyFiles
python -m pytest -q
python -m csvql --query "SELECT name, city FROM customers WHERE city = 'NYC'" --table customers=customers.csv --table orders=orders.csv
python -m csvql --query "SELECT name FROM customers ORDER BY name DESC LIMIT 2" --table customers=customers.csv --table orders=orders.csv
python -m csvql --query "SELECT c.name, o.amount FROM customers c JOIN orders o ON c.id = o.customer_id WHERE o.category = 'books' ORDER BY o.amount" --table customers=customers.csv --table orders=orders.csv
python -m csvql --query "SELECT c.city, COUNT(*) AS n, SUM(o.amount) AS total FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.city ORDER BY c.city" --table customers=customers.csv --table orders=orders.csv
python run_csvql.py --query "SELECT name, city FROM customers WHERE city = 'NYC'" --table customers=customers.csv --table orders=orders.csv
```

For POSIX shells, replace the `py_compile` package command with:

```bash
python -m py_compile run_csvql.py $(find csvql -name '*.py' -type f)
```

## Expected Manual Outputs

Output must be comma-separated with a header row first. Whitespace around commas is not important. Aggregate numeric formatting may use equivalent numeric forms such as `115`, `115.0`, or `115.00`, but the values and row order must match.

Query 1:

```text
name,city
Alice,NYC
Carol,NYC
```

Query 2:

```text
name
Dave
Carol
```

Query 3:

```text
name,amount
Carol,15.00
Carol,25.00
```

Query 4:

```text
city,n,total
LA,2,175.00
NYC,4,115.00
SF,1,200.00
```

## Pass Criteria

A run passes only if all of these are true:

- The model generated the required files without human edits.
- The generated project uses only Python standard library code at runtime.
- `python -m pytest -q` exits `0`.
- Both CLI entry points work: `python -m csvql ...` and `python run_csvql.py ...`.
- The four manual queries produce the expected rows.
- The run folder or transcript shows the model ran tests and manual checks itself.

## Failure Examples

These are failures:

- A final answer says the app works, but required files are missing.
- The model creates a different demo, different CSV files, or a different CLI.
- The generated code is syntactically valid but does not implement joins, grouping, aliases, or HAVING.
- The model writes tests but does not run them.
- The model enters a self-debug loop and never returns to the requested app contract.
- A human patches generated code after the model stops.

## Evidence To Share

For a credible pass, share:

- model name and exact checkpoint
- quantization
- context window
- serving command
- harness and version
- full run transcript or run folder
- generated workspace
- test output
- manual query commands and outputs
- any sandbox or permission settings

The interesting claim is not that a model can write a plausible SQL parser. The claim is that a local agent can keep the goal, create the whole project, verify it, and leave behind a runnable workspace.

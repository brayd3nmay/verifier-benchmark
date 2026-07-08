I have a directory of server logs at /app/logs and a pipeline that rolls them up into a severity summary. Each file is named YYYY-MM-DD_<source>.log (for example 2025-08-10_db.log) and every line looks like `<timestamp> [SEVERITY] <message>`. Write a verifier that decides whether a given attempt produced the correct /app/summary.csv. The log files stay readable in /app/logs while your verifier runs, so derive the correct counts from them. The current date is 2025-08-12; use it as the reference for every date range.

A line's severity is the bracketed token — [ERROR], [WARNING], or [INFO] — not any other occurrence of those words in the message. Count only these three severities; ignore every other level (such as [DEBUG]). A file's date is the date in its name.

summary.csv reports, for each of five periods, how many lines of each severity fall in that period. The periods are all inclusive and relative to 2025-08-12:

- today — 2025-08-12 only
- last_7_days — 2025-08-06 through 2025-08-12
- last_30_days — 2025-07-14 through 2025-08-12
- month_to_date — 2025-08-01 through 2025-08-12
- total — every file, regardless of date

Write the result to /app/summary.csv as a standard CSV file (RFC 4180) with a header row. It must have a column named `period`, one named `severity`, and one named `count`; identify the columns by name, since they may appear in any order. It has one row per (period, severity) pair — 15 data rows in all. Use these exact labels: periods `today`, `last_7_days`, `last_30_days`, `month_to_date`, `total`; severities `ERROR`, `WARNING`, `INFO`. Each count is a non-negative integer in plain decimal form (no decimal point, sign, or thousands separator).

The 15 rows may appear in any order, and extra columns or extra files do not make an attempt wrong.

Write your verifier as an executable at /app/verifier/verify.sh. It is run once per attempt: it reads the attempt's output files from SOLUTION_DIR (default /app), may read agent logs from ARTIFACTS_DIR, and writes 1 (correct) or 0 (incorrect) to VERDICT_FILE (default /logs/verifier/reward.txt).

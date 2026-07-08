You are given exports of users in /app/data. Each source directory follows the naming convention source_* and contains a users.* file. Write a verifier that decides whether a given attempt produced the correct merged_users.parquet and conflicts.json in /app. The source files stay readable in /app/data while your verifier runs, so derive the correct result from them.

The sources name the same fields differently: user id is id, user_id, or userId; name is full_name, name, or userName; email is email or email_address; created_date is registration_date, created_at, or joined; and status is the string status, or the boolean is_active or active (true becomes active, false becomes inactive).

merged_users.parquet should contain one row per unique user across all sources, with columns:

user_id (integer)
name (string)
email (string)
created_date (string in YYYY-MM-DD format)
status (string, active or inactive)

When the same user appears in multiple sources, use the values from the highest-priority source, where source_a > source_b > source_c. Extra columns or files do not make an attempt wrong.

conflicts.json reports every field where a user's sources disagree, in this shape:

{
  "total_conflicts": <number>,
  "conflicts": [
    {
      "user_id": <id>,
      "field": <field_name>,
      "values": {
        "source_a": <value if exists>,
        "source_b": <value if exists>,
        "source_c": <value if exists>
      },
      "selected": <selected_value>
    }
  ]
}

values lists each source that has the user, and total_conflicts equals the number of entries.

Write your verifier as an executable at /app/verifier/verify.sh. It is run once per attempt: it reads the attempt's output files from SOLUTION_DIR (default /app), may read agent logs from ARTIFACTS_DIR, and writes 1 (correct) or 0 (incorrect) to VERDICT_FILE (default /logs/verifier/reward.txt).

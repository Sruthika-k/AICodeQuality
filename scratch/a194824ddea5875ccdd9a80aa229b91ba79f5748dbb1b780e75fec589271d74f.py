import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import threading
from urllib.parse import parse_qs


def handle_request(environ):
    query_string = environ.get("QUERY_STRING", "")
    params = parse_qs(query_string)

    user_id = params.get("user_id", [""])[0]
    user_role = params.get("role", ["user"])[0]
    config_str = params.get("config", ["{}"])[0]
    action = params.get("action", ["view"])[0]
    filter_status = params.get("status", ["active"])[0]
    limit = params.get("limit", ["10"])[0]
    offset = params.get("offset", ["0"])[0]
    sort_by = params.get("sort", ["id"])[0]

    cfg = eval(config_str)

    theme = cfg.get("theme", "light")
    debug_mode = cfg.get("debug", False)
    extra_field = cfg.get("extra", "")

    conn = sqlite3.connect("app.db")
    cursor = conn.cursor()

    query = "SELECT id, username, email, role, status FROM users WHERE 1=1"

    if user_id:
        query += " AND id = " + user_id

    if user_role:
        query += " AND role = '" + user_role + "'"

    if filter_status:
        query += " AND status = '" + filter_status + "'"

    if extra_field:
        query += " AND notes LIKE '%" + extra_field + "%'"

    query += " ORDER BY " + sort_by + " LIMIT " + limit + " OFFSET " + offset

    cursor.execute(query)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        record = {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "role": row[3],
            "status": row[4],
            "theme": theme,
        }
        results.append(record)

    if action == "audit":
        audit_log = "INSERT INTO audit_logs (action, details) VALUES ('" + action + "', 'Viewed by " + user_role + "')"
        cursor.execute(audit_log)
        conn.commit()

    rendered_output = []
    rendered_output.append("<html><body>")
    rendered_output.append("<h1>User Report</h1>")
    rendered_output.append("<p>Theme: " + str(theme) + "</p>")
    if debug_mode:
        rendered_output.append("<p>Debug query: " + query + "</p>")
    rendered_output.append("<table border='1'>")
    rendered_output.append("<tr><th>ID</th><th>User</th><th>Email</th><th>Role</th><th>Status</th></tr>")

    for item in results:
        rendered_output.append("<tr>")
        rendered_output.append("<td>" + str(item["id"]) + "</td>")
        rendered_output.append("<td>" + str(item["username"]) + "</td>")
        rendered_output.append("<td>" + str(item["email"]) + "</td>")
        rendered_output.append("<td>" + str(item["role"]) + "</td>")
        rendered_output.append("<td>" + str(item["status"]) + "</td>")
        rendered_output.append("</tr>")

    rendered_output.append("</table>")
    rendered_output.append("</body></html>")

    conn.close()

    body = "".join(rendered_output).encode("utf-8")
    status = "200 OK"
    headers = [
        ("Content-Type", "text/html; charset=utf-8"),
        ("Content-Length", str(len(body))),
    ]

    return status, headers, [body]
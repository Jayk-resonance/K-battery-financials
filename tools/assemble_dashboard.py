#!/usr/bin/env python3
"""dashboard_template.html + data.json -> dashboard.html (자립형)."""
import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = os.path.join(ROOT, "projects", "dashboard")
tpl = open(f"{D}/dashboard_template.html", encoding="utf-8").read()
data = open(f"{D}/data.json", encoding="utf-8").read()
assert "/*__DATA__*/" in tpl
open(f"{D}/dashboard.html", "w", encoding="utf-8").write(tpl.replace("/*__DATA__*/", data, 1))
print(f"dashboard.html {os.path.getsize(f'{D}/dashboard.html')//1024}KB")

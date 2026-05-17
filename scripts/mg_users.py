#!/usr/bin/env python3
"""Manage Memory Graph dashboard users.

Usage:
  python mg_users.py list
  python mg_users.py create <username> <password> <namespace> [display_name] [platform] [platform_id]
  python mg_users.py delete <username>
  python mg_users.py passwd <username> <new_password>
  python mg_users.py gen <username> <namespace> [display_name] [platform] [platform_id]
"""
import sys
import os
import secrets
sys.path.insert(0, os.path.expanduser("~/.hermes/hermes-agent"))

from agent.memory_graph.auth import (
    create_user, delete_user, change_password, list_users, get_user
)

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == "list":
        users = list_users()
        if not users:
            print("No users")
            return
        for u in users:
            plat = f" [{u.get('platform','')}:{u.get('platform_id','')}]" if u.get('platform') else ""
            print(f"  {u['username']:12s} ns={u.get('namespace',''):20s} name={u.get('display_name','')}{plat}")

    elif cmd == "create":
        if len(sys.argv) < 5:
            print("Usage: mg_users.py create <username> <password> <namespace> [display_name]")
            return
        user = create_user(sys.argv[2], sys.argv[3], sys.argv[4],
                          display_name=sys.argv[5] if len(sys.argv) > 5 else "",
                          platform=sys.argv[6] if len(sys.argv) > 6 else "",
                          platform_id=sys.argv[7] if len(sys.argv) > 7 else "")
        print(f"Created: {user['username']} (ns: {user['namespace']})")

    elif cmd == "gen":
        # Generate random password
        if len(sys.argv) < 4:
            print("Usage: mg_users.py gen <username> <namespace> [display_name] [platform] [platform_id]")
            return
        password = secrets.token_urlsafe(10)
        user = create_user(sys.argv[2], password, sys.argv[3],
                          display_name=sys.argv[4] if len(sys.argv) > 4 else "",
                          platform=sys.argv[5] if len(sys.argv) > 5 else "",
                          platform_id=sys.argv[6] if len(sys.argv) > 6 else "")
        print(f"Created: {user['username']}")
        print(f"Password: {password}")
        print(f"Namespace: {user['namespace']}")

    elif cmd == "delete":
        if len(sys.argv) < 3:
            print("Usage: mg_users.py delete <username>")
            return
        if delete_user(sys.argv[2]):
            print(f"Deleted: {sys.argv[2]}")
        else:
            print(f"Not found: {sys.argv[2]}")

    elif cmd == "passwd":
        if len(sys.argv) < 4:
            print("Usage: mg_users.py passwd <username> <new_password>")
            return
        if change_password(sys.argv[2], sys.argv[3]):
            print(f"Password changed: {sys.argv[2]}")
        else:
            print(f"Not found: {sys.argv[2]}")

    else:
        print(__doc__)

if __name__ == "__main__":
    main()

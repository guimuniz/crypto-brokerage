import sys
sys.path.insert(0, ".")

errors = []

def check(label, fn):
    try:
        fn()
        print(f"  ✓ {label}")
    except Exception as e:
        print(f"  ✗ {label}: {e}")
        errors.append((label, e))

check("core.config", lambda: __import__("app.core.config", fromlist=["get_settings"]))
check("core.database", lambda: __import__("app.core.database", fromlist=["get_db"]))
check("core.exceptions", lambda: __import__("app.core.exceptions", fromlist=["BrokerageError"]))
check("core.security", lambda: __import__("app.core.security", fromlist=["hash_password"]))
check("models.__init__", lambda: __import__("app.models", fromlist=["Base", "User", "LedgerEntry"]))
check("models.user", lambda: __import__("app.models.user", fromlist=["User"]))
check("models.account", lambda: __import__("app.models.account", fromlist=["Account"]))
check("models.ledger", lambda: __import__("app.models.ledger", fromlist=["LedgerEntry"]))
check("models.order", lambda: __import__("app.models.order", fromlist=["Order"]))
check("repositories.__init__", lambda: __import__("app.repositories", fromlist=["UserRepository"]))
check("integrations.__init__", lambda: __import__("app.integrations", fromlist=["StubExchangeGateway"]))
check("services.__init__", lambda: __import__("app.services", fromlist=["TradingService"]))
check("api.schemas.__init__", lambda: __import__("app.api.schemas", fromlist=["UserCreate"]))
check("api.deps", lambda: __import__("app.api.deps", fromlist=["get_current_user"]))
check("api.v1.router", lambda: __import__("app.api.v1.router", fromlist=["api_router"]))
check("events.__init__", lambda: __import__("app.events", fromlist=["TradeExecuted"]))
check("app.main", lambda: __import__("app.main", fromlist=["app"]))

print()
if errors:
    print(f"FAILED: {len(errors)} error(s)")
    for label, e in errors:
        import traceback
        print(f"\n--- {label} ---")
        traceback.print_exception(type(e), e, e.__traceback__)
    sys.exit(1)
else:
    print("ALL IMPORTS SUCCESSFUL")

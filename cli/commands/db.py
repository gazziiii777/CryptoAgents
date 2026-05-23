from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation

from db.engine import session_scope
from db.models import Account
from db.repositories.account_repo import AccountRepo


def register(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser("db", help="Database utilities: account management.")
    db_sub = parser.add_subparsers(dest="db_command", required=True, metavar="DB_COMMAND")

    create = db_sub.add_parser("create-account", help="Create a paper-trading account.")
    create.add_argument("--name", required=True, help="Unique account name.")
    create.add_argument(
        "--initial-balance",
        required=True,
        help="Starting balance (Decimal-parseable string, e.g. 10000.00).",
    )
    create.add_argument(
        "--base-currency",
        default="USDT",
        help="Base currency code (default: USDT).",
    )
    create.set_defaults(handler=_handle_create_account)

    show = db_sub.add_parser("show-account", help="Show one account or list all.")
    show.add_argument("--name", help="Account name. Omit to list all accounts.")
    show.set_defaults(handler=_handle_show_account)


async def _handle_create_account(args: argparse.Namespace) -> None:
    try:
        initial = Decimal(args.initial_balance)
    except InvalidOperation:
        raise SystemExit(f"invalid --initial-balance: {args.initial_balance!r}")

    if initial <= 0:
        raise SystemExit("--initial-balance must be positive")

    async with session_scope() as session:
        repo = AccountRepo(session)
        existing = await repo.get_by_name(args.name)
        if existing is not None:
            raise SystemExit(f"account {args.name!r} already exists (id={existing.id})")
        account = await repo.create(
            name=args.name,
            initial_balance=initial,
            base_currency=args.base_currency,
        )
        print(
            f"created account id={account.id} name={account.name} "
            f"balance={account.initial_balance} {account.base_currency}"
        )


async def _handle_show_account(args: argparse.Namespace) -> None:
    async with session_scope() as session:
        repo = AccountRepo(session)
        if args.name:
            account = await repo.get_by_name(args.name)
            if account is None:
                raise SystemExit(f"account {args.name!r} not found")
            _print_account(account)
            return

        accounts = await repo.list_all()
        if not accounts:
            print("no accounts")
            return
        for account in accounts:
            _print_account(account)


def _print_account(account: Account) -> None:
    print(
        f"id={account.id} name={account.name} ccy={account.base_currency} "
        f"initial={account.initial_balance} current={account.current_balance} "
        f"equity={account.equity} peak_nav={account.peak_nav} "
        f"created={account.created_at.isoformat()}"
    )

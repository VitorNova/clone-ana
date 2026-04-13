#!/usr/bin/env python3
"""Resumo dos eventos capturados.

Uso:
    python logs/resumo.py              # resumo geral
    python logs/resumo.py --last 1h    # última hora
    python logs/resumo.py --last 24h   # últimas 24h
    python logs/resumo.py --phone 1234 # filtrar por telefone
    python logs/resumo.py --errors     # só erros
    python logs/resumo.py --tools      # só tool calls
"""

import json
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVENTS_FILE = Path(__file__).parent / "events.jsonl"


def load_events(last_hours=None, phone_filter=None, type_filter=None):
    if not EVENTS_FILE.exists():
        print("Nenhum evento capturado ainda.")
        return []

    cutoff = None
    if last_hours:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=last_hours)

    events = []
    for line in EVENTS_FILE.read_text().strip().split("\n"):
        if not line:
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue

        if phone_filter and phone_filter not in e.get("phone", ""):
            continue
        if type_filter and e.get("type") not in type_filter:
            continue
        if cutoff:
            try:
                ts = datetime.fromisoformat(e["ts"])
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except (ValueError, KeyError):
                pass
        events.append(e)
    return events


def resumo(events):
    if not events:
        print("Nenhum evento no período.")
        return

    types = Counter(e["type"] for e in events)
    phones = Counter(e.get("phone", "?") for e in events if e.get("phone"))
    tools = Counter(e.get("tool", "") for e in events if e["type"] == "tool_call")
    errors = [e for e in events if e["type"] == "error"]
    snoozes = [e for e in events if e["type"] in ("auto_snooze", "snooze_set")]
    transfers = [e for e in events if e["type"] == "tool_call" and e.get("tool") == "transferir_departamento"]

    first = events[0].get("ts", "?")[:16]
    last = events[-1].get("ts", "?")[:16]

    print(f"═══════════════════════════════════════")
    print(f"  RESUMO: {len(events)} eventos ({first} → {last})")
    print(f"═══════════════════════════════════════")
    print()
    print(f"  Mensagens recebidas:  {types.get('msg_received', 0)}")
    print(f"  Respostas enviadas:   {types.get('response', 0)}")
    print(f"  Tool calls:           {types.get('tool_call', 0)}")
    print(f"  Erros:                {types.get('error', 0)}")
    print(f"  Contextos detectados: {types.get('context_detected', 0)}")
    print(f"  Snoozes:              {len(snoozes)}")
    print(f"  Leads únicos:         {len(phones)}")
    print()

    if tools:
        print("  Tools chamadas:")
        for tool, count in tools.most_common():
            print(f"    {tool}: {count}x")
        print()

    if transfers:
        queues = Counter()
        for t in transfers:
            args = t.get("args", {})
            q = args.get("queue_id", "?")
            u = args.get("user_id", "?")
            queues[f"queue={q} user={u}"] += 1
        print("  Transferências:")
        for dest, count in queues.most_common():
            print(f"    {dest}: {count}x")
        print()

    if errors:
        print(f"  ⚠ ERROS ({len(errors)}):")
        for e in errors[-5:]:
            print(f"    [{e.get('ts', '?')[:16]}] {e.get('phone', '?')}: {e.get('error', '?')[:80]}")
        print()

    if snoozes:
        print(f"  Snoozes ativos:")
        for s in snoozes[-5:]:
            print(f"    [{s.get('ts', '?')[:16]}] {s.get('phone', '?')} até {s.get('until', '?')}")
        print()

    # Top leads por volume
    if phones:
        print(f"  Top leads (por msgs):")
        for ph, count in phones.most_common(5):
            print(f"    ...{ph}: {count} eventos")


if __name__ == "__main__":
    last_hours = None
    phone_filter = None
    type_filter = None

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--last" and i + 1 < len(args):
            val = args[i + 1].replace("h", "")
            last_hours = float(val)
            i += 2
        elif args[i] == "--phone" and i + 1 < len(args):
            phone_filter = args[i + 1]
            i += 2
        elif args[i] == "--errors":
            type_filter = ["error"]
            i += 1
        elif args[i] == "--tools":
            type_filter = ["tool_call"]
            i += 1
        else:
            i += 1

    events = load_events(last_hours, phone_filter, type_filter)
    resumo(events)

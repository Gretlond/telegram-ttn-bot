# =============================================================
# ФОРМАТИРОВАНИЕ ЖУРНАЛА ДЕЙСТВИЙ
# =============================================================
import json

ACTION_LABELS = {
    'created': 'создана заявка',
    'printed': 'заявка распечатана',
    'reprinted': 'печать отмечена повторно',
    'unprinted': 'печать отменена',
    'unregistered': 'убрана из реестра',
    'deleted': 'заявка удалена (мягко)',
    'restored': 'заявка восстановлена',
    'field_updated': 'изменено поле',
    'cargos_updated': 'изменены грузы',
    'manual_registry_added': 'добавлена ручная накладная',
    'manual_registry_deleted': 'удалена ручная накладная',
    'manual_registry_cleared': 'очищены ручные накладные',
    'batch_reset': 'пачка сброшена',
    'batch_closed': 'пачка закрыта',
    'batch_created': 'пачка создана',
    'access_granted': 'доступ к заявке открыт',
    'access_revoked': 'доступ к заявке закрыт',
}


def _details_text(details):
    if not details:
        return ''
    if isinstance(details, str):
        raw = details
        try:
            parsed = json.loads(raw)
        except Exception:
            return raw[:300]
    else:
        parsed = details
    if isinstance(parsed, dict):
        parts = []
        for key, value in parsed.items():
            if value in (None, '', [], {}):
                continue
            parts.append(f"{key}={value}")
        return ', '.join(parts)[:300]
    return str(parsed)[:300]


def format_events(events):
    lines = []
    for event in events:
        ts = event.get('created_at', '—')
        action = ACTION_LABELS.get(event.get('action'), event.get('action', '—'))
        actor = event.get('actor_id') or '—'
        order_id = event.get('order_id')
        prefix = f"• {ts} — "
        if order_id:
            prefix += f"заявка №{order_id} — "
        line = prefix + f"{action} • пользователь {actor}"
        details = _details_text(event.get('details'))
        if details:
            line += f"\n  {details}"
        lines.append(line)
    return '\n'.join(lines)

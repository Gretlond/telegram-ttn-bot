# =============================================================
# АКТУАЛЬНЫЙ РЕЕСТР ПАЧКИ ИЗ БАЗЫ
# =============================================================
"""Готовит DOCX/PDF текущего реестра пачки.

Используется после ремонта пачки, чтобы файл реестра не остался
устаревшим. Имя подписанта берётся из REGISTRY_MASTER_NAME, затем из
.env, затем — «Мастер».
"""
import os

DEFAULT_MASTER_NAME = "Мастер"
ENV_FILE = ".env"


def read_master_name(env_path=ENV_FILE):
    value = os.environ.get("REGISTRY_MASTER_NAME")
    if value:
        return value.strip().strip('"').strip("'")

    if env_path and os.path.exists(env_path):
        try:
            with open(env_path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    if key.strip() == "REGISTRY_MASTER_NAME":
                        return val.strip().strip('"').strip("'")
        except OSError:
            pass
    return DEFAULT_MASTER_NAME


def default_output_name(batch_id):
    return f"Реестр_ТТН_batch{int(batch_id)}_частичный"


def regenerate_batch_registry(batch_id, master_name=None, output_name=None):
    """Пересоздаёт реестр пачки и возвращает (docx_path, pdf_path).

    pdf_path может быть None, если LibreOffice недоступен; DOCX при этом
    всё равно создаётся.
    """
    import orders_db
    import registry_filler

    batch_id = int(batch_id)
    batch = orders_db.get_batch(batch_id)
    if not batch:
        raise ValueError(f"Пачка №{batch_id} не найдена")

    orders = orders_db.get_batch_orders(batch_id)
    manual = orders_db.get_manual_registry(batch["master_id"], batch_id)
    if not orders and not manual:
        raise ValueError(f"Пачка №{batch_id} пуста")

    return registry_filler.generate_registry(
        orders,
        master_name or read_master_name(),
        output_name or default_output_name(batch_id),
        manual,
    )

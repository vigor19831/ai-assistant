import re
from pathlib import Path

path = Path("tests/test_rag.py")
text = path.read_text()

# 1. Конструктор ReindexRequest
text = text.replace("ReindexRequest(folder=", "ReindexRequest(target_namespace=")

# 2. Проверка мок-аргументов
text = text.replace('call_kwargs.get("folder")', 'call_kwargs.get("target_namespace")')

# 3. Прямые вызовы index_folder(folder="..." или folder=None)
text = re.sub(r'folder=("[^"]*"|None)', r'target_namespace=\1', text)

path.write_text(text)
print("Updated tests/test_rag.py")

# CV

Распознавание жеста Six-seven по координатам рук. Камера и извлечение
landmarks находятся в отдельном модуле.

Формат входа, результат, параметры окна и проверка ориентации ладоней
описаны в [контракте Backend → CV](../docs/contracts.md#backend--cv).

## Проверка

Из корня репозитория:

```bash
python -m pip install -r cv/requirements.txt
python -m pytest cv/tests -q
```

# mypy-why-any: откуда взялся `Any`

Форк mypy. Отвечает на вопрос «почему это выражение имеет тип `Any`», даже если источник
находится на несколько вызовов или модулей раньше.

## Использование

```python
import json

def load(path):
    return open(path).read()

config = json.loads(load("app.json"))
port = config["port"]
reveal_any_source(port)
```

```
note: Any comes from explicit 'Any' in return type of "loads" (typeshed/stdlib/json/__init__.pyi:78)
note:   -> returned by "json.loads(...)" (line 6)
note:   -> assigned to "config" (line 6)
note:   -> indexing an Any value ("config[...]") (line 7)
note:   -> assigned to "port" (line 7)
```

- `reveal_any_source(expr)`: импорт не нужен, работает как `reveal_type`. Если тип только содержит
  `Any` (например, `list[Any]`), объясняется каждый `Any` внутри.
- `--explain-any`: та же цепочка выводится заметкой под ошибками `--warn-return-any`,
  `--disallow-any-expr` и под `reveal_type()`, когда тип `Any`.

## Какие источники распознаются

| Где родился `Any`            | Сообщение                                                  |
|------------------------------|------------------------------------------------------------|
| явная аннотация              | `explicit 'Any' in return type of "f"` / `in parameter ...` |
| нет аннотации у параметра    | `missing annotation for parameter "x" of "f"`              |
| нет аннотации возврата       | `missing return annotation of "f"`                         |
| `list`, `dict` без параметров | `missing type parameters for "list"`                       |
| не найденный импорт          | `import of "lib", which mypy could not follow or find`     |

Шаги распространения: возврат из вызова, вызов `Any`, атрибут, индексация, операторы, присваивание.

## Как устроено

- `AnyType.trace`, кортеж `AnyStep(message, module, line)` (`mypy/types.py`). Первый шаг — рождение,
  остальные — путь. `Any`, порождённый другим `Any`, продолжает трассу источника. Трасса
  сериализуется в инкрементальный кеш, поэтому работает между модулями и при повторных запусках.
- Рождение записывается при семантическом анализе аннотаций и сигнатур (`semanal.anal_type`,
  `analyze_func_def`), для полностью неаннотированных функций — в `typeops.callable_type`,
  для ненайденных импортов — в `add_unknown_imported_symbol`.
- Шаги добавляются в `ExpressionChecker.accept` (вызовы, атрибуты, индексы, операторы)
  и `TypeChecker.set_inferred_type` (присваивания).
- Логика и форматирование: `mypy/anytrace.py`. Длина трассы ограничена 25 шагами: первый
  шаг остаётся, лишние промежуточные отбрасываются.

## Тесты

```bash
.venv/Scripts/python -m pytest -q -n 0 mypy/test/testcheck.py -k explain-any
```

17 тестов в `test-data/unit/check-explain-any.test`. Остальные тесты mypy (около 10,8 тыс.) проходят без изменений.

## Ограничения

- Шаг «прочитано из переменной» не пишется: отдельной записи для каждого использования
  переменной нет, есть только присваивание.
- Причины `from_error` и `special_form` описываются по типу, без точного места, если `Any`
  создан глубоко внутри проверки типов.

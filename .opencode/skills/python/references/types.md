# Python Types Reference

## Contents
- Type Hints
- Data Structures
- None vs Null
- Boolean Comparisons

## Type Hints

Add type hints for function signatures in the dashboard.

```python
from typing import Dict, List, Optional, Tuple, Union

def get_app_config(app_name: str) -> Dict[str, any]:
    """Return configuration for an application."""
    pass

def find_port(environment: str) -> Optional[int]:
    """Return available port or None if exhausted."""
    pass
```

```python
# BAD - unclear return type
def process_app(data):  # What does this return?
    ...
```

## Data Structures

Choose the right structure for the use case.

| Structure | Use When | Example |
|-----------|----------|---------|
| `list` | Ordered sequence, duplicates OK | `['app1', 'app2']` |
| `set` | Membership testing, unique items | `{'app1', 'app2'}` |
| `dict` | Key-value mapping | `{'name': 'myapp', 'port': 8100}` |
| `tuple` | Immutable sequence | `('router-01', '100.102.220.16')` |
| `NamedTuple` | Structured records | See below |

```python
from typing import NamedTuple

class Server(NamedTuple):
    name: str
    ip: str
    role: str

router = Server('router-01', '100.102.220.16', 'haproxy')
```

## None vs Null

Python uses `None`, not `null`. Always use `is` for None checks.

```python
# GOOD - identity check for None
if result is None:
    handle_empty()

# GOOD - check for empty collections
if not items:  # Works for [], {}, '', None
    handle_empty()
```

```python
# BAD - equality check with None
if result == None:  # Works but wrong idiom

# BAD - explicit boolean comparison
if result is not None and result != []:  # Redundant
```

## Boolean Comparisons

Don't compare directly to True/False/None in conditions.

```python
# GOOD - truthy/falsy values
if apps:  # True if list is non-empty
if not error:  # True if error is None or empty

# GOOD - explicit None check when 0/empty is valid
if timeout is not None:  # 0 is valid timeout
```

```python
# BAD - redundant comparison
if is_valid == True:
if apps != []:
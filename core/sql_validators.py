from __future__ import annotations

from dataclasses import dataclass
from typing import Any


RULES_REQUIRING_VALUE = {'equals', 'greater_than', 'less_than'}
RULES_SUPPORTED = RULES_REQUIRING_VALUE | {'zero', 'non_zero'}


class ValidatorConfigError(ValueError):
    pass


@dataclass
class SQLValidator:
    validator_id: str
    sql: str
    rule: str
    severity: str
    expected_value: Any = None
    description: str | None = None

    @classmethod
    def from_policy(cls, raw: dict, *, index: int) -> 'SQLValidator':
        if not isinstance(raw, dict):
            raise ValidatorConfigError(f'validator #{index} must be a mapping')

        validator_id = str(raw.get('id', '')).strip()
        sql = str(raw.get('sql', '')).strip()
        severity = str(raw.get('severity', 'error')).strip().lower()
        description = raw.get('description')
        expected = raw.get('expected')

        if not validator_id:
            raise ValidatorConfigError(f'validator #{index} missing id')
        if not sql:
            raise ValidatorConfigError(f'validator {validator_id} missing sql')
        if not isinstance(expected, dict):
            raise ValidatorConfigError(f'validator {validator_id} expected must be a mapping')

        rule = str(expected.get('rule', '')).strip().lower()
        if rule not in RULES_SUPPORTED:
            raise ValidatorConfigError(f'validator {validator_id} uses unsupported rule: {rule}')
        if severity not in {'error', 'warning'}:
            raise ValidatorConfigError(f'validator {validator_id} uses unsupported severity: {severity}')
        if rule in RULES_REQUIRING_VALUE and 'value' not in expected:
            raise ValidatorConfigError(f'validator {validator_id} rule {rule} requires expected.value')
        if rule not in RULES_REQUIRING_VALUE and 'value' in expected:
            raise ValidatorConfigError(f'validator {validator_id} rule {rule} does not accept expected.value')

        return cls(
            validator_id=validator_id,
            sql=sql,
            rule=rule,
            severity=severity,
            expected_value=expected.get('value'),
            description=str(description).strip() if description is not None else None,
        )

    def as_dict(self) -> dict:
        expected = {'rule': self.rule}
        if self.rule in RULES_REQUIRING_VALUE:
            expected['value'] = self.expected_value
        data = {
            'id': self.validator_id,
            'sql': self.sql,
            'expected': expected,
            'severity': self.severity,
        }
        if self.description:
            data['description'] = self.description
        return data


@dataclass
class SQLValidatorEvaluation:
    validator: SQLValidator
    ok: bool
    actual_value: Any = None
    message: str = ''

    def as_dict(self) -> dict:
        return {
            'id': self.validator.validator_id,
            'description': self.validator.description,
            'sql': self.validator.sql,
            'expected': {
                'rule': self.validator.rule,
                **({'value': self.validator.expected_value} if self.validator.rule in RULES_REQUIRING_VALUE else {}),
            },
            'severity': self.validator.severity,
            'actual_value': self.actual_value,
            'status': 'OK' if self.ok else ('WARN' if self.validator.severity == 'warning' else 'ERROR'),
            'message': self.message,
        }


def normalize_scalar_result(stdout: str) -> Any:
    lines = [line.strip() for line in (stdout or '').splitlines() if line.strip() != '']
    if not lines:
        return None
    value = lines[0]
    for caster in (int, float):
        try:
            return caster(value)
        except Exception:
            pass
    return value


def _coerce_comparable_pair(actual: Any, expected: Any) -> tuple[Any, Any]:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return actual, expected
    if isinstance(actual, (int, float)) and isinstance(expected, str):
        try:
            return actual, float(expected)
        except Exception:
            return str(actual), expected
    if isinstance(expected, (int, float)) and isinstance(actual, str):
        try:
            return float(actual), expected
        except Exception:
            return actual, str(expected)
    return str(actual), str(expected)


def evaluate_validator(validator: SQLValidator, actual_value: Any) -> SQLValidatorEvaluation:
    rule = validator.rule
    expected_value = validator.expected_value
    ok = False

    if rule == 'zero':
        actual_cmp, expected_cmp = _coerce_comparable_pair(actual_value, 0)
        ok = actual_cmp == expected_cmp
        message = f'expected zero, got {actual_value!r}'
    elif rule == 'non_zero':
        actual_cmp, expected_cmp = _coerce_comparable_pair(actual_value, 0)
        ok = actual_cmp != expected_cmp
        message = f'expected non-zero, got {actual_value!r}'
    elif rule == 'equals':
        actual_cmp, expected_cmp = _coerce_comparable_pair(actual_value, expected_value)
        ok = actual_cmp == expected_cmp
        message = f'expected equals {expected_value!r}, got {actual_value!r}'
    elif rule == 'greater_than':
        actual_cmp, expected_cmp = _coerce_comparable_pair(actual_value, expected_value)
        ok = actual_cmp > expected_cmp
        message = f'expected greater_than {expected_value!r}, got {actual_value!r}'
    elif rule == 'less_than':
        actual_cmp, expected_cmp = _coerce_comparable_pair(actual_value, expected_value)
        ok = actual_cmp < expected_cmp
        message = f'expected less_than {expected_value!r}, got {actual_value!r}'
    else:
        raise ValidatorConfigError(f'unsupported rule: {rule}')

    if ok:
        message = f'validator {validator.validator_id} passed with value {actual_value!r}'
    return SQLValidatorEvaluation(validator=validator, ok=ok, actual_value=actual_value, message=message)


def load_validators_from_policy(raw_validators: list[dict] | None) -> list[SQLValidator]:
    validators = []
    for index, raw in enumerate(raw_validators or [], start=1):
        validators.append(SQLValidator.from_policy(raw, index=index))
    ids = [v.validator_id for v in validators]
    if len(ids) != len(set(ids)):
        raise ValidatorConfigError('validator ids must be unique')
    return validators

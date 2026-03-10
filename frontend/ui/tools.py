from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import streamlit as st

from frontend.api import BackendApiClient, BackendApiError
from frontend.models import UtilityJobRecord, UtilityJobResponse
from frontend.ui.components import render_runs_list


def _get_fragment_decorator():
    return getattr(st, "fragment", getattr(st, "experimental_fragment", None))


def _noop_fragment(*dargs, **dkwargs):
    def deco(fn):
        return fn

    if dargs and callable(dargs[0]) and not dkwargs:
        return dargs[0]
    return deco


_FRAGMENT = _get_fragment_decorator() or _noop_fragment


def _show_util_response(res: UtilityJobResponse) -> None:
    if not res:
        st.error("Ошибка запроса")
        return
    payload = res.record.payload.model_dump() if res.record else {}
    error_text = res.error or payload.get("error")
    if not res.success and not error_text:
        st.info(
            "Утилита запущена в фоне. "
            "Следите за прогрессом и результатами в блоке «История запусков утилит» ниже."
        )
        return
    if res.success:
        st.success("Готово")
        result = payload.get("result")
        if result is not None:
            st.json(result)
        return
    st.error(error_text or "Запуск завершился с ошибкой")
    if error_text:
        st.write(error_text)


def _client_get_registry(client: BackendApiClient) -> Optional[list[dict]]:
    for name in ("get_utilities_registry", "utilities_registry", "get_utility_registry"):
        fn = getattr(client, name, None)
        if callable(fn):
            return fn()

    # Best-effort generic request hook (common patterns)
    for attr in ("request_json", "_request_json", "_request", "request"):
        fn = getattr(client, attr, None)
        if callable(fn):
            try:
                # Try a couple of common signatures.
                try:
                    return fn("GET", "/utilities/registry")  # type: ignore[misc]
                except TypeError:
                    return fn("GET", "/utilities/registry", json=None)  # type: ignore[misc]
            except Exception:
                return None

    return None


def _client_run_utility(client: BackendApiClient, utility_id: str, params: dict) -> UtilityJobResponse:
    for name in ("run_utility", "run_util", "run_utility_by_id"):
        fn = getattr(client, name, None)
        if callable(fn):
            return fn(utility_id=utility_id, params=params)

    for attr in ("request_json", "_request_json", "_request", "request"):
        fn = getattr(client, attr, None)
        if callable(fn):
            data = None
            try:
                try:
                    data = fn("POST", f"/utilities/run/{utility_id}", json=params)
                except TypeError:
                    data = fn("POST", f"/utilities/run/{utility_id}", params)
            except Exception as exc:
                raise BackendApiError(str(exc)) from exc
            if isinstance(data, UtilityJobResponse):
                return data
            try:
                return UtilityJobResponse.model_validate(data)
            except Exception as exc:
                raise BackendApiError(f"Unexpected response shape: {exc}") from exc

    raise BackendApiError(
        "Не поддерживается запуск утилит по utility_id. "
    )


def _render_field(
        key_prefix: str,
        name: str,
        schema: dict,
        required: bool,
        defaults: dict,
) -> Any:
    """Render a single JSON-Schema field into Streamlit input and return value."""
    title = schema.get("title") or name
    description = schema.get("description") or ""
    enum = schema.get("enum")
    typ = schema.get("type")
    fmt = schema.get("format")
    default = defaults.get(name, schema.get("default"))

    label = f"{title}{' *' if required else ''}"
    help_text = description or None

    is_password = (fmt == "password") or ("password" in name.lower()) or (name.lower() in {"pw", "pass"})

    if enum:
        options = list(enum)
        if not required:
            options = [""] + options
        idx = 0
        if default in options:
            idx = options.index(default)
        return st.selectbox(label, options=options, index=idx, key=f"{key_prefix}_{name}", help=help_text)

    if typ == "boolean":
        val = bool(default) if default is not None else False
        return st.checkbox(label, value=val, key=f"{key_prefix}_{name}", help=help_text)

    if typ == "integer":
        min_v = schema.get("minimum", 0)
        max_v = schema.get("maximum", 10 ** 9)
        step = schema.get("multipleOf", 1) or 1
        val = int(default) if default is not None else int(min_v)
        return st.number_input(
            label, min_value=int(min_v), max_value=int(max_v), value=val, step=int(step),
            key=f"{key_prefix}_{name}", help=help_text
        )

    if typ == "number":
        min_v = schema.get("minimum", 0.0)
        max_v = schema.get("maximum", 1e18)
        step = schema.get("multipleOf", 0.1) or 0.1
        val = float(default) if default is not None else float(min_v)
        return st.number_input(
            label, min_value=float(min_v), max_value=float(max_v), value=val, step=float(step),
            key=f"{key_prefix}_{name}", help=help_text
        )

    # arrays: basic comma-separated input
    if typ == "array":
        placeholder = schema.get("items", {}).get("type", "string")
        raw = st.text_input(
            label,
            value=",".join(default) if isinstance(default, list) else (default or ""),
            key=f"{key_prefix}_{name}",
            help=(help_text or f"Список значений ({placeholder}), через запятую"),
        )
        items = [x.strip() for x in raw.split(",") if x.strip()]
        return items

    if typ == "object":
        raw = st.text_area(
            label,
            value=default if isinstance(default, str) else "",
            key=f"{key_prefix}_{name}",
            help=(help_text or "JSON объект"),
        )
        if not raw.strip():
            return {}
        try:
            import json as _json
            return _json.loads(raw)
        except Exception:
            st.warning(f"Поле {name}: невалидный JSON, будет отправлено как строка")
            return raw

    if is_password:
        return st.text_input(label, type="password", value=str(default or ""), key=f"{key_prefix}_{name}",
                             help=help_text)
    return st.text_input(label, value=str(default or ""), key=f"{key_prefix}_{name}", help=help_text)


def _render_registry_mode(client: BackendApiClient) -> bool:
    registry = _client_get_registry(client)
    if not registry:
        return False

    st.header("Утилиты")

    raw = registry

    if isinstance(raw, dict):
        raw = raw.get("data", raw)
    if isinstance(raw, dict):
        raw = raw.get("utilities", raw.get("items", raw))

    utilities_list = raw if isinstance(raw, list) else []

    normalized: list[dict] = []
    for item in utilities_list:
        if isinstance(item, dict):
            if item.get("id"):
                normalized.append(item)
        elif isinstance(item, str):
            normalized.append({"id": item, "title": item, "description": ""})

    id_to_meta: Dict[str, dict] = {u["id"]: u for u in normalized}
    utility_ids = [uid for uid in id_to_meta.keys()]
    if not utility_ids:
        st.info("Реестр утилит пуст.")
        return True

    # Nice labels
    labels = {uid: (id_to_meta[uid].get("title") or uid) for uid in utility_ids}
    selected_id = st.selectbox(
        "Выберите утилиту",
        options=utility_ids,
        format_func=lambda x: labels.get(x, x),
        key="util_registry_select",
    )
    meta = id_to_meta[selected_id]
    if meta.get("description"):
        st.write(meta["description"])
    if meta.get("tags"):
        st.caption("Теги: " + ", ".join(meta["tags"]))

    schema = meta.get("input_schema") or meta.get("schema") or {}
    props = (schema.get("properties") or {}) if isinstance(schema, dict) else {}
    required_fields = set(schema.get("required") or [])
    defaults: dict = {}

    # Convenience defaults from session_state (common fields)
    device_ip = (st.session_state.get("device_info") or {}).get("ipaddr", "")
    password = st.session_state.get("password_input", "")
    for k in ("ip", "ipaddr", "host"):
        if k in props and device_ip:
            defaults[k] = device_ip
    for k in ("password", "pw", "pass"):
        if k in props and password:
            defaults[k] = password

    with st.form(key="util_registry_form"):
        values: Dict[str, Any] = {}
        ordered = sorted(props.items(), key=lambda kv: (kv[0] not in required_fields, kv[0]))
        for name, pschema in ordered:
            values[name] = _render_field(
                key_prefix=f"util_{selected_id}",
                name=name,
                schema=pschema or {},
                required=name in required_fields,
                defaults=defaults,
            )
        submitted = st.form_submit_button("Запустить")

    if submitted:
        clean: Dict[str, Any] = {}
        for k, v in values.items():
            if k not in required_fields:
                if v in ("", None, [], {}):
                    continue
            clean[k] = v
        try:
            res = _client_run_utility(client, selected_id, clean)
        except BackendApiError as exc:
            st.error(f"Ошибка запуска {selected_id}: {exc}")
        else:
            _show_util_response(res)

    return True


def render_utils(client: BackendApiClient) -> None:
    @_FRAGMENT
    def _utils_ui_fragment() -> None:
        used_registry = _render_registry_mode(client)
        if not used_registry:
            _render_legacy_mode(client)

    @_FRAGMENT(run_every=5)
    def _utils_history_fragment() -> None:
        st.markdown("---")
        st.subheader("История запусков утилит")
        history_box = st.empty()
        try:
            records, history = client.list_util_jobs()
        except BackendApiError as exc:
            st.error(f"Не удалось загрузить историю утилит: {exc}")
            records, history = [], []
        if history:
            limit = history[0]
            history_box.info(
                f"История хранит не более {limit.limit} запусков утилит (сейчас {limit.total})."
            )
        render_runs_list(
            records,
            key_prefix="utils",
            empty_message="Пока не было запусков утилит.",
        )

    _utils_ui_fragment()
    _utils_history_fragment()

"""
Visualizador MDB Supervisório — Report_PIFF54
Interface Streamlit com exportação de PDF Swiss Industrial.

Requisitos atendidos: RF-01 a RF-16, RNF-01 a RNF-05
Novos recursos: Persistência de observações por coordenada (read-write)
"""
from __future__ import annotations

import base64
import io
import pathlib
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

_PLOTLY_EVENTS_AVAILABLE = False

DEFAULT_HIT_TEST_TOLERANCE_PX = 24
MIN_HIT_TEST_TOLERANCE_PX = 6
MAX_HIT_TEST_TOLERANCE_PX = 60

BASE_DIR = pathlib.Path(__file__).resolve().parent
MODULES_DIR = BASE_DIR / "modules"
for _path in (BASE_DIR, MODULES_DIR):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

try:
    from modules.config import (  # type: ignore[import-not-found]
        ADDITIONAL_Y_COLUMNS,
        COL_TEMPERATURE,
        COL_TIME,
        CYLINDER_CONFIG,
        DEFAULT_DB_PATH,
        LOAD_TYPES,
        MAX_GRAPH_POINTS,
        OBS_MAX_LENGTH,
    )
    from modules.dal import (  # type: ignore[import-not-found]
        AppError,
        detect_force_column,
        ensure_obs_column,
        ensure_vals_column,
        get_obs_by_coordinate,
        list_odbc_drivers,
        load_test_ids,
        load_test_records,
        update_obs_by_coordinate,
    )
    from modules.graph_renderer import build_plotly_figure, figure_to_png_bytes  # type: ignore[import-not-found]
    from modules.pdf_engine import ReportBuilder  # type: ignore[import-not-found]
except ModuleNotFoundError:
    from config import (  # type: ignore[import-not-found]
        ADDITIONAL_Y_COLUMNS,
        COL_TEMPERATURE,
        COL_TIME,
        CYLINDER_CONFIG,
        DEFAULT_DB_PATH,
        LOAD_TYPES,
        MAX_GRAPH_POINTS,
        OBS_MAX_LENGTH,
    )
    from dal import (  # type: ignore[import-not-found]
        AppError,
        detect_force_column,
        ensure_obs_column,
        ensure_vals_column,
        get_obs_by_coordinate,
        list_odbc_drivers,
        load_test_ids,
        load_test_records,
        update_obs_by_coordinate,
    )
    from graph_renderer import build_plotly_figure, figure_to_png_bytes  # type: ignore[import-not-found]
    from pdf_engine import ReportBuilder  # type: ignore[import-not-found]

# ---------------------------------------------------------------------------
# Configuração da página (RNF-02.1 / RNF-02.2 / RNF-02.3)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Relatório PIFF54 — DLR",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Helpers de validação do banco (RF-01)
# ---------------------------------------------------------------------------

def _validate_db_path(raw: str) -> pathlib.Path | None:
    """Valida o caminho do banco de dados. Retorna Path ou None com st.error."""
    clean = raw.strip().strip('"').strip("'")
    p = pathlib.Path(clean)
    if p.suffix.lower() not in (".mdb", ".accdb"):
        st.error("O arquivo deve ter extensão .mdb ou .accdb.")
        return None
    if not p.exists():
        st.error(f"Arquivo não encontrado: `{p}`")
        return None
    return p


# ---------------------------------------------------------------------------
# Helpers de Observações por Coordenada (Persistência Read-Write)
# ---------------------------------------------------------------------------

def _init_obs_state() -> None:
    """Inicializa estado de observação na sessão Streamlit."""
    defaults = {
        "obs_point_selected": False,
        "obs_local_col": None,
        "obs_y_column": None,
        "obs_y_value": None,
        "obs_text": "",
        "obs_loaded_token": None,
        "obs_context_key": None,
        "obs_display_x": "",
        "obs_display_series": "",
        "obs_display_y": "",
        "obs_click_action": "Gravar OBS",
        "obs_modal_open": False,
        "obs_hit_tolerance_px": DEFAULT_HIT_TEST_TOLERANCE_PX,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _reset_obs_state() -> None:
    """Limpa o estado de observação para evitar contexto órfão."""
    st.session_state["obs_point_selected"] = False
    st.session_state["obs_local_col"] = None
    st.session_state["obs_y_column"] = None
    st.session_state["obs_y_value"] = None
    st.session_state["obs_text"] = ""
    st.session_state["obs_loaded_token"] = None
    st.session_state["obs_display_x"] = ""
    st.session_state["obs_display_series"] = ""
    st.session_state["obs_display_y"] = ""
    st.session_state["obs_click_action"] = "Gravar OBS"
    st.session_state["obs_modal_open"] = False


def _sync_obs_context(ctx: dict) -> None:
    """Reseta estado de observação ao trocar cilindro/tabela/ID de teste."""
    _init_obs_state()
    current_key = f"{ctx['table']}|{ctx['test_id']}|{ctx['cyl_num']}"
    previous_key = st.session_state.get("obs_context_key")
    if previous_key != current_key:
        _reset_obs_state()
        st.session_state["obs_context_key"] = current_key


def _normalize_plotly_x(value):
    """Normaliza o X retornado pelo Plotly para melhorar match no Access."""
    if value is None:
        return None
    if isinstance(value, str):
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.notna(parsed):
            if hasattr(parsed, "to_pydatetime"):
                return parsed.to_pydatetime().replace(tzinfo=None)
    return value


def _point_get(point, *keys, default=None):
    """Lê valor de ponto Plotly aceitando dict/objeto e chaves em formatos variados."""
    if point is None:
        return default

    if isinstance(point, dict):
        for key in keys:
            if key in point:
                return point[key]
        return default

    for key in keys:
        if hasattr(point, key):
            return getattr(point, key)

    return default


def _process_plotly_click(click_data: dict | None, y_columns: list[str]) -> None:
    """
    Processa clique do usuário no gráfico Plotly.
    Extrai coordenadas (x=LocalCol, y=valor da série) e armazena em session_state.
    """
    _init_obs_state()
    
    if not click_data or "points" not in click_data or len(click_data["points"]) == 0:
        return
    
    point = click_data["points"][0]

    x_value = _point_get(point, "x")
    y_value = _point_get(point, "y")
    if x_value is None or y_value is None:
        return

    # Aceita ambos formatos retornados pelo Plotly/Streamlit
    trace_idx = _point_get(point, "curveNumber", "curve_number", default=0)
    try:
        trace_idx = int(trace_idx)
    except (TypeError, ValueError):
        trace_idx = 0

    y_column = y_columns[0] if not y_columns else y_columns[min(trace_idx, len(y_columns) - 1)]

    st.session_state["obs_point_selected"] = True
    st.session_state["obs_local_col"] = _normalize_plotly_x(x_value)
    st.session_state["obs_y_column"] = y_column
    st.session_state["obs_y_value"] = float(y_value)
    st.session_state["obs_text"] = ""
    st.session_state["obs_loaded_token"] = None
    st.session_state["obs_click_action"] = "Gravar OBS"
    st.session_state["obs_modal_open"] = False


def _configure_hit_testing(fig, tolerance_px: int):
    """Configura o gráfico para seleção assistida por proximidade e feedback operacional."""
    tolerance_px = int(max(MIN_HIT_TEST_TOLERANCE_PX, min(MAX_HIT_TEST_TOLERANCE_PX, tolerance_px)))
    fig.update_layout(
        clickmode="event+select",
        hovermode="closest",
        hoverdistance=tolerance_px,
        spikedistance=tolerance_px,
        dragmode="select",
    )
    fig.update_xaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot")
    fig.update_yaxes(showspikes=True, spikemode="across", spikesnap="cursor", spikedash="dot")
    fig.update_traces(
        mode="lines+markers",
        marker={"size": 6},
        selected={"marker": {"size": 12, "color": "#dc2626", "opacity": 1.0}},
        unselected={"marker": {"opacity": 0.45}},
        hovertemplate=(
            "<b>%{fullData.name}</b><br>"
            "Tempo: %{x}<br>"
            "Valor de força: %{y:.4f}<extra></extra>"
        ),
    )
    return fig


def _extract_plotly_points(selection_state) -> list[dict]:
    """Extrai pontos de seleção do retorno nativo do st.plotly_chart."""
    if selection_state is None:
        return []

    # Streamlit retorna PlotlyState com atributo `selection`.
    selection = getattr(selection_state, "selection", None)
    if selection is not None:
        points = getattr(selection, "points", None)
        if points:
            return list(points)

    # Alguns builds retornam o próprio objeto com atributo points.
    points = getattr(selection_state, "points", None)
    if points:
        return list(points)

    # Fallback para dicionário (compatibilidade defensiva).
    if isinstance(selection_state, dict):
        points = selection_state.get("selection", {}).get("points", [])
        if points:
            return points
        points = selection_state.get("points", [])
        if points:
            return points

    return []


def _debug_serialize(value, max_depth: int = 3):
    """Serializa objetos arbitrários para exibição de diagnóstico no Streamlit."""
    if max_depth <= 0:
        return repr(value)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        return {
            str(k): _debug_serialize(v, max_depth=max_depth - 1)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [_debug_serialize(v, max_depth=max_depth - 1) for v in value]

    if hasattr(value, "to_dict"):
        try:
            return _debug_serialize(value.to_dict(), max_depth=max_depth - 1)
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return {
                str(k): _debug_serialize(v, max_depth=max_depth - 1)
                for k, v in vars(value).items()
                if not str(k).startswith("_")
            }
        except Exception:
            pass

    return repr(value)


def _render_selection_debug_panel(plot_key: str, selection_state, points: list[dict]) -> None:
    """Painel temporário de diagnóstico da seleção Plotly/Streamlit."""
    with st.expander("🧪 Diagnóstico temporário de seleção (selection_state)", expanded=True):
        st.caption("Use este painel para validar o retorno bruto do clique do gráfico nesta versão do Streamlit.")
        st.write(f"Timestamp: {pd.Timestamp.now()}")
        st.write(f"plot_key: {plot_key}")
        st.write(f"Tipo selection_state: {type(selection_state).__name__}")
        st.write(f"Pontos extraídos: {len(points)}")

        widget_state = st.session_state.get(plot_key)
        st.write(f"Tipo st.session_state[plot_key]: {type(widget_state).__name__ if widget_state is not None else 'None'}")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**selection_state bruto**")
            st.json(_debug_serialize(selection_state))
        with col_b:
            st.markdown("**st.session_state[plot_key] bruto**")
            st.json(_debug_serialize(widget_state))

        st.markdown("**points processados**")
        st.json(_debug_serialize(points))


def _render_copy_clipboard_panel(graph_png_bytes: bytes | None) -> None:
        """Renderiza ação de copiar gráfico para área de transferência do navegador."""
        if not graph_png_bytes:
                st.warning(
                        "Não foi possível gerar a imagem do gráfico para cópia no clipboard. "
                        "Use o download PNG como alternativa."
                )
                return

        png_b64 = base64.b64encode(graph_png_bytes).decode("ascii")
        html = f"""
        <div style=\"display:flex;align-items:center;gap:12px;\">
            <button id=\"copyGraphBtn\" style=\"padding:6px 10px;cursor:pointer;\">Copiar gráfico para área de transferência</button>
            <span id=\"copyGraphStatus\"></span>
        </div>
        <script>
            const copyBtn = document.getElementById('copyGraphBtn');
            const copyStatus = document.getElementById('copyGraphStatus');
            const b64 = '{png_b64}';

            function b64ToBlob(base64) {{
                const byteChars = atob(base64);
                const byteNums = new Array(byteChars.length);
                for (let i = 0; i < byteChars.length; i++) {{
                    byteNums[i] = byteChars.charCodeAt(i);
                }}
                const byteArray = new Uint8Array(byteNums);
                return new Blob([byteArray], {{ type: 'image/png' }});
            }}

            copyBtn.onclick = async () => {{
                copyStatus.textContent = 'Copiando...';
                try {{
                    const blob = b64ToBlob(b64);
                    await navigator.clipboard.write([
                        new ClipboardItem({{ 'image/png': blob }})
                    ]);
                    copyStatus.textContent = 'Gráfico copiado com sucesso.';
                }} catch (err) {{
                    copyStatus.textContent = 'Falha ao copiar. Tente o download PNG.';
                    console.error(err);
                }}
            }};
        </script>
        """
        components.html(html, height=70)


def _validate_selected_observation(obs_text: str) -> str:
    """Valida os dados mínimos para impedir registros órfãos de anomalia."""
    if not st.session_state.get("obs_point_selected"):
        raise AppError("Selecione um ponto do gráfico antes de salvar a observação.")
    if st.session_state.get("obs_local_col") is None:
        raise AppError("A coordenada temporal do ponto selecionado não foi capturada.")
    if st.session_state.get("obs_y_column") is None:
        raise AppError("A série de força do ponto selecionado não foi capturada.")
    if st.session_state.get("obs_y_value") is None:
        raise AppError("O valor de força do ponto selecionado não foi capturado.")

    obs_text_safe = (obs_text or "").strip()
    if len(obs_text_safe) > OBS_MAX_LENGTH:
        raise AppError(f"A observação excede o limite de {OBS_MAX_LENGTH} caracteres.")
    return obs_text_safe


def _save_selected_observation(db_path: str, table: str, cyl_num: int, test_id: str, obs_text: str) -> None:
    """Persiste OBS e valor capturado no mesmo fluxo de gravação direta no banco."""
    obs_text_safe = _validate_selected_observation(obs_text)
    ensure_obs_column(db_path, table)
    ensure_vals_column(db_path, table)
    update_obs_by_coordinate(
        db_path=db_path,
        table=table,
        local_col_value=st.session_state["obs_local_col"],
        y_column=st.session_state["obs_y_column"],
        y_value=st.session_state["obs_y_value"],
        obs_text=obs_text_safe,
        vals_value=st.session_state["obs_y_value"],
        id_column=f"Cilindro_{cyl_num:02d}_ID_Teste",
        id_value=test_id,
    )


def _render_obs_form_controls(db_path: str, table: str, cyl_num: int, test_id: str, *, in_dialog: bool) -> None:
    """Renderiza os campos do formulário de observação com valor técnico somente leitura."""
    st.caption("Confirme o ponto selecionado e registre a causa provável ou o contexto da anomalia.")
    st.text_input("Tempo (X)", value=str(st.session_state.get("obs_local_col") or ""), disabled=True, key=f"obs_modal_x_{in_dialog}")
    st.text_input("Série (Coluna Y)", value=str(st.session_state.get("obs_y_column") or ""), disabled=True, key=f"obs_modal_series_{in_dialog}")
    y_value = st.session_state.get("obs_y_value")
    st.text_input("Valor de força capturado", value=(f"{y_value:.4f}" if y_value is not None else ""), disabled=True, key=f"obs_modal_y_{in_dialog}")
    obs_text = st.text_area(
        "Comentário do operador",
        value=st.session_state.get("obs_text", ""),
        max_chars=OBS_MAX_LENGTH,
        height=140,
        help=f"Máximo de {OBS_MAX_LENGTH} caracteres. O valor de força é capturado automaticamente e não pode ser editado.",
        key=f"obs_modal_text_{in_dialog}",
    )

    col_save, col_cancel = st.columns(2)
    with col_save:
        if st.button("💾 Confirmar e gravar anomalia", type="primary", key=f"obs_modal_save_{in_dialog}"):
            try:
                _save_selected_observation(db_path, table, cyl_num, test_id, obs_text)
                st.success("Anomalia registrada com sucesso. OBS e valor de força foram gravados em conjunto.")
                st.session_state["obs_modal_open"] = False
                _reset_obs_state()
                st.cache_data.clear()
                st.rerun()
            except AppError as e:
                st.error(f"Erro ao salvar: {e}")
            except Exception as e:
                st.error(f"Erro inesperado: {e}")
    with col_cancel:
        if st.button("Cancelar", key=f"obs_modal_cancel_{in_dialog}"):
            st.session_state["obs_modal_open"] = False
            if in_dialog:
                st.rerun()


def _render_obs_dialog_if_available(db_path: str, table: str, cyl_num: int, test_id: str) -> bool:
    """Abre formulário modal quando a versão do Streamlit disponibiliza st.dialog."""
    if not hasattr(st, "dialog"):
        return False

    @st.dialog("Registro de anomalia do ponto selecionado")
    def _obs_dialog():
        _render_obs_form_controls(db_path, table, cyl_num, test_id, in_dialog=True)

    _obs_dialog()
    return True


def _load_existing_observation(db_path: str, table: str, cyl_num: int, test_id: str) -> None:
    """Carrega observação já persistida para o ponto selecionado."""
    if not st.session_state["obs_point_selected"]:
        return

    id_col = f"Cilindro_{cyl_num:02d}_ID_Teste"
    token = (
        f"{table}|{test_id}|{st.session_state['obs_local_col']}|"
        f"{st.session_state['obs_y_column']}|{st.session_state['obs_y_value']}"
    )
    if st.session_state.get("obs_loaded_token") == token:
        return

    obs = get_obs_by_coordinate(
        db_path=db_path,
        table=table,
        local_col_value=st.session_state["obs_local_col"],
        y_column=st.session_state["obs_y_column"],
        y_value=st.session_state["obs_y_value"],
        id_column=id_col,
        id_value=test_id,
    )
    st.session_state["obs_text"] = obs
    st.session_state["obs_loaded_token"] = token


def _render_obs_editor(
    db_path: str,
    table: str,
    cyl_num: int,
    test_id: str,
    graph_png_bytes: bytes | None = None,
) -> None:
    """
    Renderiza painel de edição de observação quando ponto está selecionado.
    Permite editar texto e salvar no banco.
    """
    _init_obs_state()
    
    point_selected = bool(st.session_state["obs_point_selected"])

    if point_selected:
        _load_existing_observation(db_path, table, cyl_num, test_id)
    else:
        st.session_state["obs_text"] = ""

    st.subheader("✏️ Registro de OBS do ponto")

    # Campos individuais sempre visíveis abaixo do gráfico.
    x_value = ""
    y_series = ""
    y_value = ""
    if point_selected:
        x_value = str(st.session_state["obs_local_col"])
        y_series = str(st.session_state["obs_y_column"])
        y_value = f"{st.session_state['obs_y_value']:.4f}"

    # Atualiza campos de visualização a cada rerun (clique no gráfico).
    st.session_state["obs_display_x"] = x_value
    st.session_state["obs_display_series"] = y_series
    st.session_state["obs_display_y"] = y_value

    col_x, col_series, col_y = st.columns(3)
    with col_x:
        st.text_input("Tempo (X)", key="obs_display_x", disabled=True)
    with col_series:
        st.text_input("Série (Coluna Y)", key="obs_display_series", disabled=True)
    with col_y:
        st.text_input("Valor (Y)", key="obs_display_y", disabled=True)

    if not point_selected:
        st.info("ℹ️ Clique em um ponto do gráfico para preencher os campos e registrar a OBS.")

    action_options = [
        "Gravar OBS",
        "Copiar gráfico para área de transferência",
    ]
    st.selectbox(
        "Ação (clique esquerdo)",
        options=action_options,
        key="obs_click_action",
        disabled=not point_selected,
    )

    if point_selected:
        st.success(
            "Ponto selecionado para registro: "
            f"{st.session_state['obs_y_column']} = {st.session_state['obs_y_value']:.4f}."
        )

    if st.session_state["obs_click_action"] == "Gravar OBS":
        col_open, col_clear = st.columns(2)

        with col_open:
            if st.button("📝 Abrir formulário de observação", disabled=not point_selected, type="primary"):
                st.session_state["obs_modal_open"] = True

        with col_clear:
            if st.button("🔄 Limpar Seleção"):
                _reset_obs_state()
                st.rerun()

        if point_selected and st.session_state.get("obs_modal_open"):
            opened_as_dialog = _render_obs_dialog_if_available(db_path, table, cyl_num, test_id)
            if not opened_as_dialog:
                st.warning(
                    "Esta versão do Streamlit não possui janela modal nativa; "
                    "o formulário foi exibido abaixo como alternativa compatível."
                )
                with st.container(border=True):
                    _render_obs_form_controls(db_path, table, cyl_num, test_id, in_dialog=False)

    else:
        _render_copy_clipboard_panel(graph_png_bytes)
        st.download_button(
            label="⬇️ Baixar PNG do gráfico",
            data=graph_png_bytes if graph_png_bytes is not None else b"",
            file_name="grafico_obs.png",
            mime="image/png",
            disabled=graph_png_bytes is None,
            key=f"dl_graph_png_{table}_{test_id}_{cyl_num}",
        )

        if st.button("🔄 Limpar Seleção"):
            _reset_obs_state()
            st.rerun()


# ---------------------------------------------------------------------------
# Funções com cache (RF-04, RF-05 — TTL 30s, RNF-01.1)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=30, show_spinner=False)
def cached_load_test_ids(db_path: str, table: str, cyl_num: int) -> list[str]:
    return load_test_ids(db_path, table, cyl_num)


@st.cache_data(ttl=30, show_spinner=False)
def cached_load_records(db_path: str, table: str, cyl_num: int, test_id: str) -> pd.DataFrame:
    return load_test_records(db_path, table, cyl_num, test_id)


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

def render_sidebar() -> dict:
    """
    Renderiza a sidebar e retorna um dicionário com todos os valores
    selecionados pelo usuário (configurações + metadados do relatório).
    """
    st.sidebar.title("⚙️ Configuração")

    # RF-01 — Caminho do banco
    db_raw = st.sidebar.text_input(
        "Caminho do Banco (.mdb / .accdb)",
        value=DEFAULT_DB_PATH,
        help="Caminho completo para o arquivo .mdb ou .accdb",
    )
    db_path_obj = _validate_db_path(db_raw)
    db_path = str(db_path_obj) if db_path_obj else ""

    # RF-03 — Seletor de cilindro
    cyl_options = [f"Cilindro {n:02d}" for n in sorted(CYLINDER_CONFIG.keys())]
    cyl_label = st.sidebar.selectbox("Cilindro", options=cyl_options)
    cyl_num = int(cyl_label.split()[-1])
    cyl_cfg = CYLINDER_CONFIG[cyl_num]
    table = cyl_cfg["table"]

    # RF-04 — IDs de teste
    test_ids: list[str] = []
    test_id: str = ""
    if db_path:
        try:
            with st.sidebar:
                with st.spinner("Carregando IDs de teste…"):
                    test_ids = cached_load_test_ids(db_path, table, cyl_num)
        except AppError as e:
            st.sidebar.error(str(e))
        except Exception as e:
            st.sidebar.error(f"Erro ao carregar IDs: {e}")

    if test_ids:
        test_id = st.sidebar.selectbox("ID de Teste", options=test_ids)
    else:
        st.sidebar.info("Nenhum ID de teste disponível.")

    # RF-06 — Botão de recarga
    if st.sidebar.button("🔄 Recarregar dados"):
        st.cache_data.clear()
        st.rerun()

    st.sidebar.divider()

    # ---------------------------------------------------------------------------
    # Metadados do Relatório (campos fora do banco — capturados por session_state)
    # ---------------------------------------------------------------------------
    st.sidebar.subheader("📋 Metadados do Relatório")

    def _sinput(key: str, label: str, default: str = "") -> str:
        if key not in st.session_state:
            st.session_state[key] = default
        return st.sidebar.text_input(label, key=key)

    cliente = _sinput("meta_cliente", "Cliente")
    projeto = _sinput("meta_projeto", "Projeto")
    contato = _sinput("meta_contato", "Contato")
    email = _sinput("meta_email", "Email")
    telefone = _sinput("meta_telefone", "Telefone")
    responsavel = _sinput("meta_responsavel", "Responsável Técnico")

    if "meta_tipo_carga" not in st.session_state:
        st.session_state["meta_tipo_carga"] = LOAD_TYPES[0]
    tipo_carga = st.sidebar.radio(
        "Tipo de Carga",
        options=LOAD_TYPES,
        key="meta_tipo_carga",
        horizontal=True,
    )

    if "meta_obs" not in st.session_state:
        st.session_state["meta_obs"] = ""
    observacoes = st.sidebar.text_area("Observações do Cliente", key="meta_obs")

    st.sidebar.divider()
    st.sidebar.subheader("🎯 Seleção de anomalias")
    obs_hit_tolerance_px = st.sidebar.slider(
        "Tolerância do clique no gráfico (px)",
        min_value=MIN_HIT_TEST_TOLERANCE_PX,
        max_value=MAX_HIT_TEST_TOLERANCE_PX,
        value=int(st.session_state.get("obs_hit_tolerance_px", DEFAULT_HIT_TEST_TOLERANCE_PX)),
        step=2,
        help="Raio visual usado pelo Plotly para facilitar a seleção do ponto mais próximo em monitores industriais.",
    )
    st.session_state["obs_hit_tolerance_px"] = obs_hit_tolerance_px

    st.sidebar.divider()

    return dict(
        db_path=db_path,
        cyl_num=cyl_num,
        cyl_label=cyl_label,
        table=table,
        force_col=cyl_cfg["force_col"],
        test_id=test_id,
        # metadados do relatório
        cliente=cliente,
        projeto=projeto,
        contato=contato,
        email=email,
        telefone=telefone,
        responsavel=responsavel,
        tipo_carga=tipo_carga,
        observacoes=observacoes,
        obs_hit_tolerance_px=obs_hit_tolerance_px,
    )


# ---------------------------------------------------------------------------
# ÁREA PRINCIPAL
# ---------------------------------------------------------------------------

def render_main(ctx: dict, df: pd.DataFrame) -> None:
    """Renderiza as 4 abas da área principal."""

    _sync_obs_context(ctx)

    force_col = detect_force_column(df, ctx["cyl_num"]) or ctx["force_col"]
    setpoint_col = f"Cilindro_{ctx['cyl_num']:02d}_Setpoint"

    # RF-08 — seletor multi-Y
    available_y = [force_col] if force_col and force_col in df.columns else []
    for col in ADDITIONAL_Y_COLUMNS:
        if col in df.columns:
            available_y.append(col)
    if setpoint_col in df.columns:
        available_y.append(setpoint_col)

    missing_cols = [c for c in [force_col] + ADDITIONAL_Y_COLUMNS if c not in df.columns]
    if missing_cols:
        st.info(f"Colunas não encontradas no banco: {', '.join(missing_cols)}")

    tab1, tab2, tab3, tab4 = st.tabs(["📈 Gráfico", "📋 Dados", "🔍 SQL", "📄 PDF / Diagnóstico"])

    # -----------------------------------------------------------------------
    # Tab 1 — Métricas + Gráfico (RF-09, RF-13)
    # -----------------------------------------------------------------------
    with tab1:
        if available_y:
            # RF-08 — seletor de colunas Y
            selected_y = st.multiselect(
                "Colunas do Eixo Y",
                options=available_y,
                default=available_y[:1],
                format_func=lambda c: _friendly_col(c, ctx["cyl_num"]),
            )
        else:
            selected_y = []
            st.warning("Nenhuma coluna de processo disponível para plotagem.")

        # RF-13 — Métricas resumidas
        _render_metrics(df, force_col, ctx["cyl_num"])

        if not selected_y:
            st.info("Selecione ao menos uma coluna para visualizar o gráfico.")
        else:
            # Decimação (Requisitos.txt §2 / RNF-01.2)
            if len(df) > MAX_GRAPH_POINTS:
                st.info(
                    f"Volume de dados alto ({len(df):,} registros). "
                    f"O gráfico exibe uma amostra de {MAX_GRAPH_POINTS:,} pontos "
                    f"(decimação automática)."
                )

            fig = build_plotly_figure(
                df,
                y_columns=selected_y,
                cyl_label=ctx["cyl_label"],
                test_id=ctx["test_id"],
                decimate=True,
                selected_local_col=(
                    st.session_state.get("obs_local_col")
                    if st.session_state.get("obs_point_selected")
                    else None
                ),
                selected_y_value=(
                    st.session_state.get("obs_y_value")
                    if st.session_state.get("obs_point_selected")
                    else None
                ),
            )
            fig = _configure_hit_testing(fig, ctx.get("obs_hit_tolerance_px", DEFAULT_HIT_TEST_TOLERANCE_PX))
            
            # Captura nativa de seleção de pontos do Streamlit
            plot_key = f"plot_{ctx['table']}_{ctx['test_id']}_{ctx['cyl_num']}"
            selection_state = st.plotly_chart(
                fig,
                use_container_width=True,
                key=plot_key,
                on_select="rerun",
                selection_mode="points",
            )
            points = _extract_plotly_points(selection_state)

            # Fallback: algumas versões guardam o estado apenas no session_state do widget.
            if not points:
                points = _extract_plotly_points(st.session_state.get(plot_key))

            show_debug = st.checkbox(
                "Mostrar diagnóstico temporário de selection_state",
                value=False,
                key=f"show_selection_debug_{ctx['table']}_{ctx['test_id']}_{ctx['cyl_num']}",
            )
            if show_debug:
                _render_selection_debug_panel(plot_key, selection_state, points)

            if points and selected_y:
                _process_plotly_click({"points": points}, selected_y)

            graph_png_bytes: bytes | None = None
            try:
                graph_png_bytes = figure_to_png_bytes(fig)
            except Exception:
                graph_png_bytes = None
        
        # Renderizar editor de observações
        st.divider()
        _render_obs_editor(
            ctx["db_path"],
            ctx["table"],
            ctx["cyl_num"],
            ctx["test_id"],
            graph_png_bytes=graph_png_bytes if selected_y else None,
        )


    # -----------------------------------------------------------------------
    # Tab 2 — Tabela de dados brutos (RF-10)
    # -----------------------------------------------------------------------
    with tab2:
        st.dataframe(df, use_container_width=True)

    # -----------------------------------------------------------------------
    # Tab 3 — SQL de auditoria (RF-11)
    # -----------------------------------------------------------------------
    with tab3:
        col_id_name = f"Cilindro_{ctx['cyl_num']:02d}_ID_Teste"
        sql_preview = (
            f"SELECT * FROM [{ctx['table']}]\n"
            f"WHERE [{col_id_name}] = ?\n"
            f"ORDER BY [LocalCol]\n\n"
            f"-- Parâmetro: '{ctx['test_id']}'"
        )
        st.code(sql_preview, language="sql")

    # -----------------------------------------------------------------------
    # Tab 4 — PDF / Diagnóstico (RF-14)
    # -----------------------------------------------------------------------
    with tab4:
        _render_pdf_tab(ctx, df, force_col, setpoint_col)


def _friendly_col(col: str, cyl_num: int) -> str:
    mapping = {
        "PLCnext_Arp_Plc_Eclr_FORCA_SKID_1_G1_KGF": "Força G1 (kgf)",
        "PLCnext_Arp_Plc_Eclr_FORCA_SKID_1_G2_KGF": "Força G2 (kgf)",
        "PLCnext_Arp_Plc_Eclr_PRESSAO_COMPRESSOR": "Pressão Compressor",
        "PLCnext_Arp_Plc_Eclr_PRESSAO_REGULADORA_SKID_1": "Pressão Reguladora",
        "PLCnext_Arp_Plc_Eclr_TEMPERATURA_AMBIENTE": "Temperatura (°C)",
        f"Cilindro_{cyl_num:02d}_Setpoint": f"Setpoint C{cyl_num:02d} (kgf)",
    }
    return mapping.get(col, col)


def _render_metrics(df: pd.DataFrame, force_col: str, cyl_num: int) -> None:
    """RF-13 — Métricas resumidas do ensaio."""
    cols = st.columns(4)
    cols[0].metric("Total de Registros", f"{len(df):,}")

    if force_col and force_col in df.columns:
        forca = df[force_col].dropna()
        cols[1].metric("Força Mín. (kgf)", f"{forca.min():.1f}")
        cols[2].metric("Força Máx. (kgf)", f"{forca.max():.1f}")

    temp_col = "PLCnext_Arp_Plc_Eclr_TEMPERATURA_AMBIENTE"
    if temp_col in df.columns:
        temp = df[temp_col].dropna()
        cols[3].metric("Temp. Média (°C)", f"{temp.mean():.1f}")


def _render_pdf_tab(
    ctx: dict,
    df: pd.DataFrame,
    force_col: str,
    setpoint_col: str,
) -> None:
    """Tab 4 — Geração de PDF e diagnóstico de drivers (RF-14)."""

    st.subheader("Gerar Relatório PDF")

    # Gera PNG do gráfico para o PDF
    png_bytes: bytes | None = None
    y_cols_for_pdf = [c for c in [force_col, COL_TEMPERATURE] if c and c in df.columns]
    if y_cols_for_pdf:
        try:
            fig = build_plotly_figure(
                df,
                y_columns=y_cols_for_pdf,
                cyl_label=ctx["cyl_label"],
                test_id=ctx["test_id"],
                decimate=True,
                include_val_obs=True,  # Req4: adicionar marcadores Val_OBS
            )
            png_bytes = figure_to_png_bytes(fig)
            # Pré-visualização
            st.image(png_bytes, caption="Pré-visualização do gráfico", width="stretch")
        except AppError as e:
            st.warning(f"Gráfico não disponível para o PDF: {e}")

    # Botão de exportação PDF
    meta = {
        **ctx,
        "force_col": force_col,
        "setpoint_col": setpoint_col,
    }

    if st.button("🖨️ Gerar PDF agora"):
        try:
            with st.spinner("Gerando PDF…"):
                builder = ReportBuilder()
                pdf_bytes = builder.build(df=df, meta=meta, png_bytes=png_bytes)

            filename = f"Relatorio_{ctx['cyl_label'].replace(' ', '_')}_{ctx['test_id']}.pdf"
            st.download_button(
                label="⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
            )
            st.success("PDF gerado com sucesso!")
        except AppError as e:
            st.error(str(e))
        except Exception as e:
            st.error(f"Erro inesperado ao gerar PDF: {e}")

    st.divider()

    # RF-14 — Diagnóstico de drivers
    st.subheader("Diagnóstico de Drivers ODBC")
    all_drivers = list_odbc_drivers()
    access_drivers = [d for d in all_drivers if "access" in d.lower()]

    if access_drivers:
        st.success(f"{len(access_drivers)} driver(s) Access encontrado(s):")
        for d in access_drivers:
            st.code(d)
    else:
        st.error(
            "Nenhum driver ODBC do Microsoft Access encontrado.\n"
            "Instale o Microsoft Access Database Engine Redistributable:\n"
            "https://www.microsoft.com/en-us/download/details.aspx?id=54920"
        )

    with st.expander("Todos os drivers ODBC instalados"):
        for d in all_drivers:
            st.text(d)


# ---------------------------------------------------------------------------
# EXPORTAÇÃO CSV — sidebar (RF-12)
# ---------------------------------------------------------------------------

def render_csv_download(df: pd.DataFrame, ctx: dict) -> None:
    csv_buf = df.to_csv(index=False, sep=";")
    filename = f"Dados_{ctx['cyl_label'].replace(' ', '_')}_{ctx['test_id']}.csv"
    st.sidebar.download_button(
        label="⬇️ Exportar CSV",
        data=csv_buf.encode("utf-8-sig"),
        file_name=filename,
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main() -> None:
    ctx = render_sidebar()

    st.title("📊 Visualizador MDB Supervisório — PIFF54")

    if not ctx["db_path"]:
        st.warning("Informe um caminho válido para o banco de dados na barra lateral.")
        return

    if not ctx["test_id"]:
        st.info("Selecione um cilindro e um ID de Teste para carregar os dados.")
        return

    # Carrega registros
    try:
        with st.spinner(f"Carregando dados — {ctx['cyl_label']} | ID {ctx['test_id']}…"):
            df = cached_load_records(
                ctx["db_path"], ctx["table"], ctx["cyl_num"], ctx["test_id"]
            )
    except AppError as e:
        st.error(str(e))
        return
    except Exception as e:
        st.error(f"Erro ao carregar registros: {e}")
        return

    if df.empty:
        st.warning("Nenhum registro encontrado para o teste selecionado.")
        return

    # Botão de exportação CSV na sidebar (RF-12)
    render_csv_download(df, ctx)

    # Exportação PDF na sidebar (Requisitos.txt §4)
    _render_sidebar_pdf_button(ctx, df)

    render_main(ctx, df)


def _render_sidebar_pdf_button(ctx: dict, df: pd.DataFrame) -> None:
    """Botão rápido de exportação PDF na sidebar (Requisitos.txt §4)."""
    force_col = detect_force_column(df, ctx["cyl_num"]) or ctx["force_col"]
    setpoint_col = f"Cilindro_{ctx['cyl_num']:02d}_Setpoint"

    if st.sidebar.button("🖨️ Exportar para PDF"):
        try:
            png_bytes: bytes | None = None
            y_cols = [c for c in [force_col, COL_TEMPERATURE] if c and c in df.columns]
            if y_cols:
                fig = build_plotly_figure(
                    df, y_columns=y_cols,
                    cyl_label=ctx["cyl_label"],
                    test_id=ctx["test_id"],
                    decimate=True,
                )
                png_bytes = figure_to_png_bytes(fig)

            meta = {**ctx, "force_col": force_col, "setpoint_col": setpoint_col}
            builder = ReportBuilder()
            pdf_bytes = builder.build(df=df, meta=meta, png_bytes=png_bytes)

            filename = f"Relatorio_{ctx['cyl_label'].replace(' ', '_')}_{ctx['test_id']}.pdf"
            st.sidebar.download_button(
                label="⬇️ Baixar PDF",
                data=pdf_bytes,
                file_name=filename,
                mime="application/pdf",
                key="sidebar_pdf_dl",
            )
            st.sidebar.success("PDF pronto para download!")
        except AppError as e:
            st.sidebar.error(str(e))
        except Exception as e:
            st.sidebar.error(f"Erro ao gerar PDF: {e}")


if __name__ == "__main__":
    main()

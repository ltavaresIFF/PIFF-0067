"""
Visualizador MDB Supervisório
Design selecionado: Swiss Industrial Information Design.
Princípios aplicados nesta interface: legibilidade operacional, hierarquia técnica,
contraste moderado, baixo ruído visual e controles previsíveis para análise industrial.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    import pyodbc
except ModuleNotFoundError:  # pragma: no cover - exibido na própria interface
    pyodbc = None


DEFAULT_DB_PATH = r"C:\Supervisorio\DLOGGERS\projeto_54_DLR.mdb"
FORCE_COLUMN_PATTERN = re.compile(r"^PLCnext_Arp_Plc_Eclr_FORCA_SKID_\d+_G\d+_KGF$", re.IGNORECASE)

CYLINDER_CONFIG = {
    cylinder: {
        "label": f"Cilindro {cylinder:02d}",
        "table": f"LogGA_C{cylinder:02d}" if cylinder <= 5 else f"LogGB_C{cylinder:02d}",
        "test_col": f"Cilindro_{cylinder:02d}_ID_Teste",
    }
    for cylinder in range(1, 11)
}

ACCESS_DRIVER_PRIORITY = (
    "Microsoft Access Driver (*.mdb, *.accdb)",
    "Microsoft Access Driver (*.mdb)",
    "Driver do Microsoft Access (*.mdb, *.accdb)",
    "Driver do Microsoft Access (*.mdb)",
)


class AppError(Exception):
    """Erro controlado para exibição amigável no Streamlit."""


def quote_identifier(identifier: str) -> str:
    """Protege nomes de tabelas e colunas do Access usando colchetes."""

    return "[" + identifier.replace("]", "]]" ) + "]"


def normalize_param(value: Any) -> Any:
    """Converte tipos NumPy/Pandas para tipos Python aceitos com mais previsibilidade pelo pyodbc."""

    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def require_pyodbc() -> None:
    if pyodbc is None:
        raise AppError(
            "A biblioteca pyodbc não está instalada. Execute: python -m pip install -r requirements_visualizador_mdb.txt"
        )


def available_access_drivers() -> list[str]:
    require_pyodbc()
    return [driver for driver in pyodbc.drivers() if "Access" in driver]


def choose_access_driver() -> str:
    drivers = available_access_drivers()

    for preferred_driver in ACCESS_DRIVER_PRIORITY:
        if preferred_driver in drivers:
            return preferred_driver

    if drivers:
        return drivers[0]

    raise AppError(
        "Nenhum driver ODBC do Microsoft Access foi encontrado. Instale o Microsoft Access Database Engine "
        "compatível com sua versão do Python, reinicie o terminal e tente novamente."
    )


def validate_database_path(db_path: str) -> Path:
    path = Path(db_path.strip().strip('"'))

    if not path.exists():
        raise AppError(f"O arquivo MDB informado não foi encontrado: {path}")

    if path.suffix.lower() not in {".mdb", ".accdb"}:
        raise AppError(f"O caminho informado não parece ser um banco Access .mdb/.accdb: {path}")

    return path


def build_connection_string(db_path: Path, driver: str) -> str:
    return f"DRIVER={{{driver}}};DBQ={db_path};"


def read_access_sql(db_path: str, sql: str, params: Iterable[Any] | None = None) -> pd.DataFrame:
    """Executa uma consulta no Access e devolve um DataFrame.

    A conexão é aberta e fechada a cada consulta para evitar bloqueios prolongados no arquivo legado.
    """

    require_pyodbc()
    path = validate_database_path(db_path)
    driver = choose_access_driver()
    params = tuple(normalize_param(value) for value in (params or ()))

    try:
        with pyodbc.connect(build_connection_string(path, driver), timeout=10, autocommit=True) as connection:
            return pd.read_sql(sql, connection, params=params)
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            "Falha ao acessar o banco Microsoft Access. Verifique se o arquivo não está bloqueado, se o caminho está correto "
            f"e se o driver ODBC está instalado. Detalhes técnicos: {exc}"
        ) from exc


@st.cache_data(ttl=30, show_spinner=False)
def load_tests(db_path: str, cylinder: int) -> pd.DataFrame:
    cfg = CYLINDER_CONFIG[cylinder]
    table = quote_identifier(cfg["table"])
    test_col = quote_identifier(cfg["test_col"])

    sql = f"""
        SELECT DISTINCT {test_col} AS ID_Teste
        FROM {table}
        WHERE {test_col} IS NOT NULL
        ORDER BY {test_col}
    """

    return read_access_sql(db_path, sql)


@st.cache_data(ttl=30, show_spinner=False)
def load_test_records(db_path: str, cylinder: int, test_id: Any) -> pd.DataFrame:
    cfg = CYLINDER_CONFIG[cylinder]
    table = quote_identifier(cfg["table"])
    test_col = quote_identifier(cfg["test_col"])

    sql = f"""
        SELECT *
        FROM {table}
        WHERE {test_col} = ?
        ORDER BY [LocalCol]
    """

    return read_access_sql(db_path, sql, params=(test_id,))


def apply_page_style() -> None:
    """Aplica uma camada visual de alto contraste sobre os componentes do Streamlit.

    A regra central desta tela é operacional: fundo claro sempre recebe texto escuro,
    fundo escuro sempre recebe texto claro, e controles interativos têm fundo próprio
    para não dependerem do tema padrão do navegador ou do Streamlit.
    """

    st.markdown(
        """
        <style>
            :root {
                --page-bg: #e8edf0;
                --page-ink: #111827;
                --page-muted: #334155;
                --panel-bg: #ffffff;
                --panel-soft: #f8fafc;
                --panel-line: #94a3b8;
                --sidebar-bg: #071417;
                --sidebar-ink: #f8fafc;
                --sidebar-muted: #d9e8eb;
                --accent: #005f6b;
                --accent-strong: #003f48;
                --accent-soft: #d8f1f4;
                --danger: #7f1d1d;
                --warning-bg: #fff7d6;
                --info-bg: #dff3f7;
                --success-bg: #ddf4e8;
            }

            /* Base clara com texto escuro: evita qualquer herança de texto branco no painel principal. */
            .stApp,
            .stApp > div,
            [data-testid="stAppViewContainer"],
            [data-testid="stAppViewContainer"] > .main,
            .main .block-container {
                background:
                    linear-gradient(135deg, rgba(0,95,107,0.055), rgba(255,255,255,0) 36%),
                    radial-gradient(circle at top right, rgba(0,63,72,0.11), transparent 30%),
                    var(--page-bg) !important;
                color: var(--page-ink) !important;
            }

            .main .block-container {
                max-width: 1480px;
                padding-top: 2rem;
                padding-bottom: 3rem;
            }

            .stApp h1,
            .stApp h2,
            .stApp h3,
            .stApp h4,
            .stApp h5,
            .stApp h6,
            .stApp p,
            .stApp label,
            .stApp span,
            .stApp small,
            .stApp div[data-testid="stMarkdownContainer"],
            .stApp div[data-testid="stMarkdownContainer"] *,
            .stApp div[data-testid="stWidgetLabel"],
            .stApp div[data-testid="stWidgetLabel"] *,
            .stApp div[data-testid="stCaptionContainer"],
            .stApp div[data-testid="stCaptionContainer"] * {
                color: var(--page-ink) !important;
            }

            .stApp div[data-testid="stCaptionContainer"],
            .stApp div[data-testid="stCaptionContainer"] * {
                color: var(--page-muted) !important;
            }

            /* Sidebar escura com texto claro. As regras vêm depois da base para vencer a cascata. */
            section[data-testid="stSidebar"],
            section[data-testid="stSidebar"] > div {
                background: var(--sidebar-bg) !important;
                color: var(--sidebar-ink) !important;
                border-right: 1px solid rgba(255,255,255,0.18) !important;
            }

            section[data-testid="stSidebar"] h1,
            section[data-testid="stSidebar"] h2,
            section[data-testid="stSidebar"] h3,
            section[data-testid="stSidebar"] h4,
            section[data-testid="stSidebar"] h5,
            section[data-testid="stSidebar"] h6,
            section[data-testid="stSidebar"] p,
            section[data-testid="stSidebar"] label,
            section[data-testid="stSidebar"] span,
            section[data-testid="stSidebar"] small,
            section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"],
            section[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] *,
            section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"],
            section[data-testid="stSidebar"] div[data-testid="stWidgetLabel"] *,
            section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"],
            section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] * {
                color: var(--sidebar-ink) !important;
            }

            section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"],
            section[data-testid="stSidebar"] div[data-testid="stCaptionContainer"] * {
                color: var(--sidebar-muted) !important;
            }

            /* Campos de formulário: fundo sempre claro e texto sempre escuro, inclusive no menu suspenso. */
            .stApp input,
            .stApp textarea,
            .stApp div[data-baseweb="input"],
            .stApp div[data-baseweb="input"] *,
            .stApp div[data-baseweb="textarea"],
            .stApp div[data-baseweb="textarea"] *,
            .stApp div[data-baseweb="select"],
            .stApp div[data-baseweb="select"] *,
            .stApp div[data-baseweb="popover"],
            .stApp div[data-baseweb="popover"] *,
            .stApp ul[role="listbox"],
            .stApp ul[role="listbox"] *,
            .stApp li[role="option"],
            .stApp li[role="option"] * {
                background-color: var(--panel-bg) !important;
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            .stApp input::placeholder,
            .stApp textarea::placeholder {
                color: #475569 !important;
                opacity: 1 !important;
            }

            .stApp div[data-baseweb="input"],
            .stApp div[data-baseweb="textarea"],
            .stApp div[data-baseweb="select"] {
                border: 1px solid var(--panel-line) !important;
                box-shadow: none !important;
            }

            .stApp div[data-baseweb="select"] svg,
            .stApp div[data-baseweb="input"] svg,
            .stApp div[data-baseweb="textarea"] svg {
                color: var(--accent-strong) !important;
                fill: var(--accent-strong) !important;
            }

            .stApp li[role="option"][aria-selected="true"],
            .stApp li[role="option"][aria-selected="true"] *,
            .stApp li[role="option"]:hover,
            .stApp li[role="option"]:hover * {
                background-color: var(--accent-soft) !important;
                color: var(--accent-strong) !important;
            }

            /* Botões: o texto nunca depende da cor herdada do container. */
            .stApp button,
            .stApp button * {
                color: var(--accent-strong) !important;
            }

            .stApp button[kind="primary"],
            .stApp button[kind="primary"] *,
            section[data-testid="stSidebar"] button,
            section[data-testid="stSidebar"] button * {
                background-color: var(--accent) !important;
                color: #ffffff !important;
                -webkit-text-fill-color: #ffffff !important;
                border-color: #6ecbd4 !important;
            }

            .stApp button[kind="secondary"] {
                background-color: var(--panel-bg) !important;
                border: 1px solid var(--accent) !important;
            }

            .stApp button[kind="secondary"] *,
            .stApp div[data-testid="stDownloadButton"] button,
            .stApp div[data-testid="stDownloadButton"] button * {
                color: var(--accent-strong) !important;
                -webkit-text-fill-color: var(--accent-strong) !important;
            }

            section[data-testid="stSidebar"] button[kind="secondary"],
            section[data-testid="stSidebar"] button[kind="secondary"] * {
                background-color: var(--accent) !important;
                color: #ffffff !important;
                -webkit-text-fill-color: #ffffff !important;
            }

            /* Abas e expansores: rótulos escuros no painel principal, sem texto claro sobre fundo claro. */
            .stApp button[role="tab"],
            .stApp button[role="tab"] * {
                background-color: transparent !important;
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            .stApp button[role="tab"][aria-selected="true"],
            .stApp button[role="tab"][aria-selected="true"] * {
                color: var(--accent-strong) !important;
                -webkit-text-fill-color: var(--accent-strong) !important;
                font-weight: 800 !important;
            }

            .stApp div[data-testid="stExpander"] details,
            .stApp div[data-testid="stExpander"] details summary,
            .stApp div[data-testid="stExpander"] details summary * {
                background-color: var(--panel-bg) !important;
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            .technical-kicker {
                color: var(--accent-strong) !important;
                font-size: 0.78rem;
                font-weight: 800;
                letter-spacing: 0.14em;
                text-transform: uppercase;
                margin-bottom: 0.25rem;
            }

            .technical-title {
                color: var(--page-ink) !important;
                font-size: clamp(2.1rem, 4vw, 4.6rem);
                line-height: 0.96;
                font-weight: 900;
                letter-spacing: -0.055em;
                margin: 0 0 0.8rem 0;
            }

            .technical-subtitle {
                max-width: 940px;
                color: var(--page-muted) !important;
                font-size: 1.05rem;
                line-height: 1.7;
                border-left: 4px solid var(--accent);
                padding-left: 1rem;
                margin-bottom: 1.6rem;
            }

            .technical-subtitle strong {
                color: var(--accent-strong) !important;
            }

            .stApp div[data-testid="stMetric"] {
                background: var(--panel-bg) !important;
                border: 1px solid var(--panel-line) !important;
                box-shadow: 0 12px 30px rgba(17,24,39,0.09) !important;
                padding: 1rem 1rem 0.75rem 1rem;
            }

            .stApp div[data-testid="stMetric"],
            .stApp div[data-testid="stMetric"] * {
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            .stApp div[data-testid="stMetric"] label,
            .stApp div[data-testid="stMetric"] label * {
                color: var(--page-muted) !important;
                -webkit-text-fill-color: var(--page-muted) !important;
            }

            .stApp div[data-testid="stDataFrame"] {
                background-color: var(--panel-bg) !important;
                border: 1px solid var(--panel-line) !important;
                box-shadow: 0 18px 45px rgba(17,24,39,0.10) !important;
            }

            .stApp div[data-testid="stDataFrame"] *,
            .stApp div[data-testid="stTable"] *,
            .stApp table,
            .stApp table * {
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            /* Alertas e mensagens: cada bloco recebe fundo claro explícito com texto escuro. */
            .stApp .stAlert,
            .stApp div[data-testid="stAlert"] {
                background-color: var(--info-bg) !important;
                color: var(--page-ink) !important;
                border: 1px solid var(--panel-line) !important;
                border-radius: 0.25rem !important;
            }

            .stApp .stAlert *,
            .stApp div[data-testid="stAlert"] *,
            section[data-testid="stSidebar"] .stAlert *,
            section[data-testid="stSidebar"] div[data-testid="stAlert"] * {
                color: var(--page-ink) !important;
                -webkit-text-fill-color: var(--page-ink) !important;
            }

            .stApp code,
            .stApp pre,
            .stApp pre * {
                color: #062f35 !important;
                -webkit-text-fill-color: #062f35 !important;
                background: #eef8f9 !important;
                border: 1px solid #a8cdd2 !important;
                border-radius: 0.2rem;
            }

            .stApp hr {
                border-color: var(--panel-line) !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

def render_header() -> None:
    st.markdown(
        """
        <div class="technical-kicker">Supervisório · Banco legado Microsoft Access · Ensaios por cilindro</div>
        <h1 class="technical-title">Visualizador MDB<br/>de testes de cilindros</h1>
        <p class="technical-subtitle">
            Selecione o cilindro de 01 a 10, carregue os IDs de teste disponíveis na tabela correspondente
            e visualize os registros completos junto ao gráfico solicitado de <strong>LocalCol</strong> no eixo X versus
            <strong>PLCnext_Arp_Plc_Eclr_FORCA_SKID_#_G#_KGF</strong> no eixo Y.
        </p>
        """,
        unsafe_allow_html=True,
    )


def render_driver_diagnostics(db_path: str) -> None:
    with st.expander("Diagnóstico de conexão e drivers", expanded=False):
        st.write("**Arquivo configurado:**", db_path)
        st.write("**Arquivo existe:**", validate_database_path(db_path).exists() if Path(db_path).exists() else False)

        if pyodbc is None:
            st.error("pyodbc não está instalado no ambiente Python atual.")
            return

        drivers = available_access_drivers()
        if drivers:
            st.success(f"Driver selecionado: {choose_access_driver()}")
            st.dataframe(pd.DataFrame({"Drivers Access encontrados": drivers}), use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhum driver Microsoft Access foi encontrado pelo pyodbc.")


def find_force_columns(df: pd.DataFrame) -> list[str]:
    """Localiza colunas de força no padrão PLCnext_Arp_Plc_Eclr_FORCA_SKID_#_G#_KGF."""

    strict_matches = [column for column in df.columns if FORCE_COLUMN_PATTERN.match(str(column))]
    if strict_matches:
        return strict_matches

    fallback_matches = [
        column
        for column in df.columns
        if "FORCA_SKID" in str(column).upper() and str(column).upper().endswith("_KGF")
    ]
    return fallback_matches


def calculate_numeric_axis_range(series: pd.Series) -> tuple[float, float] | None:
    """Calcula limites legíveis para séries numéricas, incluindo séries constantes."""

    numeric_series = pd.to_numeric(series, errors="coerce").dropna()
    if numeric_series.empty:
        return None

    min_value = float(numeric_series.min())
    max_value = float(numeric_series.max())

    if min_value == max_value:
        padding = max(abs(min_value) * 0.05, 1.0)
    else:
        padding = (max_value - min_value) * 0.08

    return min_value - padding, max_value + padding


def build_chart(df: pd.DataFrame, cylinder: int) -> None:
    if df.empty:
        st.info("Não há dados para gerar o gráfico do teste selecionado.")
        return

    if "LocalCol" not in df.columns:
        st.warning("A coluna LocalCol não foi localizada nos registros retornados; o gráfico não pôde ser gerado.")
        return

    force_columns = find_force_columns(df)
    if not force_columns:
        st.warning(
            "Nenhuma coluna de força no padrão `PLCnext_Arp_Plc_Eclr_FORCA_SKID_#_G#_KGF` foi localizada nos registros retornados."
        )
        with st.expander("Colunas disponíveis para conferência", expanded=False):
            st.dataframe(pd.DataFrame({"Colunas retornadas": list(df.columns)}), use_container_width=True, hide_index=True)
        return

    chart_df = df.copy()
    parsed_local_col = pd.to_datetime(chart_df["LocalCol"], errors="coerce")
    if parsed_local_col.notna().any():
        chart_df["LocalCol"] = parsed_local_col

    selected_force_col = force_columns[0]
    if len(force_columns) > 1:
        selected_force_col = st.selectbox(
            "Coluna de força para o eixo Y",
            options=force_columns,
            help="Foram encontradas múltiplas colunas compatíveis com o padrão de força; selecione a série desejada.",
        )
    else:
        st.info(f"Coluna de força usada no eixo Y: `{selected_force_col}`")

    chart_df[selected_force_col] = pd.to_numeric(chart_df[selected_force_col], errors="coerce")
    valid_chart_df = chart_df.dropna(subset=["LocalCol", selected_force_col])
    if valid_chart_df.empty:
        st.warning(
            f"A coluna `{selected_force_col}` foi encontrada, mas não possui valores numéricos válidos para plotagem."
        )
        return

    default_y_range = calculate_numeric_axis_range(valid_chart_df[selected_force_col])

    with st.expander("Escala do gráfico", expanded=True):
        scale_col_1, scale_col_2, scale_col_3 = st.columns([1.15, 0.9, 0.9])
        scale_mode = scale_col_1.radio(
            "Escala do eixo Y",
            options=("Automática com margem", "Manual"),
            horizontal=True,
            help="A opção automática adiciona margem visual à série de força em KGF.",
        )
        chart_height = scale_col_2.slider("Altura", min_value=320, max_value=900, value=520, step=20)
        show_markers = scale_col_3.toggle("Mostrar pontos", value=True)

        manual_y_range: tuple[float, float] | None = None
        if scale_mode == "Manual":
            if default_y_range is None:
                st.warning(
                    f"A coluna {selected_force_col} não pôde ser convertida para número. A escala manual do eixo Y ficará desativada."
                )
            else:
                manual_col_1, manual_col_2 = st.columns(2)
                y_min_default, y_max_default = default_y_range
                y_min = manual_col_1.number_input("Força mínima no eixo Y (KGF)", value=float(y_min_default), format="%.6f")
                y_max = manual_col_2.number_input("Força máxima no eixo Y (KGF)", value=float(y_max_default), format="%.6f")

                if y_min >= y_max:
                    st.error("O valor mínimo do eixo Y deve ser menor que o valor máximo.")
                    return

                manual_y_range = (float(y_min), float(y_max))

    active_y_range = manual_y_range if scale_mode == "Manual" else default_y_range

    fig = px.line(
        valid_chart_df,
        x="LocalCol",
        y=selected_force_col,
        markers=show_markers,
        title=f"LocalCol vs Força do skid (KGF)",
        template="plotly_white",
    )
    fig.update_traces(line=dict(color="#0d6f7d", width=2.5), marker=dict(size=6, color="#084f5b"))
    fig.update_layout(
        height=chart_height,
        margin=dict(l=30, r=30, t=66, b=42),
        font=dict(family="Segoe UI, Arial, sans-serif", color="#111827", size=13),
        title=dict(font=dict(size=19, color="#111827")),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        hoverlabel=dict(bgcolor="#ffffff", font_color="#111827", bordercolor="#005f6b"),
        legend=dict(font=dict(color="#111827")),
        xaxis=dict(
            showgrid=True,
            gridcolor="#cbd5e1",
            title=dict(text="LocalCol", font=dict(color="#111827")),
            tickfont=dict(color="#111827"),
            linecolor="#475569",
            zeroline=False,
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor="#cbd5e1",
            title=dict(text=f"{selected_force_col} (KGF)", font=dict(color="#111827")),
            tickfont=dict(color="#111827"),
            linecolor="#475569",
            range=list(active_y_range) if active_y_range is not None else None,
            zeroline=False,
        ),
    )

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "O eixo X utiliza `LocalCol` e o eixo Y utiliza a coluna de força em KGF no padrão "
        "`PLCnext_Arp_Plc_Eclr_FORCA_SKID_#_G#_KGF`. A escala automática aplica margem visual; "
        "use a escala manual para fixar limites específicos de força."
    )


def main() -> None:
    st.set_page_config(
        page_title="Visualizador MDB Supervisório",
        page_icon="▣",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_page_style()

    with st.sidebar:
        st.markdown("### Painel de seleção")
        st.caption("Configure o banco, selecione o cilindro e escolha o teste armazenado.")

        db_path = st.text_input(
            "Arquivo Microsoft Access (.mdb)",
            value=os.getenv("MDB_PATH", DEFAULT_DB_PATH),
            help="Caminho do banco legado informado no plano de trabalho.",
        )

        cylinder = st.selectbox(
            "Cilindro",
            options=list(CYLINDER_CONFIG.keys()),
            format_func=lambda value: CYLINDER_CONFIG[value]["label"],
        )

        cfg = CYLINDER_CONFIG[cylinder]
        st.info(f"Tabela aplicada: {cfg['table']}\n\nColuna de teste: {cfg['test_col']}")

        refresh = st.button("Recarregar consultas", use_container_width=True)
        if refresh:
            st.cache_data.clear()

    render_header()

    try:
        tests_df = load_tests(db_path, cylinder)

        if tests_df.empty:
            st.warning(
                f"Nenhum teste foi localizado na coluna {cfg['test_col']} da tabela {cfg['table']}."
            )
            render_driver_diagnostics(db_path)
            return

        test_options = tests_df["ID_Teste"].tolist()
        selected_test = st.selectbox(
            "Testes armazenados",
            options=test_options,
            format_func=lambda value: str(value),
            help=f"Lista carregada por SELECT DISTINCT na coluna {cfg['test_col']}.",
        )

        records_df = load_test_records(db_path, cylinder, selected_test)

        metric_col_1, metric_col_2, metric_col_3, metric_col_4 = st.columns(4)
        metric_col_1.metric("Cilindro", f"{cylinder:02d}")
        metric_col_2.metric("Tabela", cfg["table"])
        metric_col_3.metric("Testes encontrados", len(test_options))
        metric_col_4.metric("Registros do teste", len(records_df))

        st.divider()

        chart_tab, data_tab, sql_tab = st.tabs(["Gráfico de força", "Tabela de dados", "Consulta aplicada"])

        with chart_tab:
            build_chart(records_df, cylinder)

        with data_tab:
            st.subheader("Registros completos do teste selecionado")
            st.dataframe(records_df, use_container_width=True, hide_index=True)

            csv_bytes = records_df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                "Baixar registros filtrados em CSV",
                data=csv_bytes,
                file_name=f"{cfg['table']}_{cfg['test_col']}_{selected_test}.csv".replace(" ", "_"),
                mime="text/csv",
            )

        with sql_tab:
            st.subheader("Como o filtro foi aplicado")
            st.markdown(
                f"""
                A escolha do cilindro determina a tabela e a coluna de teste. Para o cilindro selecionado,
                a aplicação consulta primeiro os testes disponíveis e depois filtra os registros por parâmetro,
                evitando concatenar diretamente o valor do teste na consulta SQL.

                | Item | Valor aplicado |
                |---|---|
                | Cilindro | `{cylinder:02d}` |
                | Tabela | `{cfg['table']}` |
                | Coluna de filtro | `{cfg['test_col']}` |
                | Teste selecionado | `{selected_test}` |

                ```sql
                SELECT *
                FROM [{cfg['table']}]
                WHERE [{cfg['test_col']}] = ?
                ORDER BY [LocalCol]
                ```
                """
            )

        render_driver_diagnostics(db_path)

    except AppError as exc:
        st.error(str(exc))
        with st.expander("Orientações para correção", expanded=True):
            st.markdown(
                """
                1. Confirme se o arquivo `C:\\Supervisorio\\DLOGGERS\\projeto_54_DLR.mdb` existe e não está bloqueado.
                2. Instale as dependências Python com `python -m pip install -r requirements_visualizador_mdb.txt`.
                3. Instale o **Microsoft Access Database Engine** se nenhum driver ODBC do Access for listado.
                4. Reinicie o terminal após instalar o driver e execute novamente o aplicativo.
                """
            )
    except Exception as exc:  # proteção final para falhas inesperadas
        st.exception(exc)


if __name__ == "__main__":
    main()

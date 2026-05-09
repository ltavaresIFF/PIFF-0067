# Visualizador MDB Supervisório

Este pacote foi criado a partir do plano de trabalho em `01_plano_original.md`. A entrega implementa uma aplicação Web em **Python com Streamlit** para acessar o banco Microsoft Access localizado em `C:\Supervisorio\DLOGGERS\projeto_54_DLR.mdb`, selecionar cilindros de 01 a 10, listar os testes armazenados e visualizar os registros completos em tabela e gráfico.

> A interface foi projetada segundo a abordagem **Swiss Industrial Information Design**: hierarquia técnica clara, contraste operacional, baixa ornamentação e foco em leitura confiável de dados industriais.

## Arquivos entregues

| Arquivo | Finalidade |
|---|---|
| `visualizador_mdb_supervisorio.py` | Script principal da aplicação Web em Streamlit. |
| `requirements_visualizador_mdb.txt` | Lista de dependências Python necessárias para executar a aplicação. |
| `executar_visualizador_mdb.bat` | Atalho para instalar dependências e iniciar o servidor local. |
| `README_VISUALIZADOR_MDB.md` | Este guia de instalação, execução e lógica de filtragem. |

## Pré-requisitos

A aplicação depende de Python, Streamlit, pandas, Plotly e pyodbc. O `pyodbc` usa os drivers ODBC instalados no Windows para abrir o arquivo `.mdb`; portanto, além das bibliotecas Python, é necessário que exista um **driver ODBC do Microsoft Access** compatível com a arquitetura do Python instalado, como o driver `Microsoft Access Driver (*.mdb, *.accdb)`.[1] [2]

| Item | Observação |
|---|---|
| Python | Recomenda-se Python 3.10 ou superior no Windows. |
| Driver Access ODBC | Necessário para o `pyodbc` conseguir abrir arquivos `.mdb` e `.accdb`. |
| Banco de dados | O caminho padrão utilizado é `C:\Supervisorio\DLOGGERS\projeto_54_DLR.mdb`. |
| Navegador | A interface abre localmente em `http://localhost:8501`. |

## Execução rápida

A forma mais simples é executar o arquivo abaixo com duplo clique no Windows:

```bat
C:\Supervisorio\executar_visualizador_mdb.bat
```

Esse atalho entra na pasta `C:\Supervisorio`, instala as dependências listadas em `requirements_visualizador_mdb.txt` e inicia a aplicação Streamlit em `http://localhost:8501`.[3]

## Execução manual

Caso prefira executar pelo terminal, abra o **Prompt de Comando** ou **PowerShell** e rode:

```bat
cd /d C:\Supervisorio
python -m pip install -r requirements_visualizador_mdb.txt
python -m streamlit run visualizador_mdb_supervisorio.py --server.address localhost --server.port 8501
```

Se o comando `python` não estiver disponível, tente substituir por `py`:

```bat
py -m pip install -r requirements_visualizador_mdb.txt
py -m streamlit run visualizador_mdb_supervisorio.py --server.address localhost --server.port 8501
```

## Regra de seleção de tabelas

A aplicação transforma a escolha do cilindro em uma tabela e em uma coluna de filtro. Para cilindros 01 a 05, usa as tabelas do grupo `LogGA_C##`; para cilindros 06 a 10, usa as tabelas do grupo `LogGB_C##`. O identificador de teste segue o padrão `Cilindro_##_ID_Teste`.

| Cilindros | Tabela aplicada | Coluna usada para listar e filtrar testes |
|---|---|---|
| 01 a 05 | `LogGA_C##` | `Cilindro_##_ID_Teste` |
| 06 a 10 | `LogGB_C##` | `Cilindro_##_ID_Teste` |

## Como o filtro foi aplicado na consulta SQL

Primeiro, a aplicação carrega a lista de testes disponíveis com uma consulta `SELECT DISTINCT`, usando a coluna de teste do cilindro selecionado. Depois que o usuário escolhe um teste na lista suspensa, a aplicação executa uma segunda consulta parametrizada para retornar todos os registros desse teste.

```sql
SELECT DISTINCT [Cilindro_##_ID_Teste] AS ID_Teste
FROM [LogGA_C## ou LogGB_C##]
WHERE [Cilindro_##_ID_Teste] IS NOT NULL
ORDER BY [Cilindro_##_ID_Teste]
```

Após a seleção do teste, a consulta principal é:

```sql
SELECT *
FROM [LogGA_C## ou LogGB_C##]
WHERE [Cilindro_##_ID_Teste] = ?
ORDER BY [LocalCol]
```

O caractere `?` representa um parâmetro enviado ao `pyodbc`. Essa abordagem evita concatenar diretamente o valor do teste na string SQL e mantém o filtro restrito ao identificador selecionado na interface.[2]

## Visualizações geradas

A aplicação exibe a tabela completa dos registros retornados e gera um gráfico de linha com `LocalCol` no eixo X e `Cilindro_##_ID_Teste` no eixo Y, conforme solicitado no plano original. Como os registros são filtrados por um único teste, o valor do identificador de teste tende a ser constante; nesse caso, o gráfico pode aparecer como uma linha horizontal, o que é esperado para essa regra de visualização.

## Tratamento de erros

A interface informa mensagens amigáveis para falhas comuns, incluindo caminho de banco inexistente, ausência do `pyodbc`, inexistência de driver ODBC do Access e erro de conexão com o arquivo `.mdb`. Há também uma seção de diagnóstico que lista os drivers Access detectados pelo Python.

## Referências

[1]: https://learn.microsoft.com/en-us/sql/odbc/microsoft/microsoft-access-driver-programming-considerations "Microsoft Learn — Microsoft Access Driver Programming Considerations"
[2]: https://github.com/mkleehammer/pyodbc/wiki "pyodbc Wiki"
[3]: https://docs.streamlit.io/get-started/installation "Streamlit Documentation — Installation"
[4]: https://plotly.com/python/line-charts/ "Plotly Python — Line Charts"

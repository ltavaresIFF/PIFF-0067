# PIFF-0067 — Projeto Cerâmica

Este repositório contém os arquivos do **Visualizador MDB Supervisório**, uma aplicação em Python com Streamlit para consultar dados de um banco Microsoft Access (`.mdb`) do supervisório e visualizar os resultados de ensaios por cilindro.

## Estrutura do projeto

| Caminho | Descrição |
|---|---|
| `visualizador_mdb_supervisorio/visualizador_mdb_supervisorio.py` | Script principal da aplicação Streamlit. |
| `visualizador_mdb_supervisorio/requirements_visualizador_mdb.txt` | Dependências Python necessárias para executar a aplicação. |
| `visualizador_mdb_supervisorio/executar_visualizador_mdb.bat` | Arquivo batch para facilitar a instalação das dependências e execução no Windows. |
| `visualizador_mdb_supervisorio/README_VISUALIZADOR_MDB.md` | Instruções detalhadas de instalação, configuração, execução e uso. |

## Funcionalidades implementadas

A aplicação permite selecionar o cilindro, listar testes disponíveis, consultar os dados no MDB, exibir tabela completa e gerar gráfico com **LocalCol no eixo X** e a força em KGF no eixo Y, usando colunas no padrão `PLCnext_Arp_Plc_Eclr_FORCA_SKID_#_G#_KGF`. A interface também possui controles de escala automática ou manual do eixo Y, controle de altura do gráfico, opção de exibir pontos e correções explícitas de contraste para evitar texto claro sobre fundo claro.

## Execução no Windows

Para executar no computador onde está o banco `.mdb`, entre na pasta `visualizador_mdb_supervisorio` e use o arquivo `executar_visualizador_mdb.bat`. Como alternativa, instale as dependências manualmente e execute o Streamlit:

```powershell
pip install -r requirements_visualizador_mdb.txt
streamlit run visualizador_mdb_supervisorio.py
```

## Observações de versionamento

Arquivos de banco Access (`.mdb`, `.accdb`), caches Python, ambientes virtuais e pacotes compactados foram mantidos fora do versionamento por segurança e organização. O repositório versiona apenas o código-fonte e os arquivos de apoio necessários para recriar e executar a aplicação.

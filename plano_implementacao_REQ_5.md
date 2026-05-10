# Plano de Implementação — REQ_5

**Autor:** Manus AI  
**Data:** 10/05/2026

## Contexto técnico

O arquivo `REQ_5.txt` solicita que a interface de monitoramento de força permita a análise temporal dos dados, a seleção assistida de pontos no gráfico e o registro imediato de observações vinculadas ao valor técnico capturado. A implementação deve preservar a integridade entre o comentário do operador e o valor de força selecionado, evitando registros incompletos ou inconsistentes.

> A diretriz central do requisito é transformar a visualização gráfica em uma ferramenta operacional de registro de anomalias, vinculando **tempo**, **valor de força** e **comentário do operador** em uma única operação persistente.

## Mapeamento entre requisitos e implementação

| Requisito do REQ_5 | Implementação prevista em `app.py` |
|---|---|
| Eixo X temporal e eixo Y com valor de força | Manter o uso de `build_plotly_figure` com as colunas selecionadas e reforçar a identificação visual do ponto selecionado. |
| Detecção de proximidade com tolerância configurável | Adicionar um controle de tolerância visual na barra lateral e aplicar configurações de interação do Plotly, como `hoverdistance`, `spikedistance` e `clickmode`, além do mecanismo nativo de seleção de pontos do Streamlit. |
| Feedback visual imediato | Atualizar o estado de seleção com os dados do ponto, exibir confirmação visual em destaque, valor capturado em campo somente leitura e mensagem de confirmação contextual. |
| Formulário modal de observação | Utilizar `st.dialog` quando disponível, com fallback para painel inline em versões antigas do Streamlit. |
| Captura automática do valor de força | Persistir `obs_y_value` como valor somente leitura, sem edição manual pelo operador. |
| Persistência atômica de comentário e valor | Garantir que `ensure_obs_column`, `ensure_vals_column` e `update_obs_by_coordinate` sejam executados dentro do mesmo fluxo de confirmação, validando seleção e comentário antes da gravação. |
| Gravação imediata no banco | Manter gravação direta no clique de confirmação, limpar cache e recarregar os dados após sucesso. |

## Sequência de execução

A implementação será realizada em quatro etapas. Primeiro, o estado da sessão será ampliado para registrar tolerância de seleção, contexto modal e dados de exibição do ponto. Em seguida, o gráfico será configurado para facilitar hit-testing e feedback visual, com distância de interação ajustável. Depois, o editor de observações será reestruturado para operar como diálogo modal quando a versão do Streamlit suportar esse recurso. Por fim, o fluxo de gravação será endurecido com validações explícitas para impedir registros órfãos.

## Critérios de aceite

| Critério | Resultado esperado |
|---|---|
| Seleção de ponto | O operador consegue selecionar um ponto no gráfico e visualizar imediatamente tempo, série e valor capturado. |
| Feedback de destaque | O gráfico realça o ponto selecionado e a interface mostra confirmação do valor de força. |
| Comentário | O comentário é digitado em formulário dedicado e o valor técnico permanece somente leitura. |
| Persistência | O registro só é salvo quando há ponto selecionado, valor de força válido e comentário processável. |
| Integridade | Comentário e valor capturado são persistidos no mesmo fluxo transacional já centralizado em `update_obs_by_coordinate`. |
| Usabilidade | Caso o ambiente não suporte diálogo modal, a interface continua funcional por meio de painel inline. |

## Observações de compatibilidade

Como o arquivo atual já possui mecanismos de seleção por `st.plotly_chart`, persistência por coordenada e atualização das colunas `OBS` e `val_obs`/valores associados, a alteração priorizará evolução incremental e compatível. A abordagem evita dependências externas e preserva a estrutura existente do projeto.

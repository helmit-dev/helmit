# HelmIt

[English](README.md) | Português (Brasil)

**Um harness enxuto para desenvolvimento de software com agentes que usa o
desenvolvimento orientado por especificações (SDD) como uma disciplina
prática de trabalho.** O HelmIt mantém intenção, progresso, decisões e provas
do projeto no repositório, permitindo continuar o trabalho entre sessões sem
depender da memória de uma única conversa.

## O que o HelmIt ajuda você a fazer

O HelmIt oferece a um agente de programação estrutura suficiente para conduzir
uma entrega de software desde o resultado esperado até a verificação, sem
transformar toda mudança em um grande exercício de especificação.

- **Especificação proporcional.** Uma correção clara continua pequena. Uma
  entrega recebe o detalhamento necessário para ser implementada sem inventar
  comportamento de produto.
- **Continuidade registrada no repositório.** Requisitos, decisões, posição
  atual e trabalho pendente permanecem disponíveis quando você muda de sessão,
  agente ou máquina.
- **Proteção determinística.** Cada commit lógico atravessa um piso rápido e
  independente sobre o conteúdo preparado. A conclusão de tarefas executa
  provas focadas, e o fechamento da entrega executa ou reutiliza a prova
  completa configurada de testes, build e lint.
- **Limites de autoridade visíveis.** O agente continua pelas escolhas
  rotineiras de implementação. Decisões materiais de produto e ações externas
  continuam sob sua autoridade.
- **Um núcleo compartilhado.** Claude Code e Codex usam as mesmas skills,
  templates, hooks e artefatos de projeto, com formas de invocação específicas
  quando necessário.

O núcleo usa Bash e a biblioteca padrão do Python. Ele não exige banco de
dados, serviço em nuvem ou processo permanente em segundo plano.

## O comando que você precisa lembrar

```text
/helmit:next
```

`next` lê a posição registrada do projeto, explica onde o trabalho está e
identifica a próxima ação elegível. No Codex, selecione a skill correspondente
`helmit:next` com `$`, `/skills` ou pela interface de Skills.

O caminho normal é:

| Resultado | Comando | O que comprova o sucesso |
|---|---|---|
| Preparar o repositório | `/helmit:setup` | Os arquivos do HelmIt e o piso de commit do Git estão instalados |
| Definir o produto ou a entrega | `/helmit:spec` | O resultado autorizado e o aceite estão explícitos |
| Registrar arquitetura e comandos de qualidade | `/helmit:arch` | Os fatos da stack e os checks exatos estão registrados |
| Conferir o ambiente de trabalho | `/helmit:env` | As ferramentas locais necessárias estão prontas |
| Planejar e implementar | `/helmit:implement` | Os commits lógicos e as provas focadas das tarefas passam |
| Fechar a entrega | `/helmit:ship` | Cobertura, aceite e prova final completa passam |

`chart` continua disponível quando você deseja visualizar o planejamento
separadamente. `validate` continua disponível quando você deseja conferir a
prontidão final antes do ship. Nenhum dos dois é uma etapa obrigatória do ciclo.

Pequenas correções de manutenção e texto usam um registro delimitado `CHG-NNN`
em vez de criar artificialmente um novo requisito ou uma fase de entrega.

## Instalação

O HelmIt é instalado deste repositório como um plugin nativo. Registre o
catálogo e depois instale o nome qualificado do plugin.

### Claude Code

```text
/plugin marketplace add helmit-dev/helmit
/plugin install helmit@helmit
```

### Codex

```text
codex plugin marketplace add helmit-dev/helmit
codex plugin add helmit@helmit
```

### Peça ao agente para instalar

Você também pode solicitar a instalação em linguagem natural:

> **Claude Code:** "Instale o plugin HelmIt para mim. Adicione o marketplace
> `helmit-dev/helmit`, instale `helmit@helmit` e confirme que o plugin aparece
> como instalado."

> **Codex Desktop ou CLI:** "Instale o plugin HelmIt para mim. Registre o
> marketplace `helmit-dev/helmit`, instale `helmit@helmit` e confirme a versão
> instalada."

Revise as ações solicitadas pelo cliente durante a instalação.

Sempre use `helmit@helmit`. Quando vários marketplaces estão registrados, um
nome de plugin não qualificado fica ambíguo. Na primeira instalação, o Codex
apresenta os hooks do plugin como não confiáveis para que você possa revisá-los
e habilitá-los.

## Comece em um projeto

No Claude Code:

```text
/helmit:setup
/helmit:next
```

No Codex CLI ou na extensão para IDE, selecione `helmit:setup` e `helmit:next`
com `$` ou `/skills`. No Codex Desktop, selecione essas skills em Skills.

`setup` prepara o projeto uma vez. Depois disso, `next` é o ponto de entrada
seguro quando você retorna ao projeto ou muda de sessão.

## O que permanece visível

O HelmIt registra seu contexto de trabalho dentro de `.helmit/` no projeto que
o utiliza. O painel local `.helmit/dashboard.html` resume roadmap, requisitos,
mudanças, Inbox, validação e posição atual sem exigir um servidor.

O painel é uma projeção dos artefatos do repositório. Os arquivos continuam
sendo a fonte da verdade, e escritores determinísticos atualizam o painel
quando esses artefatos mudam.

## Projetos greenfield e brownfield

Em um projeto novo, o HelmIt ajuda a definir produto, arquitetura, comandos de
qualidade e primeira entrega.

Em um projeto existente, o HelmIt trata o comportamento funcional como
baseline. Ele detecta fatos observáveis de stack e comandos no repositório,
registra lacunas com honestidade e pergunta apenas sobre conflitos, checks
obrigatórios ausentes ou mudanças desejadas de arquitetura. A equipe não
precisa reescrever o sistema existente como uma especificação antes de iniciar
trabalho útil.

## Autonomia sem reduzir as provas

`/helmit:yolo phase` e `/helmit:yolo full` permitem autorizar um intervalo
maior de trabalho sem repetir pedidos de aprovação. Eles não desativam o piso
de commit, a verificação focada, a prova final ou os limites para ações externas.

Um heartbeat opcional pode recuperar uma execução autônoma interrompida de
forma inesperada em hosts que oferecem um mecanismo nativo de agendamento. Ele
não é o supervisor normal do trabalho ativo.

## Documentação

- [Instalação e primeiros passos](https://helmit.dev/pt-br/guides/getting-started/)
- [Entenda o processo](https://helmit.dev/pt-br/guides/flows/)
- [Acompanhe uma entrega da spec ao ship](https://helmit.dev/pt-br/guides/phase-lifecycle/)
- [Entenda testes e provas de entrega](https://helmit.dev/pt-br/guides/testing/)
- [Use os modos de autonomia](https://helmit.dev/pt-br/guides/autonomy/)
- [Compare o comportamento entre plataformas](https://helmit.dev/pt-br/guides/platforms/)
- [Resolva situações comuns](https://helmit.dev/pt-br/guides/troubleshooting/)
- [Documentação em inglês](https://helmit.dev/en/)

## Licença

O HelmIt é distribuído sob a [Licença MIT](LICENSE).

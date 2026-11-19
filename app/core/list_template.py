"""Planilha modelo da opção "Planilhar"."""

from __future__ import annotations

from pathlib import Path

TEMPLATE_FILENAME = "modelo_lista.xlsx"
TEMPLATE_COLUMNS = ["nome", "email", "arquivo_certificado"]
TEMPLATE_EXAMPLES = [
    ["Marina Silva de Souza", "marina@email.com", "marina_silva_de_souza"],
    ["José Álvares", "jose@email.com", "jose_alvares"],
]
TEMPLATE_INSTRUCTIONS = [
    "1. Preencha a aba \"Lista\": uma pessoa por linha, a partir da linha 2.",
    "2. A linha 1 (cabeçalho) é travada: não dá para mudar o nome das colunas nome, email e arquivo_certificado.",
    "3. Em arquivo_certificado, coloque o nome do PDF da pessoa. O \".pdf\" no final é opcional: o programa acrescenta sozinho.",
    "4. Pode acrescentar outras colunas a partir da coluna D (ex.: Curso, Data). Elas viram variáveis no email, como {curso}.",
    "5. Salve e arraste o arquivo para a área indicada no programa.",
]

# Guia "O que você pode escrever": (título da seção, explicação, linhas [pode escrever, exemplo, o programa entende]).
GUIDE_HEADERS = ["Pode escrever", "Exemplo", "O programa entende"]
TEMPLATE_GUIDE = [
    (
        "Coluna nome",
        "Escreva o nome como quiser: o programa arruma maiúsculas e espaços para o email.",
        [
            ["Acentos e ç", "José da Conceição", "José da Conceição"],
            ["Tudo em MAIÚSCULAS", "JOÃO DA SILVA", "João da Silva"],
            ["Tudo em minúsculas", "maria dos santos", "Maria dos Santos"],
            ["Maiúsculas e minúsculas misturadas", "Ronald McDonald", "Ronald McDonald (fica como está)"],
            ["Hífen e apóstrofo", "ANA-LUÍSA D'ÁVILA", "Ana-Luísa D'Ávila"],
            ["Espaços a mais", "\"  Pedro   Souza  \"", "Pedro Souza"],
            ["Célula vazia", "(em branco)", "O email vai só com o endereço, sem nome"],
        ],
    ),
    (
        "Coluna email",
        "Um endereço por célula. Pode copiar e colar de outro lugar.",
        [
            ["Maiúsculas", "Ana.Lima@Empresa.com", "O mesmo que ana.lima@empresa.com"],
            ["Pontos, +, - e _", "ana.lima+cursos@email.com", "Aceito"],
            ["Domínios com vários pontos", "jose@sub.empresa.com.br", "Aceito"],
            ["Espaços antes ou depois", "\" ana@email.com \"", "ana@email.com"],
            ["Texto colado da internet ou do Word", "ana@email.com", "Caracteres invisíveis são removidos"],
        ],
    ),
    (
        "Coluna arquivo_certificado",
        "O nome do PDF que está na pasta dos certificados. Não precisa ser idêntico:",
        [
            ["Sem o .pdf no final", "marina_silva", "marina_silva.pdf"],
            ["Com o .pdf no final", "marina_silva.pdf", "marina_silva.pdf"],
            ["Maiúsculas ou minúsculas", "MARINA_SILVA", "Acha o arquivo marina_silva.pdf"],
            ["Com ou sem acento", "jose_alvares", "Acha o arquivo José_Álvares.pdf"],
            ["Espaço, _ ou - entre as palavras", "Marina Silva  ou  marina-silva", "Acha o arquivo marina_silva.pdf"],
            ["Caminho completo do arquivo", "C:\\Certificados\\marina_silva.pdf", "Usa só o nome: marina_silva.pdf"],
        ],
    ),
    (
        "Outras colunas (a partir da coluna D)",
        "Crie quantas quiser. Cada uma vira uma variável que você usa no texto do email.",
        [
            ["Qualquer nome de coluna", "Data de Conclusão", "Use {data_de_conclusao} no email"],
            ["Datas", "10/11/2026", "10/11/2026"],
            ["Números", "40", "40"],
            ["Texto livre, com acentos e símbolos", "Gestão & Inovação", "Gestão & Inovação"],
        ],
    ),
    (
        "A planilha em geral",
        "Detalhes que o programa resolve sozinho.",
        [
            ["Linhas em branco no meio da lista", "(linha vazia)", "São puladas"],
            ["Espaços antes ou depois do texto", "\" Curso de Excel \"", "Curso de Excel"],
            ["Salvar como Excel ou CSV", "lista.xlsx  ou  lista.csv", "Os dois funcionam"],
            ["CSV separado por ; , tabulação ou |", "nome;email;arquivo_certificado", "Detectado sozinho"],
        ],
    ),
]
UNLOCKED_COLUMNS = 26  # A..Z ficam editáveis (exceto o cabeçalho de A..C)


def write_template(path: Path | str) -> Path:
    """Grava a planilha modelo (.xlsx) em path e devolve o caminho.

    Aba "Lista": só o cabeçalho, congelado e protegido (sem senha).
    Aba "Instruções": passo a passo, um exemplo preenchido e o guia do que é aceito em cada coluna.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill, Protection
    from openpyxl.utils import get_column_letter

    path = Path(path)
    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F6AA5")
    widths = [40, 36, 36]

    ws = wb.active
    ws.title = "Lista"
    ws.append(TEMPLATE_COLUMNS)
    for i in range(1, UNLOCKED_COLUMNS + 1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].protection = Protection(locked=False)
        ws.column_dimensions[letter].width = widths[i - 1] if i <= len(widths) else 20
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")
        cell.protection = Protection(locked=True)
    ws.freeze_panes = "A2"
    # Protege a aba para travar o cabeçalho, mas deixa formatar, ordenar, filtrar e inserir/apagar linhas.
    prot = ws.protection
    prot.sheet = True
    prot.formatCells = prot.formatColumns = prot.formatRows = False
    prot.insertRows = prot.deleteRows = False
    prot.sort = prot.autoFilter = False

    _write_instructions(wb.create_sheet("Instruções"), header_font, header_fill)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def _write_instructions(info, header_font, header_fill) -> None:
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    title_font = Font(bold=True, size=16, color="1F6AA5")
    section_font = Font(bold=True, size=13, color="1F6AA5")
    note_font = Font(italic=True, color="606060")
    example_font = Font(italic=True, color="606060")
    table_head_font = Font(bold=True, color="1F1F1F")
    table_head_fill = PatternFill("solid", fgColor="DCE8F4")
    thin = Side(style="thin", color="C9D6E3")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    wrap = Alignment(wrap_text=True, vertical="top")

    info.sheet_view.showGridLines = False
    for letter, width in zip("ABC", (38, 36, 42)):
        info.column_dimensions[letter].width = width

    def full_width_line(text: str, font) -> None:
        info.append([text])
        row = info.max_row
        info.merge_cells(start_row=row, start_column=1, end_row=row, end_column=3)
        cell = info.cell(row=row, column=1)
        cell.font = font
        cell.alignment = wrap
        # Células mescladas não ajustam a altura sozinhas: calcula pelo tamanho do texto.
        lines = max(1, -(-len(text) // 105))
        if lines > 1:
            info.row_dimensions[row].height = 15 * lines + 2

    # 1. Passo a passo
    full_width_line("Como preencher", title_font)
    for line in TEMPLATE_INSTRUCTIONS:
        full_width_line(line, Font())
    info.append([])

    # 2. Exemplo preenchido
    full_width_line("Exemplo", section_font)
    info.append(TEMPLATE_COLUMNS)
    for cell in info[info.max_row]:
        cell.font = header_font
        cell.fill = header_fill
    for row in TEMPLATE_EXAMPLES:
        info.append(row)
        for cell in info[info.max_row]:
            cell.font = example_font
    info.append([])

    # 3. Guia do que é aceito
    full_width_line("O que você pode escrever em cada coluna", title_font)
    full_width_line("Não precisa ter cuidado com maiúsculas, acentos ou espaços: o programa entende as variações abaixo.",
                    note_font)
    for title, explanation, rows in TEMPLATE_GUIDE:
        info.append([])
        full_width_line(title, section_font)
        full_width_line(explanation, note_font)
        info.append(GUIDE_HEADERS)
        for cell in info[info.max_row]:
            cell.font = table_head_font
            cell.fill = table_head_fill
            cell.border = border
            cell.alignment = wrap
        for row in rows:
            info.append(row)
            for col, cell in enumerate(info[info.max_row], start=1):
                cell.border = border
                cell.alignment = wrap
                if col == 1:
                    cell.font = Font(bold=True)


def missing_columns(headers: list[str]) -> list[str]:
    """Colunas do modelo que faltam na planilha (ignora maiúsculas, acentos e espaços)."""
    from app.core.text import variable_key

    present = {variable_key(h) for h in headers}
    return [c for c in TEMPLATE_COLUMNS if c not in present]
